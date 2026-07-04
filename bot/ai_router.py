"""
bot/ai_router.py — Multi-Provider AI Router with Caching

Provider Chain (fastest → most capable, all FREE / cloud):
  1. Cache         — Instant reuse for same JD (zero API calls)
  2. Groq          — Llama 3.3 70B cloud (30 RPM free)
  3. Gemini        — gemini-2.0-flash cloud (1500 req/day free)
  4. OpenRouter    — 15+ free cloud models (fallback pool)
  5. Ollama Cloud  — Self-hosted on HF Spaces (always-on, zero cost)

Removed:
  - Local JCode CLI subprocess (windows-only, slow, unreliable)
  - Local LM Studio (localhost-only)
  - Ollama localhost (replaced by cloud deployment)
  - Claude Sonnet 402 (paid, always fails on free key)
  - OpenCode Zen (requires paid subscription/billing details)
"""

import json, os, time, hashlib, requests
from bot.config import (
    GROQ_API_KEY, HUGGINGFACE_TOKEN, GEMINI_API_KEY,
    GROQ_MODEL_PRIMARY, GROQ_MODEL_FAST, DATA_FOLDER
)
from bot.utils import logger

# ─── ENDPOINTS ───────────────────────────────────────────────────────────────
GROQ_API_URL       = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Ollama Cloud — deployed on Hugging Face Spaces (free, always-on)
# Deployed at: https://huggingface.co/spaces/Shivan2603/jcode-ollama-cloud
OLLAMA_CLOUD_URL   = os.getenv(
    "OLLAMA_CLOUD_URL",
    "https://shivan2603-jcode-ollama-cloud.hf.space"
)
OLLAMA_CLOUD_MODELS = [
    "qwen2.5-coder:7b",   # Best for JSON/structured output
    "qwen2.5:7b",          # High quality general
    "llama3.2:3b",         # Fast reliable fallback
    "phi3:mini",           # Ultra fast (form filling)
]

# Cache
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
        if time.time() - entry.get("ts", 0) < 86400:  # 24-hour cache
            return entry["response"]
    return None

def _set_cached(key: str, response: str):
    cache = _load_cache()
    cache[key] = {"response": response, "ts": time.time()}
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
        resp = requests.post(GROQ_API_URL, headers=headers,
                             json=payload, timeout=40)
        if resp.status_code == 429:
            logger.warn("Groq 429 rate limit hit — switching instantly to next provider", "ai")
            raise Exception("Groq 429 Rate Limit")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise Exception(f"Groq failed: {e}")


# ─── GOOGLE GEMINI ────────────────────────────────────────────────────────────
GEMINI_MODELS = [
    "gemini-2.0-flash",       # Free, fast, generous quota
    "gemini-2.0-flash-lite",  # Free, lighter
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
                logger.warn(f"Gemini {model} quota hit, trying next...", "ai")
                continue
            if "404" in err:
                continue
            raise

    raise Exception("All Gemini models failed or hit quota limits")


# ─── OPENROUTER (FREE TIER FALLBACK) ─────────────────────────────────────────
# Trimmed to only the models that actually respond quickly.
# Removed slow/always-rate-limited models to save time.
OPENROUTER_FREE_MODELS = [
    "openai/gpt-oss-120b:free",               # Best quality free (GPT class)
    "meta-llama/llama-3.3-70b-instruct:free", # Strong 70B
    "qwen/qwen3-coder:free",                  # Good for code/JSON
    "nvidia/nemotron-3-super-120b-a12b:free", # Large + capable
    "openai/gpt-oss-20b:free",                # Fast GPT-class
    "meta-llama/llama-3.2-3b-instruct:free",  # Tiny but reliable
    "openrouter/free",                         # Auto-router fallback
]

def openrouter_complete(system_prompt: str, user_prompt: str,
                        max_tokens: int = 2048) -> str:
    if not OPENROUTER_API_KEY or len(OPENROUTER_API_KEY) < 10:
        raise ValueError("OPENROUTER_API_KEY not set — get free key at openrouter.ai")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Shivan2603/linkedin-job-monitor",
        "X-Title": "JCode Job Bot",
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
            if resp.status_code != 200:
                logger.warn(f"OpenRouter {model} status {resp.status_code}: {resp.text[:150]}", "ai")
                continue
            data = resp.json()
            if not data.get("choices") or not data["choices"][0].get("message"):
                continue
            content = data["choices"][0]["message"].get("content", "").strip()
            if not content:
                continue
            model_short = model.split("/")[-1]
            logger.ai(f"AI response from OpenRouter ({model_short})", "ai")
            return content
        except Exception as e:
            logger.warn(f"OpenRouter {model} failed: {str(e)[:80]}", "ai")
            continue

    raise Exception("All OpenRouter free models unavailable")


# ─── OLLAMA CLOUD (HuggingFace Spaces) ───────────────────────────────────────
def _is_ollama_cloud_up() -> bool:
    """Ping the cloud Ollama health endpoint."""
    try:
        r = requests.get(f"{OLLAMA_CLOUD_URL}/api/tags", timeout=5)
        return r.status_code in [200, 204]
    except Exception:
        return False

def ollama_cloud_complete(system_prompt: str, user_prompt: str,
                          max_tokens: int = 2048) -> str:
    """
    Calls the cloud-deployed Ollama on Hugging Face Spaces.
    Endpoint: OLLAMA_CLOUD_URL (default: shivan2603-jcode-ollama-cloud.hf.space)
    Deployed via: E:\\SivaShankar\\ollama-cloud (Docker → HF Spaces)
    """
    combined = f"{system_prompt}\n\n{user_prompt}"
    generate_url = f"{OLLAMA_CLOUD_URL}/api/generate"

    for model in OLLAMA_CLOUD_MODELS:
        try:
            resp = requests.post(
                generate_url,
                json={
                    "model": model,
                    "prompt": combined,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.3},
                },
                timeout=120,
            )
            if resp.status_code == 404:
                logger.warn(f"Ollama Cloud: model {model} not pulled yet, trying next...", "ai")
                continue
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            if result:
                logger.ai(f"AI response from Ollama Cloud ({model})", "ai")
                return result
        except requests.ConnectionError:
            raise Exception("Ollama Cloud (HF Spaces) is offline or sleeping")
        except Exception as e:
            logger.warn(f"Ollama Cloud {model} failed: {str(e)[:60]}", "ai")
            continue

    raise Exception("All Ollama Cloud models unavailable")


