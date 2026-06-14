"""
ai_resume.py — Google Gemini 2.0 Flash powered resume tailoring (FREE)
Reads base .docx, tailors per job description, saves to today's folder.
"""
import os, re, json
from docx import Document
import google.generativeai as genai
from bot.config import GEMINI_API_KEY, GEMINI_MODEL, BASE_RESUME_DOCX, TAILORED_TODAY
from bot.utils import logger

# Configure Gemini client
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

TAILOR_SYSTEM_PROMPT = """You are an expert resume writer and ATS optimization specialist.
Your job is to tailor a candidate's resume to maximize match with a specific job description.

Rules:
1. ONLY rewrite: Professional Summary, Skills section, and key bullet points in experience
2. NEVER fabricate experience, companies, or degrees — only reframe existing content
3. Inject job-specific keywords naturally into the summary and skills
4. Keep the same structure and formatting — only change text content
5. Output the FULL rewritten resume content section-by-section in JSON format
6. Target ATS match score: 88-97%
"""

def extract_resume_text(docx_path: str) -> str:
    """Extract plain text from .docx"""
    doc = Document(docx_path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

def tailor_resume(job_title: str, company: str, job_description: str, site: str = "ai") -> dict:
    """
    Use Gemini 2.0 Flash (FREE) to tailor the base resume for a specific job.
    Returns: { "resume_path": str, "match_score": int, "tailored_sections": dict }
    """
    logger.ai(f"Tailoring resume for {company} - {job_title}", site=site)

    base_text = extract_resume_text(BASE_RESUME_DOCX)

    if not GEMINI_API_KEY or "PASTE" in GEMINI_API_KEY or len(GEMINI_API_KEY) < 10:
        logger.warn(f"No Gemini API Key — using base resume for {company}", site=site)
        safe_company = re.sub(r'[^\w\-]', '_', company)[:20]
        safe_role    = re.sub(r'[^\w\-]', '_', job_title)[:20]
        filename     = f"{safe_company}_{safe_role}_base.docx"
        out_path     = os.path.join(TAILORED_TODAY, filename)
        doc = Document(BASE_RESUME_DOCX)
        doc.save(out_path)
        return {"resume_path": out_path, "match_score": 85, "tailored": {}}

    prompt = f"""{TAILOR_SYSTEM_PROMPT}

Here is the candidate's current resume:

<resume>
{base_text}
</resume>

Here is the job description for {job_title} at {company}:

<job_description>
{job_description[:3000]}
</job_description>

Please tailor this resume for this specific role.
Return a JSON object with these keys:
- "professional_summary": rewritten 3-4 line summary targeting this role
- "key_skills": list of 12-16 relevant skills matching the JD keywords
- "experience_bullets": dict of {{company_name: [bullet1, bullet2, ...]}} with improved bullets
- "match_score": integer 88-97 (estimated ATS match percentage)
- "keywords_added": list of important keywords you injected

Return ONLY valid JSON, no other text."""

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Strip markdown code fences if present
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        tailored = json.loads(raw)
        match_score = tailored.get("match_score", 90)

        # Build tailored .docx
        doc = Document(BASE_RESUME_DOCX)
        _apply_tailoring(doc, tailored)

        safe_company = re.sub(r'[^\w\-]', '_', company)[:20]
        safe_role    = re.sub(r'[^\w\-]', '_', job_title)[:20]
        filename     = f"{safe_company}_{safe_role}_{match_score}pct.docx"
        out_path     = os.path.join(TAILORED_TODAY, filename)
        doc.save(out_path)

        logger.ai(f"Resume saved: {filename} ({match_score}% match)", site=site)
        return {"resume_path": out_path, "match_score": match_score, "tailored": tailored}

    except Exception as e:
        logger.error(f"Gemini resume tailor failed: {e}", site=site)
        # Fallback to base resume
        safe_company = re.sub(r'[^\w\-]', '_', company)[:20]
        safe_role    = re.sub(r'[^\w\-]', '_', job_title)[:20]
        out_path     = os.path.join(TAILORED_TODAY, f"{safe_company}_{safe_role}_base.docx")
        doc = Document(BASE_RESUME_DOCX)
        doc.save(out_path)
        return {"resume_path": out_path, "match_score": 85, "tailored": {}}


def _apply_tailoring(doc: Document, tailored: dict):
    """Inject tailored content into the document paragraphs"""
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
                skills_text = " • ".join(tailored["key_skills"])
                _replace_run_text(para, skills_text)
                skills_done = False
            continue


def _replace_run_text(para, new_text: str):
    """Replace paragraph text while preserving formatting of first run"""
    if para.runs:
        for i, run in enumerate(para.runs):
            if i == 0:
                run.text = new_text
            else:
                run.text = ""
    else:
        para.text = new_text
