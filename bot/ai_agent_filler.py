"""
bot/ai_agent_filler.py — AI-Powered Web Form Filler (Google Gemini 2.0 Flash - FREE)
Extracts form fields from a page, asks Gemini how to fill them using profile.yaml, and executes the actions.
"""
import json
import os
import yaml
from playwright.sync_api import Page
from bot.config import GEMINI_API_KEY, GEMINI_MODEL, PROJECT_FOLDER
from bot.utils import logger
import google.generativeai as genai

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def load_profile():
    profile_path = os.path.join(PROJECT_FOLDER, "profile.yaml")
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}

def extract_form_fields(page: Page):
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
                    options: el.tagName.toLowerCase() === 'select' ? Array.from(el.options).map(o => o.text) : []
                });
            });
            return fields;
        }
    """)

def fill_form_with_ai(page: Page, site: str = "ai"):
    """Extracts form fields, asks Gemini for answers, and fills the form."""
    if not GEMINI_API_KEY or len(GEMINI_API_KEY) < 10:
        logger.warn("Skipping AI form filling (no Gemini API Key configured).", site)
        return False

    fields = extract_form_fields(page)
    if not fields:
        logger.info("No form fields found to fill.", site)
        return True

    profile = load_profile()

    prompt = f"""You are an AI job application assistant helping a user apply for jobs.
Here is the user's profile information:
```json
{json.dumps(profile, indent=2)}
```

Here is a list of form fields extracted from the current web page:
```json
{json.dumps(fields, indent=2)}
```

For each field, determine the best value to fill in.
Rules:
1. For text inputs, provide the exact string to type.
2. For select dropdowns, provide the EXACT text of one of the options listed in the "options" array.
3. For checkboxes/radio buttons, provide "check" to check it, or leave value empty to ignore.
4. If a field asks for a Cover Letter, write a short professional 2-3 sentence response.
5. Skip fields that are clearly not relevant (e.g. CAPTCHA, file upload).
6. Provide the output strictly as a JSON array of objects with keys "id" and "value".

Return ONLY valid JSON array, no other text.
Example:
[
  {{"id": "ai-form-field-0", "value": "Siva Shankar"}},
  {{"id": "ai-form-field-1", "value": "Yes"}}
]
"""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        raw = response.text.strip()

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        actions = json.loads(raw)

        for action in actions:
            field_id = action.get("id")
            val = action.get("value")
            if not field_id or not val:
                continue
            selector = f'[data-ai-id="{field_id}"]'
            try:
                el = page.locator(selector)
                tag_name   = el.evaluate("el => el.tagName.toLowerCase()")
                input_type = el.evaluate("el => el.type")
                if tag_name == 'select':
                    el.select_option(label=val)
                elif input_type in ['checkbox', 'radio']:
                    if str(val).lower() in ['check', 'true', 'yes']:
                        el.check()
                else:
                    el.fill(str(val))
            except Exception as ex:
                logger.warn(f"Failed to fill field {field_id}: {ex}", site)

        logger.ai(f"Filled {len(actions)} fields using Gemini AI.", site)
        return True

    except Exception as e:
        logger.error(f"Gemini Form Filler failed: {e}", site)
        return False
