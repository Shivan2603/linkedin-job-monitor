"""
bot/ai_agent_filler.py — AI-Powered Web Form Filler
Primary: Groq Llama 3.1 8B (fast) | Fallback: Groq 70B → Gemini → HuggingFace
"""
import json, os, yaml, re, time
from urllib.parse import urlparse
from playwright.sync_api import Page
from bot.config import GROQ_API_KEY, PROJECT_FOLDER, DATA_FOLDER
from bot.utils import logger
from bot.ai_router import ai_complete

ACCOUNTS_FILE = os.path.join(DATA_FOLDER, "workday_accounts.json")


def load_profile() -> dict:
    profile_path = os.path.join(PROJECT_FOLDER, "profile.yaml")
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def _load_workday_accounts() -> dict:
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_workday_account(domain: str, email: str):
    try:
        accounts = _load_workday_accounts()
        accounts[domain] = email
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warn(f"Failed to save Workday account: {e}", "ai")


def extract_form_fields(page: Page) -> list:
    """Inject JS to extract all visible inputs, selects, textareas, and custom comboboxes."""
    return page.evaluate("""
        () => {
            const allElements = document.querySelectorAll('input, select, textarea, [role="combobox"], [role="checkbox"], [role="radio"], [aria-haspopup="listbox"], [data-automation-id*="Dropdown"], [data-automation-id*="Select"]');
            const fields = [];
            const seen = new Set();
            
            allElements.forEach((el, index) => {
                // Skip hidden or disabled elements
                if (el.offsetWidth === 0 && el.offsetHeight === 0) return;
                if (el.disabled || el.getAttribute('aria-disabled') === 'true') return;
                if (el.type === 'hidden') return;
                if (seen.has(el)) return;
                seen.add(el);
                
                let labelText = '';
                
                // 1. Check aria-label
                const ariaLabel = el.getAttribute('aria-label');
                if (ariaLabel && ariaLabel.trim()) {
                    labelText = ariaLabel;
                }
                
                // 2. Check aria-labelledby
                if (!labelText) {
                    const labelledby = el.getAttribute('aria-labelledby');
                    if (labelledby) {
                        const lbl = document.getElementById(labelledby);
                        if (lbl && lbl.innerText.trim()) {
                            labelText = lbl.innerText;
                        }
                    }
                }
                
                // 3. Check associated label
                if (!labelText && el.labels && el.labels.length > 0) {
                    labelText = el.labels[0].innerText;
                }
                
                // 4. Check for label element pointing to this element's ID
                if (!labelText && el.id) {
                    const lbl = document.querySelector('label[for="' + el.id + '"]');
                    if (lbl && lbl.innerText.trim()) {
                        labelText = lbl.innerText;
                    }
                }
                
                // 5. Look up parent/sibling text (standard heuristic)
                if (!labelText) {
                    let parent = el.closest('fieldset, .form-group, [class*="group"], [class*="element"], [class*="row"], .wd-form-row');
                    if (parent) {
                        const legend = parent.querySelector('legend, label, [class*="label"], [class*="title"], [class*="question"]');
                        if (legend && legend.innerText.trim()) {
                            labelText = legend.innerText;
                        } else {
                            labelText = parent.innerText.trim().split('\\n')[0];
                        }
                    }
                }
                
                // 6. Check placeholder, name, id, or data-automation-id
                if (!labelText) {
                    labelText = el.placeholder || el.getAttribute('placeholder') || el.name || el.id || el.getAttribute('data-automation-id') || '';
                }
                
                labelText = labelText.trim().replace(/\\s+/g, ' ');
                // Strip trailing asterisks or punctuation from labels
                labelText = labelText.replace(/\\s*\\*\\s*$/, '').trim();
                
                const selectorId = 'ai-form-field-' + index;
                el.setAttribute('data-ai-id', selectorId);
                
                let inputType = el.type || '';
                const role = el.getAttribute('role') || '';
                const tag = el.tagName.toLowerCase();
                
                if (role === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox' || el.getAttribute('data-automation-id')?.toLowerCase().includes('dropdown') || el.getAttribute('data-automation-id')?.toLowerCase().includes('select')) {
                    inputType = 'combobox';
                } else if (role === 'checkbox') {
                    inputType = 'checkbox';
                } else if (role === 'radio') {
                    inputType = 'radio';
                }
                
                // Determine options for select
                let options = [];
                if (tag === 'select') {
                    options = Array.from(el.options).map(o => o.text.trim());
                }
                
                fields.push({
                    id: selectorId,
                    type: tag,
                    inputType: inputType,
                    label: labelText,
                    name: el.name || el.getAttribute('name') || el.getAttribute('data-automation-id') || '',
                    options: options
                });
            });
            return fields;
        }
    """)


