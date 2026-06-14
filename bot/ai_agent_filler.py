"""
bot/ai_agent_filler.py — AI-Powered Web Form Filler
Primary: Groq Llama 3.1 8B (fast) | Fallback: Groq 70B → Gemini → HuggingFace
"""
import json, os, yaml
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


def fill_form_with_ai(page: Page, site: str = "ai") -> bool:
    """
    Extracts form fields, asks AI for answers (via ai_router), and fills the form.
    Uses fast Groq model (Llama 3.1 8B) for speed.
    """
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
{json.dumps(profile, indent=2)[:3000]}
```

Form fields:
```json
{json.dumps(fields, indent=2)[:2000]}
```

Fill each field from the profile. Rules:
1. Text inputs: exact string to type
2. Select: EXACT text from "options" array  
3. Checkbox/radio: "check" to tick, empty string to skip
4. Cover letter: professional 2-3 sentences
5. Skip CAPTCHA and file upload fields (type=file)

Return JSON array: [{{"id": "ai-form-field-N", "value": "answer"}}]"""

    try:
        raw = ai_complete(system, user, task="form_fill", max_tokens=1500)

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        actions = json.loads(raw)
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
                        el.check()
                elif input_type == "file":
                    pass  # Skip file uploads
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
