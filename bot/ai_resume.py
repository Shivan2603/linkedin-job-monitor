"""
ai_resume.py — Multi-AI resume tailoring using ai_router.py with Self-Correction Loop
Primary: Groq Llama 3.3 70B | ATS Check: HuggingFace Mistral | Fallback: Gemini
"""
import os, re, json
from docx import Document
from bot.config import GROQ_API_KEY, BASE_RESUME_DOCX, TAILORED_TODAY
from bot.utils import logger
from bot.ai_router import ai_complete, check_resume_ats

TAILOR_SYSTEM = """You are an expert resume writer and ATS optimization specialist.
Rules:
1. ONLY rewrite: Professional Summary, Skills section
2. NEVER fabricate experience, companies, or degrees — only reframe existing content
3. Inject job-specific keywords naturally into the summary and skills
4. Highlight Rust and Cargo skills where appropriate, referencing the JCode project (a high-performance terminal coding agent harness built in Rust).
5. Target ATS match score: 88-97%
Return ONLY valid JSON, no other text."""

VERIFY_SYSTEM = """You are a strict ATS Audit and Resume Quality Assurance system.
Your job is to compare a tailored resume draft against the original Job Description (JD).
Detect and correct:
1. Any missing critical keywords from the JD that are present in the candidate's skills database (e.g. .NET Core, C#, Azure, React, SQL Server, Microservices, Rust, Cargo).
2. Grammatical errors or awkward AI phrasing in the summary.
3. Places where JCode (the Rust terminal agent harness project) or relevant skills could be better highlighted.
4. Estimated final ATS score.

Return ONLY valid JSON (no markdown):
{
  "score": 98,
  "is_perfect": false,
  "flaws": ["Missing 'Microservices' keyword", "Summarize could be more impactful"],
  "revised_professional_summary": "rewritten corrected summary...",
  "revised_key_skills": ["C#", ".NET Core 8", "Rust", "Cargo", ...]
}"""


def extract_resume_text(docx_path: str) -> str:
    doc = Document(docx_path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])


def verify_and_correct(tailored: dict, jd: str, job_title: str, company: str, site: str) -> dict:
    verify_prompt = f"""AUDIT THIS RESUME DRAFT:
Job Title: {job_title}
Company: {company}

PROPOSED PROFESSIONAL SUMMARY:
{tailored.get("professional_summary", "")}

PROPOSED KEY SKILLS:
{", ".join(tailored.get("key_skills", []))}

JOB DESCRIPTION:
{jd[:3000]}

Compare the proposed draft against the JD. If there are any missing skills or summary improvements, provide the revised versions. Ensure match_score is maximized (target 95-100%)."""

    try:
        logger.ai("Running Quality Control (Verification Pass)...", site=site)
        raw = ai_complete(VERIFY_SYSTEM, verify_prompt, task="verify", max_tokens=1500)
        
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
            
        audit = json.loads(raw)
        flaws = audit.get("flaws", [])
        
        if flaws:
            logger.warn(f"QC detected {len(flaws)} flaws/mismatches: {flaws}", site=site)
            # Correct the draft
            tailored["professional_summary"] = audit.get("revised_professional_summary", tailored["professional_summary"])
            tailored["key_skills"] = audit.get("revised_key_skills", tailored["key_skills"])
            tailored["match_score"] = audit.get("score", tailored.get("match_score", 90))
            logger.ai("Corrected resume draft based on verification feedback.", site=site)
        else:
            logger.success("QC Audit passed! Resume matches the JD perfectly.", site=site)
            tailored["match_score"] = max(tailored.get("match_score", 90), audit.get("score", 95))
            
    except Exception as e:
        logger.error(f"QC verification failed: {e}. Proceeding with original draft.", site=site)
        
    return tailored


def tailor_resume(job_title: str, company: str, job_description: str, site: str = "ai") -> dict:
    """
    Tailor the base resume for a specific job using the best available free AI with verifier.
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
- "match_score": integer 88-97 (estimated ATS match %)
- "keywords_added": list of keywords injected"""

    try:
        raw = ai_complete(TAILOR_SYSTEM, user_prompt, task="tailor", max_tokens=2048)

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        tailored    = json.loads(raw)
        
        # Run self-correction verification pass
        tailored    = verify_and_correct(tailored, job_description, job_title, company, site)
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