def _upload_resume_if_needed(page: Page, resume_path: str, site: str):
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


def _handle_workday_entry_options(page: Page, site: str) -> bool:
    """Handles Workday-specific landing buttons to enter the application."""
    try:
        # Check if there is an Autofill with Resume button
        autofill_btn = page.query_selector('[data-automation-id="applyWithResume"], button:has-text("Autofill with Resume"), button:has-text("Autofill with CV")')
        if autofill_btn and autofill_btn.is_visible():
            logger.info("AI Filler: Workday landing options detected. Clicking 'Autofill with Resume'...", site)
            autofill_btn.click()
            time.sleep(3)
            return True
            
        # Or Apply Manually
        manual_btn = page.query_selector('[data-automation-id="applyManually"], button:has-text("Apply Manually")')
        if manual_btn and manual_btn.is_visible():
            logger.info("AI Filler: Workday landing options detected. Clicking 'Apply Manually'...", site)
            manual_btn.click()
            time.sleep(3)
            return True
    except Exception as e:
        logger.warn(f"Failed to handle Workday entry options: {e}", site)
    return False


def _handle_registration_or_signin(page: Page, site: str) -> bool:
    try:
        parsed = urlparse(page.url)
        domain = parsed.netloc.lower()
        
        email = "sivashankar.avi6@gmail.com"
        password = "SivaShankar@2026_Secure!"
        
        accounts = _load_workday_accounts()
        has_account = domain in accounts
        
        # Check if there is a "Create Account" button/link on the page and we DO NOT have an account saved
        create_account_btn = page.query_selector('button:has-text("Create Account"), a:has-text("Create Account"), [data-automation-id="createAccountLink"]')
        if create_account_btn and not has_account:
            logger.info("AI Filler: No cached account for this domain. Clicking 'Create Account'...", site)
            create_account_btn.click()
            time.sleep(2)
            # Check if registration form is loaded
            password_input = page.query_selector('input[type="password"]')
            if not password_input:
                return True
                
        # Now we are on a form page
        email_input = page.query_selector('input[type="email"], input[name*="email"], input[id*="username"], input[id*="email"], [data-automation-id="email"]')
        password_input = page.query_selector('input[type="password"]')
        
        if email_input and password_input:
            confirm_pwd = page.query_selector('input[id*="confirm"], input[name*="confirm"], input[placeholder*="Confirm"], [data-automation-id*="confirmPassword"]')
            
            email_input.scroll_into_view_if_needed()
            email_input.fill(email)
            password_input.fill(password)
            
            if confirm_pwd:
                logger.info("AI Filler: Registering new Workday account...", site)
                confirm_pwd.fill(password)
                
                # Check any terms / privacy checkboxes
                checkboxes = page.query_selector_all('input[type="checkbox"], [role="checkbox"]')
                for cb in checkboxes:
                    try:
                        if cb.is_visible() and not cb.is_checked():
                            cb.check(force=True)
                    except Exception:
                        try:
                            cb.click(force=True)
                        except Exception:
                            pass
                
                btn = page.query_selector('button[type="submit"], button:has-text("Create Account"), button:has-text("Register"), [data-automation-id="registerButton"]')
                if btn:
                    btn.click()
                    _save_workday_account(domain, email)
                    logger.success("AI Filler: Submitted registration. Saved credentials.", site)
                    return True
            else:
                logger.info("AI Filler: Logging in with credentials...", site)
                btn = page.query_selector('button[type="submit"], button:has-text("Sign In"), button:has-text("Log In"), [data-automation-id="signInButton"]')
                if btn:
                    btn.click()
                    _save_workday_account(domain, email)
                    return True
                    
        # Check if sign in failed because of invalid username/password
        error_msg = page.query_selector('.wd-error-message, [role="alert"], [class*="error"]')
        if error_msg and error_msg.is_visible():
            err_text = error_msg.inner_text().lower()
            if "not exist" in err_text or "invalid" in err_text or "incorrect" in err_text:
                logger.warn(f"AI Filler: Login failed ({err_text}). Attempting registration...", site)
                create_account_btn = page.query_selector('button:has-text("Create Account"), a:has-text("Create Account"), [data-automation-id="createAccountLink"]')
                if create_account_btn:
                    create_account_btn.click()
                    time.sleep(2)
                    return True
                    
    except Exception as e:
        logger.warn(f"Failed to handle registration/login form: {e}", site)
    return False


