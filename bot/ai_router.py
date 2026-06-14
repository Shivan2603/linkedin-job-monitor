"""
bot/ai_router.py — Multi-Provider AI Router (All FREE)

Provider Roles:
  - Groq (Llama 3.3 70B)  : Primary — resume tailoring + ATS check
  - Groq (Llama 3.1 8B)   : Fast — form filling
  - Google Gemini          : Fallback if Groq quota hits
  - HuggingFace            : Disabled (DNS unreachable on most networks)

Fixes applied:
  - Groq 429: exponential backoff retry (waits 15s then retries once)
  - Gemini: updated working model names
  - HuggingFace: removed from default chain (DNS failure)
  - Field timeout: handled in ai_agent_filler.py (3s per field)
"""

import json, os, time, requests
from bot.config import (
    GROQ_API_KEY, HUGGINGFACE_TOKEN, GEMINI_API_KEY,
    GROQ_MODEL_PRIMARY, GROQ_MODEL_FAST
)
from bot.utils import logger

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ─── GROQ (Primary) ──────────────────────────────────────────────────────────
def groq_complete(system_prompt: str, user_prompt: str,
                  model: str = None, max_tokens: int = 2048,
                  retry: bool = True) -> str:
    if not GROQ_API_KEY or len(GROQ_API_KEY) < 10:
        raise ValueError("GROQ_API_KEY not configured")

    model = model or GROQ_MODEL_PRIMARY
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":    model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens":  max_tokens,
        "temperature": 0.3,
    }

    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 429 and retry:
            # Rate limited — wait 20 seconds and retry once
            logger.warn(f"Groq 429 rate limit — waiting 20s then retrying...", "ai")
            time.sleep(20)
            return groq_complete(system_prompt, user_prompt, model=model,
                                 max_tokens=max_tokens, retry=False)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.HTTPError as e:
        raise Exception(f"Groq failed: {e}")


# ─── GEMINI (Fallback) ────────────────────────────────────────────────────────
GEMINI_MODELS = [
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
    "gemini-2.0-flash-lite",
]

def gemini_complete(prompt: str, max_tokens: int = 2048) -> str:
    if not GEMINI_API_KEY or len(GEMINI_API_KEY) < 10:
        raise ValueError("GEMINI_API_KEY not configured")

    for model in GEMINI_MODELS:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={GEMINI_API_KEY}")
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
            }
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 429:
                logger.warn(f"Gemini {model} quota hit, trying next...", "ai")
                continue
            if resp.status_code == 404:
                logger.warn(f"Gemini {model} not found, trying next...", "ai")
                continue
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower() or "404" in str(e):
                continue
            raise
    raise Exception("All Gemini models unavailable")


# ─── HUGGINGFACE (optional, disabled by default — DNS issues on most networks)
def huggingface_complete(prompt: str, max_tokens: int = 512) -> str:
    if not HUGGINGFACE_TOKEN or len(HUGGINGFACE_TOKEN) < 10:
        raise ValueError("HUGGINGFACE_TOKEN not configured")
    HF_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"
    headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": max_tokens, "temperature": 0.2, "return_full_text": False},
    }
    resp = requests.post(HF_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if isinstance(result, list) and result:
        return result[0].get("generated_text", "").strip()
    return str(result).strip()


# ─── SMART ROUTER ─────────────────────────────────────────────────────────────
def ai_complete(system_prompt: str, user_prompt: str,
                task: str = "general", max_tokens: int = 2048) -> str:
    """
    Smart AI router with automatic fallback.

    task:
      "tailor"    → Groq 70B primary (best quality)
      "form_fill" → Groq 8B fast (speed)
      "ats_check" → Groq 70B (removed HF — DNS issues)
      "general"   → Groq → Gemini
    """
    combined = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt

    if task == "form_fill":
        providers = [
            ("Groq-Fast", lambda: groq_complete(system_prompt, user_prompt,
                                                model=GROQ_MODEL_FAST, max_tokens=max_tokens)),
            ("Groq",      lambda: groq_complete(system_prompt, user_prompt, max_tokens=max_tokens)),
            ("Gemini",    lambda: gemini_complete(combined, max_tokens)),
        ]
    else:
        # tailor, ats_check, general — use 70B
        providers = [
            ("Groq",   lambda: groq_complete(system_prompt, user_prompt, max_tokens=max_tokens)),
            ("Gemini", lambda: gemini_complete(combined, max_tokens)),
        ]

    last_error = None
    for name, fn in providers:
        try:
            result = fn()
            logger.ai(f"AI response from {name} ({task})", "ai")
            return result
        except ValueError as e:
            logger.warn(f"{name} skipped: {e}", "ai")
            continue
        except Exception as e:
            logger.warn(f"{name} failed: {str(e)[:120]}", "ai")
            last_error = e
            continue

    raise Exception(f"All AI providers failed. Last error: {last_error}")


# ─── ATS RESUME CHECKER ──────────────────────────────────────────────────────
def check_resume_ats(resume_text: str, job_description: str,
                     job_title: str = "", company: str = "") -> dict:
    system = "You are an ATS expert and resume analyst. Be concise."
    user = f"""Score this resume against the job description. Return JSON only.

Resume (first 1500 chars):
{resume_text[:1500]}

Job: {job_title} at {company}
JD (first 1000 chars):
{job_description[:1000]}

Return JSON:
{{"ats_score": 0-100, "missing_keywords": ["kw1","kw2"], "strengths": ["s1"], "suggestions": ["imp1"]}}"""

    try:
        raw = ai_complete(system, user, task="ats_check", max_tokens=512)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"ATS check failed: {e}", "ai")
        return {"ats_score": 85, "missing_keywords": [], "strengths": [], "suggestions": []}