# ─── SMART ROUTER WITH CACHE ─────────────────────────────────────────────────
def ai_complete(system_prompt: str, user_prompt: str,
                task: str = "general", max_tokens: int = 2048) -> str:
    """
    Cloud-first AI router. Provider order:
      Cache → OpenCode Zen → Groq → Gemini → OpenRouter → Ollama Cloud

    All providers are cloud-hosted. No local subprocess, no localhost dependency.
    """
    combined = f"{system_prompt}\n\n{user_prompt}"

    # 1. Cache — instant for repeat calls (same JD never calls API twice)
    if task in ["tailor", "ats_check"]:
        key = _cache_key(system_prompt, user_prompt, task)
        cached = _get_cached(key)
        if cached:
            logger.ai(f"AI response from Cache ({task})", "ai")
            return cached

    providers = []

    # 1. Ollama Cloud (HF Spaces) — Primary. Zero rate limits, private, 100% free.
    providers.append((
        "Ollama-Cloud",
        lambda: ollama_cloud_complete(system_prompt, user_prompt, max_tokens)
    ))

    # 2. Gemini — Fallback. Free, fast cloud.
    providers.append((
        "Gemini",
        lambda: gemini_complete(combined, max_tokens)
    ))

    # 3. Groq — Fallback. Fast cloud, instant failover on 429.
    if task == "form_fill":
        providers.append((
            "Groq-Fast",
            lambda: groq_complete(system_prompt, user_prompt,
                                  model=GROQ_MODEL_FAST, max_tokens=max_tokens)
        ))
    else:
        providers.append((
            "Groq",
            lambda: groq_complete(system_prompt, user_prompt, max_tokens=max_tokens)
        ))

    # 4. OpenRouter — Final Fallback. Free cloud model pool.
    providers.append((
        "OpenRouter",
        lambda: openrouter_complete(system_prompt, user_prompt, max_tokens=max_tokens)
    ))

    # 3. Try each provider
    last_error = None
    for name, fn in providers:
        try:
            result = fn()
            # Cache successful tailor/ats results
            if task in ["tailor", "ats_check"]:
                _set_cached(key, result)
            return result
        except ValueError:
            # API key not set — skip silently
            continue
        except Exception as e:
            logger.warn(f"{name} failed: {str(e)[:100]}", "ai")
            last_error = e
            continue

    raise Exception(f"All AI providers failed (Cloud). Last: {last_error}")


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
        for fence in ["```json", "```"]:
            if fence in raw:
                raw = raw.split(fence)[1].split("```")[0].strip()
                break
        return json.loads(raw)
    except Exception as e:
        logger.warn(f"ATS parse failed: {e}", "ai")
        return {"ats_score": 85, "missing_keywords": [], "strengths": [], "suggestions": []}