def _find_next_or_submit_button(page: Page):
    # Common submit / next buttons (prioritize Submit first, then Next/Continue)
    submit_selectors = [
        'button[data-automation-id="submit-button"]',
        'button[data-automation-id*="submit"]',
        'button:has-text("Submit Application")',
        'button:has-text("Submit")',
        'button:has-text("Apply")',
        'button:has-text("Submit application")',
    ]
    for sel in submit_selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible():
                return el
        except Exception:
            continue
            
    nav_selectors = [
        'button[data-automation-id="next-button"]',
        'button[data-automation-id="bottom-navigation-next-button"]',
        'button[data-automation-id*="next"]',
        'button:has-text("Next")',
        'button:has-text("Save and Continue")',
        'button:has-text("Continue")',
        'button:has-text("Review")',
        'button:has-text("Next Step")',
        'input[type="button"][value="Next"]',
        'input[type="submit"][value="Next"]',
    ]
    for sel in nav_selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible():
                return el
        except Exception:
            continue
    return None


def fill_form_with_ai(page: Page, site: str = "ai", resume_path: str = None) -> bool:
    """
    Extracts form fields, asks AI for answers, and fills forms.
    Can handle multi-step portals (like Workday) by looping page-by-page.
    """
    profile = load_profile()
    if not profile:
        logger.error("Profile configuration not loaded.", site)
        return False

    # Loop up to 8 steps for multi-page forms (Workday, SuccessFactors, direct portals)
    for step in range(8):
        # Wait a moment for the step to load
        time.sleep(2)
        
        # Check if we are on a Workday landing page with Apply or entry options
        _handle_workday_entry_options(page, site)
        
        # Check for standard "Apply" buttons on description pages to enter the application
        apply_btn = page.query_selector('[data-automation-id="adventureButton"], button:has-text("Apply"), button:has-text("Apply Now")')
        if apply_btn and apply_btn.is_visible() and not page.query_selector('input, textarea, select'):
            logger.info("AI Filler: Job description page detected. Clicking 'Apply' to enter application form...", site)
            apply_btn.click()
            time.sleep(3)
            continue
        
        # Check if we are on a login or registration screen
        if page.query_selector('input[type="password"]') and not page.query_selector('span:has-text("Apply"), [data-automation-id="genderDropdown"]'):
            logger.info("AI Filler: Login/Registration screen detected.", site)
            if _handle_registration_or_signin(page, site):
                time.sleep(3)
                continue

        # Upload resume to file inputs if any are visible on this step
        _upload_resume_if_needed(page, resume_path, site)

        # Extract fields visible on current page/tab
        fields = extract_form_fields(page)
        if not fields:
            # Check if there is a next/submit button to click even if no visible input fields
            next_btn = _find_next_or_submit_button(page)
            if next_btn:
                logger.info(f"AI Filler: No fields found on step {step + 1}, clicking next/submit button...", site)
                btn_text = next_btn.inner_text().lower()
                next_btn.click()
                if "submit" in btn_text or "apply" in btn_text:
                    time.sleep(4)
                    return True
                continue
            else:
                break

        system = """You are an AI job application assistant filling web forms.
Be precise. Match dropdown values EXACTLY from the options list.
Return ONLY a valid JSON array, no other text."""

        user = f"""User profile:
```json
{json.dumps(profile, indent=2)}
```

Form fields on this step:
```json
{json.dumps(fields, indent=2)}
```

Fill each field from the profile. Rules:
1. Text inputs: exact string to type
2. Select or Combobox: EXACT text from options list, or common valid option (e.g. Country, State, Gender, Relocation answers)
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
                m = re.search(r'(\[.*?\])', raw, re.DOTALL)
                candidate = m.group(1).strip() if m else raw

            pattern = re.compile(r'"(?:[^"\\]|\\.)*"')
            def repl(match):
                s = match.group(0)
                return s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            candidate = pattern.sub(repl, candidate)
            candidate = re.sub(r'[\x00-\x1F\x7F]', '', candidate)
            candidate = re.sub(r',\s*([\]}])', r'\1', candidate)

            try:
                actions = json.loads(candidate)
            except Exception as e:
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
                    el = page.locator(selector).first
                    if not el.is_visible():
                        continue
                    
                    # Resolve element characteristics
                    tag_name   = el.evaluate("el => el.tagName.toLowerCase()", timeout=2000)
                    input_type = el.evaluate("el => el.type", timeout=2000)
                    role       = el.evaluate("el => el.getAttribute('role') || ''", timeout=2000)
                    
                    # Detect custom combobox type
                    is_combobox = (
                        role == 'combobox' or 
                        el.evaluate("el => el.getAttribute('aria-haspopup') === 'listbox'", timeout=2000) or
                        "dropdown" in el.evaluate("el => (el.getAttribute('data-automation-id') || '').toLowerCase()", timeout=2000) or
                        "select" in el.evaluate("el => (el.getAttribute('data-automation-id') || '').toLowerCase()", timeout=2000)
                    )

                    if tag_name == "select":
                        el.select_option(label=str(val))
                        filled += 1
                    elif is_combobox:
                        # Interact with custom combobox
                        logger.info(f"AI Filler: Interacting with custom combobox '{field_id}' for value '{val}'", site)
                        el.scroll_into_view_if_needed()
                        el.click()
                        time.sleep(1) # wait for listbox/options
                        
                        # Find the options on the page
                        option_selectors = [
                            '[role="option"]',
                            '[data-automation-id*="promptOption"]',
                            '.wd-popup li',
                            '[class*="listbox"] [role="option"]',
                            '.dropdown-menu li',
                            'li'
                        ]
                        
                        options_found = []
                        for opt_sel in option_selectors:
                            try:
                                matches = page.locator(opt_sel).all()
                                visible_matches = [m for m in matches if m.is_visible()]
                                if visible_matches:
                                    options_found = visible_matches
                                    break
                            except Exception:
                                continue
                        
                        clicked_option = False
                        if options_found:
                            best_match = None
                            for opt in options_found:
                                text = opt.inner_text().strip().lower()
                                val_lower = str(val).lower()
                                if text == val_lower or val_lower in text or text in val_lower:
                                    best_match = opt
                                    break
                            
                            if best_match:
                                logger.info(f"AI Filler: Clicking option '{best_match.inner_text().strip()}'", site)
                                best_match.click()
                                clicked_option = True
                                time.sleep(0.5)
                        
                        if not clicked_option:
                            # Try typing inside search input of combobox
                            try:
                                search_input = el.locator('input').first
                                if search_input.is_visible():
                                    search_input.fill(str(val))
                                    time.sleep(0.5)
                                    search_input.press("Enter")
                                    clicked_option = True
                                    time.sleep(0.5)
                            except Exception:
                                pass
                                
                        if not clicked_option:
                            # Try fallback typing directly
                            try:
                                el.fill(str(val))
                                time.sleep(0.5)
                                el.press("Enter")
                                clicked_option = True
                            except Exception:
                                pass
                                
                        if not clicked_option:
                            # Click outside to close dropdown if not selected
                            logger.warn(f"AI Filler: Could not select option '{val}'", site)
                            page.mouse.click(10, 10)
                        else:
                            filled += 1
                            
                    elif input_type in ["checkbox", "radio"] or role in ["checkbox", "radio"]:
                        if str(val).lower() in ["check", "true", "yes", "1"]:
                            try:
                                el.check(force=True)
                            except Exception:
                                try:
                                    el.click(force=True)
                                except Exception:
                                    el.evaluate("el => el.click()")
                            filled += 1
                    elif input_type == "file":
                        pass
                    elif input_type == "number":
                        num_val = ''.join(c for c in str(val) if c.isdigit() or c == '.')
                        if num_val:
                            el.fill(num_val)
                            filled += 1
                    else:
                        el.fill(str(val))
                        filled += 1
                except Exception as ex:
                    pass

            logger.ai(f"Step {step + 1}: Filled {filled}/{len(actions)} fields via AI.", site)

        except Exception as e:
            logger.error(f"AI Form Filler error on step {step + 1}: {e}", site)

        # Click navigation (Next / Continue) or final Submit button
        next_btn = _find_next_or_submit_button(page)
        if not next_btn:
            break

        btn_text = next_btn.inner_text().lower()
        if "submit" in btn_text or "apply" in btn_text:
            logger.info("AI Filler: Clicking final submit button...", site)
            next_btn.click()
            time.sleep(4)
            return True
        else:
            logger.info(f"AI Filler: Moving to next page via '{next_btn.inner_text().strip()}'", site)
            next_btn.click()
            time.sleep(2)

    return True
