import os, yaml
from playwright.sync_api import Page
from bot.utils import logger
from bot.config import PROJECT_FOLDER

PROFILE_PATH = os.path.join(PROJECT_FOLDER, "profile.yaml")

def learn_from_filled_form(page: Page, site: str):
    """
    Scans the current page/modal for all filled inputs, selects, radios, and checkboxes.
    If the user has entered new or different answers, saves them back to profile.yaml
    so the bot learns and applies the same answers in future applications.
    """
    try:
        new_answers = page.evaluate("""
            () => {
                const data = {};
                
                // Helper to get element label
                const getLabel = (el) => {
                    let aria = el.getAttribute('aria-label');
                    if (aria && aria.trim()) return aria.trim();
                    
                    let id = el.getAttribute('id');
                    if (id) {
                        let label = document.querySelector('label[for="' + id + '"]');
                        if (label && label.innerText.trim()) return label.innerText.trim();
                    }
                    
                    let parent = el.closest('fieldset, .form-group, .fb-form-element, [class*="group"], [class*="element"], [class*="row"]');
                    if (parent) {
                        let legend = parent.querySelector('legend, label, p, span, [class*="label"], [class*="title"], [class*="question"]');
                        if (legend && legend.innerText.trim()) return legend.innerText.trim();
                        let firstLine = parent.innerText.trim().split('\\n')[0];
                        if (firstLine && firstLine.trim()) return firstLine.trim();
                    }
                    
                    let sib = el.previousElementSibling;
                    while (sib) {
                        if (sib.tagName.match(/H[1-6]|LABEL|P|SPAN/i) && sib.innerText.trim()) {
                            return sib.innerText.trim();
                        }
                        sib = sib.previousElementSibling;
                    }
                    
                    let ph = el.getAttribute('placeholder');
                    if (ph && ph.trim()) return ph.trim();
                    
                    let name = el.getAttribute('name');
                    if (name && name.trim()) return name.trim();
                    
                    return '';
                };

                // 1. Text inputs & Textareas
                const inputs = document.querySelectorAll('input[type="text"], input[type="number"], input[type="email"], input:not([type]), textarea');
                inputs.forEach(el => {
                    if (el.offsetWidth === 0 && el.offsetHeight === 0) return; // not visible
                    let type = (el.getAttribute('type') || '').toLowerCase();
                    if (['checkbox', 'radio', 'hidden', 'file'].includes(type)) return;
                    
                    let val = el.value ? el.value.trim() : '';
                    if (val) {
                        let label = getLabel(el);
                        if (label) data[label] = val;
                    }
                });

                // 2. Selects
                const selects = document.querySelectorAll('select');
                selects.forEach(el => {
                    if (el.offsetWidth === 0 && el.offsetHeight === 0) return;
                    let opt = el.options[el.selectedIndex];
                    let val = opt ? opt.text.trim() : '';
                    if (val && !['', 'select', 'select an option', '-1'].includes(val.toLowerCase())) {
                        let label = getLabel(el);
                        if (label) data[label] = val;
                    }
                });

                // 3. Radio groups
                const radios = document.querySelectorAll('input[type="radio"]:checked');
                radios.forEach(el => {
                    if (el.offsetWidth === 0 && el.offsetHeight === 0) return;
                    let label = getLabel(el);
                    let id = el.getAttribute('id');
                    let lblEl = id ? document.querySelector('label[for="' + id + '"]') : el.parentElement;
                    let val = lblEl ? lblEl.innerText.trim() : '';
                    if (label && val) {
                        data[label] = val;
                    }
                });

                // 4. Checkboxes
                const checkboxes = document.querySelectorAll('input[type="checkbox"]:checked');
                checkboxes.forEach(el => {
                    if (el.offsetWidth === 0 && el.offsetHeight === 0) return;
                    let id = el.getAttribute('id');
                    if (id && id.toLowerCase().includes('follow')) return; // skip company follows
                    let lblEl = id ? document.querySelector('label[for="' + id + '"]') : el.parentElement;
                    let label = lblEl ? lblEl.innerText.trim() : getLabel(el);
                    if (label) {
                        data[label] = 'Yes';
                    }
                });

                return data;
            }
        """)

        if not new_answers:
            return

        # Load profile
        profile = {}
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                profile = yaml.safe_load(f) or {}

        standard = profile.get("standard_answers", {})
        learned_any = False

        for q, a in new_answers.items():
            if not q or not a:
                continue
            if q not in standard or standard[q] != a:
                standard[q] = a
                logger.info(f"Learned from form: '{q}' = '{a}'", site)
                learned_any = True

        if learned_any:
            profile["standard_answers"] = standard
            with open(PROFILE_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(profile, f, allow_unicode=True, default_flow_style=False)
            logger.success(f"Profile updated with new learned answers.", site)

    except Exception as e:
        logger.warn(f"Learning engine error: {e}", site)
