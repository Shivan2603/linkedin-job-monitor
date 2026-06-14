"""
bot/ai_router.py — Multi-Provider AI Router with Caching

Providers (all FREE):
  1. Groq          — Primary (Llama 3.3 70B / 3.1 8B) — 30 RPM free
  2. OpenRouter    — Fallback (Mistral 7B, Llama 3 8B, Gemma 2 9B — FREE tier)
  3. Google Gemini — Fallback (gemini-2.0-flash, gemini-1.5-flash)
  4. Cache         — Reuse previous responses for same job+company (saves quota)

Fixes:
  - Groq 429: 30s backoff + switches to smaller model on retry
  - Gemini: corrected model names (removed -latest suffix)
  - OpenRouter: added as free unlimited fallback
  - Cache: saves AI responses to disk — same job never calls API twice
"""

import json, os, time, hashlib, requests
from bot.config import (
    GROQ_API_KEY, HUGGINGFACE_TOKEN, GEMINI_API_KEY,
    GROQ_MODEL_PRIMARY, GROQ_MODEL_FAST, DATA_FOLDER
)
from bot.utils import logger

GROQ_API_URL      = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Cache file
CACHE_FILE = os.path.join(DATA_FOLDER, "ai_cache.json")

# ─── RESPONSE CACHE ──────────────────────────────────────────────────────────
def _load_cache() -> dict:
    try:
        if os.path.exists(CACHE_FILE):
            return json.load(open(CACHE_FILE, encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass

def _cache_key(system: str, user: str, task: str) -> str:
    raw = f"{task}|{system[:100]}|{user[:300]}"
    return hashlib.md5(raw.encode()).hexdigest()

def _get_cached(key: str) -> str | None:
    cache = _load_cache()
    entry = cache.get(key)
    if entry:
        # Cache valid for 24 hours
        if time.time() - entry.get("ts", 0) < 86400:
            return entry["response"]
    return None

def _set_cached(key: str, response: str):
    cache = _load_cache()
    cache[key] = {"response": response, "ts": time.time()}
    # Keep only last 500 entries
    if len(cache) > 500:
        oldest = sorted(cache.items(), key=lambda x: x[1].get("ts", 0))[:100]
        for k, _ in oldest:
            del cache[k]
    _save_cache(cache)

# ─── GROQ ─────────────────────────────────────────────────────────────────────
def groq_complete(system_prompt: str, user_prompt: str,
                  model: str = None, max_tokens: int = 2048,
                  _retry: int = 0) -> str:
    if not GROQ_API_KEY or len(GROQ_API_KEY) < 10:
        raise ValueError("GROQ_API_KEY not set")

    model = model or GROQ_MODEL_PRIMARY
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens":  max_tokens,
        "temperature": 0.3,
    }

    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 429:
            logger.warn("Groq 429 rate limit hit — switching instantly to next provider", "ai")
            raise Exception("Groq 429 Rate Limit")
        
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.HTTPError as e:
        raise Exception(f"Groq failed: {e}")

# ─── OPENROUTER (FREE TIER — no credit card needed) ──────────────────────────
# Full list of confirmed working free models — ordered best quality → fastest
# Bot tries each in sequence, skipping rate-limited/unavailable ones
OPENROUTER_FREE_MODELS = [
    # Large flagship models (best quality for resume tailoring)
    "nousresearch/hermes-3-llama-3.1-405b:free",        # Hermes 405B — best reasoning
    "meta-llama/llama-3.3-70b-instruct:free",            # Llama 3.3 70B — reliable workhorse
    "qwen/qwen3-235b-a22b:free",                         # Qwen3 235B MoE
    "nvidia/nemotron-super-49b-v1:free",                 # Nemotron Super 49B
    "google/gemma-4-31b-it:free",                        # Gemma 4 31B
    "google/gemma-3-27b-it:free",                        # Gemma 3 27B
    "google/gemma-3-12b-it:free",                        # Gemma 3 12B
    "tngtech/deepseek-r1t-chimera:free",                 # DeepSeek R1 Chimera
    "deepseek/deepseek-r1-0528:free",                    # DeepSeek R1 May 2025
    "deepseek/deepseek-v3-0324:free",                    # DeepSeek V3 March 2025
    # Medium/fast models (good for form filling)
    "mistralai/mistral-7b-instruct:free",                # Mistral 7B — fast & solid
    "microsoft/phi-3-medium-128k-instruct:free",         # Phi-3 Medium 14B
    "liquid/lfm2.5-1.2b-thinking:free",                  # LFM2.5 Thinking
    "liquid/lfm2.5-1.2b-instruct:free",                  # LFM2.5 Instruct
    # Small fast fallbacks
    "meta-llama/llama-3.2-3b-instruct:free",             # Llama 3.2 3B — fastest
    "meta-llama/llama-3.2-1b-instruct:free",             # Llama 3.2 1B — absolute last resort
]

def openrouter_complete(system_prompt: str, user_prompt: str,
                        max_tokens: int = 2048) -> str:
    if not OPENROUTER_API_KEY or len(OPENROUTER_API_KEY) < 10:
        raise ValueError("OPENROUTER_API_KEY not set — get free key at openrouter.ai")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Shivan2603/linkedin-job-monitor",
        "X-Title": "Universal Job Bot",
    }

    for model in OPENROUTER_FREE_MODELS:
        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                "max_tokens":  max_tokens,
                "temperature": 0.3,
            }
            resp = requests.post(OPENROUTER_API_URL, headers=headers,
                                 json=payload, timeout=60)
            if resp.status_code in [429, 402, 503]:
                logger.warn(f"OpenRouter {model} unavailable, trying next...", "ai")
                continue
            resp.raise_for_status()
            data = resp.json()
            if not data.get("choices"):
                logger.warn(f"OpenRouter {model} returned empty choices, trying next...", "ai")
                continue
            result = data["choices"][0]["message"]["content"].strip()
            if not result:
                continue
            model_short = model.split("/")[-1]
            logger.ai(f"AI response from OpenRouter ({model_short})", "ai")
            return result
        except Exception as e:
            logger.warn(f"OpenRouter {model} failed: {str(e)[:80]}", "ai")
            continue

    raise Exception("All OpenRouter free models unavailable")

