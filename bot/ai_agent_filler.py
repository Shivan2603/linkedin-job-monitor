"""
bot/ai_agent_filler.py — AI-Powered Web Form Filler
Primary: Groq Llama 3.1 8B (fast) | Fallback: Groq 70B → Gemini → HuggingFace
"""
import json, os, yaml, re
from playwright.sync_api import Page
from bot.config import GROQ_API_KEY, PROJECT_FOLDER
from bot.utils import logger
from bot.ai_router import ai_complete


def load_profile() -> dict:
    profile_path = os.path.join(PROJECT_FOLDER, "profile.yaml")
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def extract_form_fields(page: Page) -> list:
    """Inject JS to extract all visible inputs, selects, and textareas."""
    return page.evaluate("""
        () => {
            const elements = document.querySelectorAll('input, select, textarea');
            const fields = [];
            elements.forEach((el, index) => {
                if (el.type === 'hidden' || el.disabled || el.style.display === 'none') return;
                let labelText = '';
                if (el.labels && el.labels.length > 0) {
                    labelText = el.labels[0].innerText;
                } else if (el.placeholder) {
                    labelText = el.placeholder;
                } else if (el.name || el.id) {
                    labelText = el.name || el.id;
                } else {
                    labelText = el.parentElement.innerText.trim().split('\\n')[0];
                }
                const selectorId = 'ai-form-field-' + index;
                el.setAttribute('data-ai-id', selectorId);
                fields.push({
                    id: selectorId,
                    type: el.tagName.toLowerCase(),
                    inputType: el.type,
                    label: labelText.trim(),
                    name: el.name,
                    options: el.tagName.toLowerCase() === 'select'
                        ? Array.from(el.options).map(o => o.text) : []
                });
            });
            return fields;
        }
    """)


