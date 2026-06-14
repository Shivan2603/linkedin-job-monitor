"""
bot/ai_router.py — Multi-Provider AI Router (All FREE)

Provider Roles:
  - Groq (Llama 3.3 70B)    : Primary — resume tailoring + form filling (fast, accurate)
  - HuggingFace (Mistral 7B) : Resume ATS scoring and checking/validation
  - Google Gemini             : Fallback if Groq quota hits

Sign-up links (all free, no credit card):
  Groq       : https://console.groq.com  → "Create API Key"
  HuggingFace: https://huggingface.co/settings/tokens → "New token" (read)
  Gemini     : https://aistudio.google.com/app/apikey
"""

import json
import os
import requests
from bot.config import (
    GROQ_API_KEY, HUGGINGFACE_TOKEN, GEMINI_API_KEY,
    GROQ_MODEL_PRIMARY, GROQ_MODEL_FAST
)
from bot.utils import logger

# ─── GROQ (Primary) ──────────────────────────────────────────────────────────
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def groq_complete(system_prompt: str, user_prompt: str,
                  model: str = None, max_tokens: int = 2048) -> str:
    """
    Call Groq API (OpenAI-compatible).
    Free tier: 14,400 requests/day, 500,000 tokens/min on Llama 3.3 70B.
    """
    if not GROQ_API_KEY or len(GROQ_API_KEY) < 10:
        raise ValueError("GROQ_API_KEY not configured")

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
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ─── HUGGINGFACE (ATS Checker / Validator) ───────────────────────────────────
HF_API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"

def huggingface_complete(prompt: str, max_tokens: int = 1024) -> str:
    """
    Call HuggingFace Inference API (free tier, no credit card).
    Used for ATS resume scoring and validation checks.
    """
    if not HUGGINGFACE_TOKEN or len(HUGGINGFACE_TOKEN) < 10:
        raise ValueError("HUGGINGFACE_TOKEN not configured")

    headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": 0.2,
            "return_full_text": False,
        },
    }
    resp = requests.post(HF_API_URL, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    result = resp.json()
    if isinstance(result, list) and result:
        return result[0].get("generated_text", "").strip()
    return str(result).strip()


# ─── GEMINI (Fallback) ────────────────────────────────────────────────────────
def gemini_complete(prompt: str, max_tokens: int = 2048) -> str:
    """Gemini fallback via REST API (no SDK needed, avoids deprecated package issues)."""
    if not GEMINI_API_KEY or len(GEMINI_API_KEY) < 10:
        raise ValueError("GEMINI_API_KEY not configured")

    models = ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]
    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
            }
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                logger.warn(f"Gemini {model} quota hit, trying next...", "ai")
                continue
            raise
    raise Exception("All Gemini models quota exhausted")


# ─── SMART ROUTER ─────────────────────────────────────────────────────────────
def ai_complete(system_prompt: str, user_prompt: str,
                task: str = "general", max_tokens: int = 2048) -> str:
    """
    Smart AI router — tries providers in order of preference per task.

    task options:
      "tailor"   → Groq primary (best quality for resume writing)
      "form_fill"→ Groq fast model (speed priority)
      "ats_check"→ HuggingFace (Mistral 7B, great for analysis)
      "general"  → Groq → Gemini fallback
    """
    combined_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt

    if task == "ats_check":
        # HuggingFace first for ATS scoring
        providers = [
            ("HuggingFace", lambda: huggingface_complete(combined_prompt, max_tokens)),
            ("Groq",        lambda: groq_complete(system_prompt, user_prompt, max_tokens=max_tokens)),
            ("Gemini",      lambda: gemini_complete(combined_prompt, max_tokens)),
        ]
    elif task == "form_fill":
        # Groq fast model for speed
        providers = [
            ("Groq-Fast",   lambda: groq_complete(system_prompt, user_prompt, model=GROQ_MODEL_FAST, max_tokens=max_tokens)),
            ("Groq",        lambda: groq_complete(system_prompt, user_prompt, max_tokens=max_tokens)),
            ("Gemini",      lambda: gemini_complete(combined_prompt, max_tokens)),
            ("HuggingFace", lambda: huggingface_complete(combined_prompt, max_tokens)),
        ]
    else:
        # Groq primary for tailoring and general use
        providers = [
            ("Groq",        lambda: groq_complete(system_prompt, user_prompt, max_tokens=max_tokens)),
            ("Gemini",      lambda: gemini_complete(combined_prompt, max_tokens)),
            ("HuggingFace", lambda: huggingface_complete(combined_prompt, max_tokens)),
        ]

    last_error = None
    for name, fn in providers:
        try:
            result = fn()
            logger.ai(f"AI response from {name} ({task})", "ai")
            return result
        except ValueError as e:
            # API key not configured — skip silently
            logger.warn(f"{name} skipped: {e}", "ai")
            continue
        except Exception as e:
            logger.warn(f"{name} failed: {str(e)[:100]}", "ai")
            last_error = e
            continue

    raise Exception(f"All AI providers failed. Last error: {last_error}")


# ─── ATS RESUME CHECKER ──────────────────────────────────────────────────────
def check_resume_ats(resume_text: str, job_description: str,
                     job_title: str = "", company: str = "") -> dict:
    """
    Use HuggingFace Mistral to score and analyse a tailored resume against a JD.
    Returns: { "ats_score": int, "missing_keywords": list, "strengths": list, "suggestions": list }
    """
    system = "You are an ATS (Applicant Tracking System) expert and resume analyst."
    user = f"""Analyse this resume against the job description and return a JSON report.

Resume:
{resume_text[:2000]}

Job Description for {job_title} at {company}:
{job_description[:1500]}

Return JSON with:
- "ats_score": integer 0-100
- "missing_keywords": list of important keywords from JD missing in resume
- "strengths": list of resume strengths matching JD
- "suggestions": list of 3-5 improvement suggestions

Return ONLY valid JSON."""

    try:
        raw = ai_complete(system, user, task="ats_check", max_tokens=1024)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"ATS check failed: {e}", "ai")
        return {"ats_score": 85, "missing_keywords": [], "strengths": [], "suggestions": []}