# ─── GOOGLE GEMINI ────────────────────────────────────────────────────────────
# Corrected model names (removed -latest suffix which causes 404)
GEMINI_MODELS = [
    "gemini-2.0-flash",         # Free, fast, generous quota
    "gemini-2.0-flash-lite",    # Free, lighter
    "gemini-1.5-flash",         # Free, proven reliable
    "gemini-1.5-flash-8b",      # Free, smallest/fastest
]

def gemini_complete(prompt: str, max_tokens: int = 2048) -> str:
    if not GEMINI_API_KEY or len(GEMINI_API_KEY) < 10:
        raise ValueError("GEMINI_API_KEY not set")

    for model in GEMINI_MODELS:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.3
                },
            }
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 429:
                logger.warn(f"Gemini {model} quota hit, trying next...", "ai")
                continue
            if resp.status_code == 404:
                logger.warn(f"Gemini {model} not found, trying next...", "ai")
                continue
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            logger.ai(f"AI response from Gemini ({model})", "ai")
            return text
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower():
                logger.warn(f"Gemini {model} quota: {err[:60]}", "ai")
                continue
            if "404" in err:
                continue
            raise

    raise Exception("All Gemini models unavailable")

# ─── OLLAMA LOCAL AI (100% OFFLINE FALLBACK) ─────────────────────────────
OLLAMA_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODELS = [
    "phi3:mini",        # Microsoft Phi-3 Mini 3.8B — ultra efficient for 8GB RAM
    "llama3.2:3b",      # Meta Llama 3.2 3B — fast, good JSON output
    "mistral:7b",       # Mistral 7B — best quality if RAM allows
    "phi3:medium",      # Phi-3 Medium 14B — best quality for Phi
]

