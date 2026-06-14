"""
ai_resume.py — Multi-AI resume tailoring using ai_router.py
Primary: Groq Llama 3.3 70B | ATS Check: HuggingFace Mistral | Fallback: Gemini
"""
import os, re, json
from docx import Document
from bot.config import GROQ_API_KEY, BASE_RESUME_DOCX, TAILORED_TODAY
from bot.utils import logger
from bot.ai_router import ai_complete, check_resume_ats

TAILOR_SYSTEM = """You are an expert resume writer and ATS optimization specialist.
Rules:
1. ONLY rewrite: Professional Summary, Skills section, and key bullet points in experience
2. NEVER fabricate experience, companies, or degrees — only reframe existing content
3. Inject job-specific keywords naturally into the summary and skills
4. Keep the same structure — only change text content
5. Target ATS match score: 88-97%
Return ONLY valid JSON, no other text."""


def extract_resume_text(docx_path: str) -> str:
    doc = Document(docx_path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])


def tailor_resume(job_title: str, company: str, job_description: str, site: str = "ai") -> dict:
    """
    Tailor the base resume for a specific job using the best available free AI.
    Returns: { "resume_path": str, "match_score": int, "ats_report": dict }
    """
    logger.ai(f"Tailoring resume for {company} - {job_title}", site=site)

    safe_company = re.sub(r'[^\w\-]', '_', company)[:20]
    safe_role    = re.sub(r'[^\w\-]', '_', job_title)[:20]
    base_text    = extract_resume_text(BASE_RESUME_DOCX)

    user_prompt = f"""Tailor this resume for {job_title} at {company}:

<resume>
{base_text}
</resume>

<job_description>
{job_description[:3000]}
</job_description>

Return JSON with:
- "professional_summary": rewritten 3-4 line summary targeting this role
- "key_skills": list of 12-16 skills matching JD keywords
- "experience_bullets": dict {{company_name: [bullet1, bullet2, ...]}} with improved bullets
- "match_score": integer 88-97 (estimated ATS match %)
- "keywords_added": list of keywords injected"""

    try:
        raw = ai_complete(TAILOR_SYSTEM, user_prompt, task="tailor", max_tokens=2048)

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        tailored    = json.loads(raw)
        match_score = tailored.get("match_score", 90)

        # Build tailored .docx
        doc = Document(BASE_RESUME_DOCX)
        _apply_tailoring(doc, tailored)

        filename = f"Siva_Shankar_{safe_role}_{safe_company}_Resume.docx"
        out_path = os.path.join(TAILORED_TODAY, filename)
        doc.save(out_path)
        logger.ai(f"Resume saved: {filename} ({match_score}% match)", site=site)

        # Run ATS check on the tailored resume using HuggingFace
        try:
            tailored_text = extract_resume_text(out_path)
            ats_report = check_resume_ats(tailored_text, job_description, job_title, company)
            logger.ai(f"ATS Check: {ats_report.get('ats_score', '?')}% — "
                      f"Missing: {ats_report.get('missing_keywords', [])[:3]}", site=site)
        except Exception:
            ats_report = {}

        return {
            "resume_path": out_path,
            "match_score": match_score,
            "tailored":    tailored,
            "ats_report":  ats_report,
        }

    except Exception as e:
        logger.error(f"Resume tailoring failed: {e}", site=site)
        out_path = os.path.join(TAILORED_TODAY, f"Siva_Shankar_{safe_role}_{safe_company}_Resume.docx")
        doc = Document(BASE_RESUME_DOCX)
        doc.save(out_path)
        return {"resume_path": out_path, "match_score": 85, "tailored": {}, "ats_report": {}}


def _apply_tailoring(doc: Document, tailored: dict):
    summary_done = False
    skills_done  = False
    for para in doc.paragraphs:
        text = para.text.strip().lower()
        if not summary_done and any(k in text for k in ["summary", "objective", "profile"]):
            summary_done = True
        if summary_done and para.text.strip() and not any(
            k in para.text.lower() for k in ["summary", "objective", "profile", "skills", "experience"]
        ):
            if tailored.get("professional_summary"):
                _replace_run_text(para, tailored["professional_summary"])
                summary_done = False
            continue
        if not skills_done and "skill" in text:
            skills_done = True
        if skills_done and para.text.strip() and "skill" not in para.text.lower():
            if tailored.get("key_skills"):
                _replace_run_text(para, " | ".join(tailored["key_skills"]))
                skills_done = False
            continue


def _replace_run_text(para, new_text: str):
    if para.runs:
        for i, run in enumerate(para.runs):
            run.text = new_text if i == 0 else ""
    else:
        para.text = new_text