def fill_form_with_ai(page: Page, site: str = "ai", resume_path: str = None) -> bool:
    """
    Extracts form fields, asks AI for answers (via ai_router), and fills the form.
    Uses fast Groq model (Llama 3.1 8B) for speed. Also uploads resume if provided.
    """
    # 1. Programmatically upload resume if provided
    if resume_path and os.path.exists(resume_path):
        try:
            file_inputs = page.locator('input[type="file"]').all()
            for file_in in file_inputs:
                try:
                    inp_id = file_in.get_attribute("id") or ""
                    inp_name = file_in.get_attribute("name") or ""
                    inp_class = file_in.get_attribute("class") or ""
                    
                    is_resume_input = file_in.evaluate("""
                        (el) => {
                            const id = el.id || '';
                            const name = el.name || '';
                            const className = el.className || '';
                            const aria = el.getAttribute('aria-label') || '';
                            const placeholder = el.placeholder || '';
                            const term = (id + ' ' + name + ' ' + className + ' ' + aria + ' ' + placeholder).toLowerCase();
                            if (term.includes('resume') || term.includes('cv') || term.includes('profile') || term.includes('document') || term.includes('upload')) return true;
                            
                            if (el.labels && el.labels.length > 0) {
                                const lblText = el.labels[0].innerText.toLowerCase();
                                if (lblText.includes('resume') || lblText.includes('cv') || lblText.includes('profile') || lblText.includes('document')) return true;
                            }
                            let parent = el.closest('div, label, section, fieldset');
                            if (parent) {
                                const parentText = parent.innerText.toLowerCase();
                                if (parentText.includes('resume') || parentText.includes('cv') || parentText.includes('profile') || parentText.includes('document')) return true;
                            }
                            return false;
                        }
                    """)
                    if is_resume_input:
                        logger.info(f"AI Filler: Uploading resume {resume_path} to input ID={inp_id}, Name={inp_name}", site)
                        file_in.set_input_files(resume_path)
                        logger.success(f"Resume uploaded successfully to {inp_name or inp_id or 'file input'}", site)
                except Exception as ex:
                    logger.warn(f"Failed to check/upload to file input: {str(ex)[:80]}", site)
        except Exception as e:
            logger.warn(f"Failed to process file inputs: {str(e)[:80]}", site)

    fields = extract_form_fields(page)
    if not fields:
        logger.info("No form fields found to fill.", site)
        return True

    profile = load_profile()

    system = """You are an AI job application assistant filling web forms.
Be precise. Match dropdown values EXACTLY from the options list.
Return ONLY a valid JSON array, no other text."""

    user = f"""User profile:
```json
{json.dumps(profile, indent=2)}
```

Form fields:
```json
{json.dumps(fields, indent=2)}
```

Fill each field from the profile. Rules:
1. Text inputs: exact string to type
2. Select: EXACT text from "options" array  
3. Checkbox/radio: "check" to tick, empty string to skip
4. Cover letter: professional 2-3 sentences
5. Skip CAPTCHA and file upload fields (type=file)

Return JSON array: [{"id": "ai-form-field-N", "value": "answer"}]"""

    try:
        raw = ai_complete(system, user, task="form_fill", max_tokens=1500)

        # Robust JSON cleaning and parsing
        raw = raw.strip()
        if "```json" in raw:
            candidate = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            candidate = raw.split("```")[1].split("```")[0].strip()
        else:
            # Try to find array brackets
            m = re.search(r'(\[.*?\])', raw, re.DOTALL)
            candidate = m.group(1).strip() if m else raw

        # 1. Escape raw newlines/tabs inside double-quoted string values
        pattern = re.compile(r'"(?:[^"\\]|\\.)*"')
        def repl(match):
            s = match.group(0)
            return s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        candidate = pattern.sub(repl, candidate)

        # 2. Strip any raw control characters that are not properly escaped
        candidate = re.sub(r'[\x00-\x1F\x7F]', '', candidate)

        # 3. Clean up trailing commas
        candidate = re.sub(r',\s*([\]}])', r'\1', candidate)

        try:
            actions = json.loads(candidate)
        except Exception as e:
            # Basic fallback attempt to auto-close quotes/brackets
            try:
                quotes = candidate.count('"')
                if quotes % 2 != 0:
                    candidate += '"'
                brackets = candidate.count('[') - candidate.count(']')
                braces = candidate.count('{') - candidate.count('}')
                candidate += '}' * braces
                candidate += ']' * brackets
                actions = json.loads(candidate)
            except Exception:
                raise e
        filled = 0

        for action in actions:
            field_id = action.get("id")
            val      = action.get("value")
            if not field_id or val is None or val == "":
                continue

            selector = f'[data-ai-id="{field_id}"]'
            try:
                el         = page.locator(selector).first
                # Use 3s timeout instead of default 30s — skip non-existent fields fast
                if not el.is_visible(timeout=3000):
                    continue
                tag_name   = el.evaluate("el => el.tagName.toLowerCase()", timeout=3000)
                input_type = el.evaluate("el => el.type", timeout=3000)

                if tag_name == "select":
                    el.select_option(label=str(val))
                elif input_type in ["checkbox", "radio"]:
                    if str(val).lower() in ["check", "true", "yes"]:
                        try:
                            el.check(force=True)
                        except Exception:
                            try:
                                el.click(force=True)
                            except Exception:
                                try:
                                    el.evaluate("el => el.click()")
                                except Exception:
                                    pass
                elif input_type == "file":
                    pass  # Skip file uploads as handled separately
                elif input_type == "number":
                    num_val = ''.join(c for c in str(val) if c.isdigit() or c == '.')
                    if num_val:
                        el.fill(num_val)
                else:
                    el.fill(str(val))
                filled += 1
            except Exception as ex:
                logger.warn(f"Failed to fill field {field_id}: {str(ex)[:60]}", site)

        logger.ai(f"Filled {filled}/{len(actions)} fields via AI.", site)
        return True

    except Exception as e:
        logger.error(f"AI Form Filler failed: {e}", site)
        return False