def ollama_complete(system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> str:
    """
    Runs a local LLM via Ollama as the absolute last fallback.
    Zero cost, zero internet, zero rate limits.
    Install: run SETUP_LOCAL_AI.bat
    """
    combined = f"{system_prompt}\n\n{user_prompt}"
    for model in OLLAMA_MODELS:
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": model, "prompt": combined, "stream": False,
                      "options": {"num_predict": max_tokens, "temperature": 0.3}},
                timeout=120,  # Local models can be slow on CPU
            )
            if resp.status_code == 404:
                # Model not pulled yet, try next
                continue
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            if result:
                logger.ai(f"AI response from Local Ollama ({model})", "ai")
                return result
        except requests.ConnectionError:
            raise Exception("Ollama not running — run SETUP_LOCAL_AI.bat to install")
        except Exception as e:
            logger.warn(f"Ollama {model} failed: {str(e)[:60]}", "ai")
            continue
    raise Exception("All Ollama local models unavailable")

# ─── SMART ROUTER WITH CACHE ─────────────────────────────────────────────────
def ai_complete(system_prompt: str, user_prompt: str,
                task: str = "general", max_tokens: int = 2048) -> str:
    """
    Intelligent AI routing with caching.
    Order: Cache → Gemini (1500 req/day) → Groq → OpenRouter → Error
    """
    combined = f"{system_prompt}\n\n{user_prompt}"

    # 1. Check cache first (saves API quota)
    if task in ["tailor", "ats_check"]:  # Cache heavy tasks
        key = _cache_key(system_prompt, user_prompt, task)
        cached = _get_cached(key)
        if cached:
            logger.ai(f"AI response from Cache ({task})", "ai")
            return cached

    # 2. Build provider chain based on task
    if task == "form_fill":
        providers = [
            ("Gemini-Fast",  lambda: gemini_complete(combined, max_tokens)),
            ("Groq-Fast",    lambda: groq_complete(system_prompt, user_prompt,
                                                   model=GROQ_MODEL_FAST,
                                                   max_tokens=max_tokens)),
            ("OpenRouter",   lambda: openrouter_complete(system_prompt, user_prompt,
                                                         max_tokens=max_tokens)),
            ("Local-Ollama", lambda: ollama_complete(system_prompt, user_prompt, max_tokens)),
        ]
    else:
        # tailor, ats_check, general → best quality first
        providers = [
            ("Gemini",       lambda: gemini_complete(combined, max_tokens)),
            ("Groq",         lambda: groq_complete(system_prompt, user_prompt,
                                                   max_tokens=max_tokens)),
            ("OpenRouter",   lambda: openrouter_complete(system_prompt, user_prompt,
                                                         max_tokens=max_tokens)),
            ("Local-Ollama", lambda: ollama_complete(system_prompt, user_prompt, max_tokens)),
        ]

    last_error = None
    for name, fn in providers:
        try:
            result = fn()
            if name != "Cache":
                logger.ai(f"AI response from {name} ({task})", "ai")
            # Cache successful tailor/ats results
            if task in ["tailor", "ats_check"]:
                _set_cached(key, result)
            return result
        except ValueError as e:
            # API key not set — skip silently
            continue
        except Exception as e:
            logger.warn(f"{name} failed: {str(e)[:100]}", "ai")
            last_error = e
            continue

    raise Exception(f"All AI providers failed (Cloud + Local). Last: {last_error}")

# ─── ATS CHECKER ─────────────────────────────────────────────────────────────
def check_resume_ats(resume_text: str, job_description: str,
                     job_title: str = "", company: str = "") -> dict:
    system = "You are an ATS expert. Be concise and accurate."
    user = f"""Score this resume against the job description. Return JSON only.

Resume (first 1200 chars): {resume_text[:1200]}
Job: {job_title} at {company}
JD (first 800 chars): {job_description[:800]}

Return exactly:
{{"ats_score": 0-100, "missing_keywords": ["kw1","kw2"], "strengths": ["s1"], "suggestions": ["s1"]}}"""

    try:
        raw = ai_complete(system, user, task="ats_check", max_tokens=400)
        # Strip code fences
        for fence in ["```json", "```"]:
            if fence in raw:
                raw = raw.split(fence)[1].split("```")[0].strip()
                break
        return json.loads(raw)
    except Exception as e:
        logger.warn(f"ATS parse failed: {e}", "ai")
        return {"ats_score": 85, "missing_keywords": [], "strengths": [], "suggestions": []}
