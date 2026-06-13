"""
bot/ai_agent_filler.py — AI-Powered Web Form Filler
Extracts form fields from a page, asks Claude how to fill them based on profile.yaml, and executes the actions.
"""
import json
import os
import yaml
from playwright.sync_api import Page
from bot.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, PROJECT_FOLDER
from bot.utils import logger
from anthropic import Anthropic

client = Anthropic(api_key=ANTHROPIC_API_KEY)

def load_profile():
    profile_path = os.path.join(PROJECT_FOLDER, "profile.yaml")
    if os.path.exists(profile_path):
        with open(profile_path, "r") as f:
            return yaml.safe_load(f)
    return {}

def extract_form_fields(page: Page):
    """Inject JS to extract all visible inputs, selects, and textareas."""
    return page.evaluate("""
        () => {
            const elements = document.querySelectorAll('input, select, textarea');
            const fields = [];
            elements.forEach((el, index) => {
                // Skip hidden or disabled fields
                if (el.type === 'hidden' || el.disabled || el.style.display === 'none') return;
                
                // Try to find an associated label
                let labelText = '';
                if (el.labels && el.labels.length > 0) {
                    labelText = el.labels[0].innerText;
                } else if (el.placeholder) {
                    labelText = el.placeholder;
                } else if (el.name || el.id) {
                    labelText = el.name || el.id;
                } else {
                    // Try to look at previous sibling or parent text
                    labelText = el.parentElement.innerText.trim().split('\\n')[0];
                }
                
                // Add an artificial data attribute to select it later
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
    """Extracts form fields, asks Claude for answers, and fills the form."""
    if not ANTHROPIC_API_KEY or "PASTE_YOUR_KEY" in ANTHROPIC_API_KEY:
        logger.warn("Skipping AI form filling (no Anthropic API Key configured).", site)
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
4. If a field asks for something not in the profile (e.g. "Cover Letter"), provide a short, professional generic response or leave it empty if appropriate.
5. Provide the output strictly as a JSON array of objects, with keys "id" and "value".

Example output format:
```json
[
  {{"id": "ai-form-field-0", "value": "Siva Shankar"}},
  {{"id": "ai-form-field-1", "value": "Yes"}}
]
```
Return ONLY valid JSON.
"""
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw = response.content[0].text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
            
        actions = json.loads(raw)
        
        # Execute actions
        for action in actions:
            field_id = action.get("id")
            val = action.get("value")
            
            if not field_id or not val:
                continue
                
            selector = f'[data-ai-id="{field_id}"]'
            try:
                el = page.locator(selector)
                tag_name = el.evaluate("el => el.tagName.toLowerCase()")
                input_type = el.evaluate("el => el.type")
                
                if tag_name == 'select':
                    el.select_option(label=val)
                elif input_type in ['checkbox', 'radio']:
                    if val.lower() == 'check' or val.lower() == 'true' or val == 'Yes':
                        el.check()
                else:
                    el.fill(str(val))
            except Exception as ex:
                logger.warn(f"Failed to fill field {field_id}: {ex}", site)
                
        logger.ai(f"Successfully filled {len(actions)} fields using AI.", site)
        return True
    except Exception as e:
        logger.error(f"AI Form Filler failed: {e}", site)
        return False
