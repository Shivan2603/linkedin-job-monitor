"""
ai_resume.py — Multi-AI resume tailoring using ai_router.py with Self-Correction Loop and clean DOCX generation
Primary: Groq Llama 3.3 70B | ATS Check: HuggingFace Mistral | Fallback: Gemini
"""
import os, re, json
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from bot.config import GROQ_API_KEY, BASE_RESUME_DOCX, TAILORED_TODAY
from bot.utils import logger
from bot.ai_router import ai_complete, check_resume_ats

JCODE_PORTFOLIO = """CANDIDATE'S SYSTEMS & AGENT PROJECT PORTFOLIO (JCode):
The candidate has worked extensively on JCode, a next-generation high-performance terminal coding agent harness built in Rust.
Key engineering highlights from JCode to utilize:
1. Swarm & Coordinator: Implemented recursive, depth-limited spawning of agent swarm coordinators (tree of coordinators) with root-coordinator-scoped plan operations.
2. Memory & Reranker Optimization: Engineered precision-focused reranking (Mode-1/Mode-2 selection) and KV-reuse reranker design, implementing a cadence gate for mode-2 rerank to decrease token costs.
3. High Performance TUI: Rebuilt TUI rendering with prefix-reuse body rebuilds using a shared renderer and message boundaries, minimizing redrawing costs. Added scrollbar optimizations for cold starts to avoid wasted body builds.
4. Telemetry: Developed custom telemetry collection workers to track token usage, costing, and runtime metrics.
"""

TAILOR_SYSTEM = f"""You are a professional resume writer and ATS optimization expert.
Your task is to tailor the candidate's resume for a specific job description (JD).

Follow these rules strictly:

1. ANALYZE FIRST:
- Extract ALL keywords from the JD (skills, tools, frameworks, methodologies, job title variations, and soft skills).
- Identify the top 5 "must-have" requirements vs "nice-to-have" requirements.
- Mirror the exact job title used in the JD in the resume headline (job_title_headline).
- Identify the seniority level and tone (startup vs enterprise vs government).

2. ATS RULES (non-negotiable):
- Return the response in a structured JSON. The python program will build the document from scratch using your returned data with NO tables, NO columns, NO text boxes, NO icons, and NO headers/footers to guarantee perfect ATS parsing.
- Mirror exact keywords from the JD in the summary, skills, and bullet points — do not paraphrase them.
- Include both full forms and abbreviations (e.g., "Continuous Integration / CI", "Microsoft Azure (AZ-204)").
- Keep headings clean without symbols, graphics, or special characters in section titles.

3. CONTENT LIMITS:
- ONLY include skills and experience the candidate actually has in the base resume.
- DO NOT invent, hallucinate, or add skills the candidate has not listed.
- DO NOT change job titles, company names, or employment dates.
- DO NOT add projects, certifications, or tools not mentioned.
- If the JD requires a skill the candidate genuinely doesn't have, DO NOT add it — list it under "missing_skills" in the "ats_report".

4. JCODE EXCEPTION:
- The candidate has worked on the JCode project:
{JCODE_PORTFOLIO}
- If the JD requires Rust, systems engineering, CLI/TUI tools, high-performance computing, or AI agent coordinators, you MUST include the JCode project in the projects list. Otherwise, choose from the other projects in the base resume.

5. OUTPUT JSON FORMAT:
You must output a single valid JSON block containing:
- "job_title_headline": "Exact Job Title from JD"
- "professional_summary": "4-5 lines max. Start with '[Job Title from JD] with 4+ years of experience in [top 3 skills from JD]'. Include 2-3 measurable achievements from candidate's actual experience. End with value brought to this specific company/role. Mirror exact job title from JD in the first sentence."
- "skills_by_category": {{
     "Backend": [list of relevant skills from base resume matching JD first, remove irrelevant],
     "Frontend": [list of relevant frontend skills from base resume],
     "Cloud": [list of relevant cloud skills from base resume],
     "Databases": [list of relevant database skills from base resume],
     "DevOps": [list of DevOps skills],
     "Security": [list of security skills],
     "Testing": [list of testing skills],
     "Methodology": [list of methodology skills]
  }}
- "work_experience": {{
     "LTIMindtree": [4-6 bullets. Formula: "[Strong action verb] + [what I did] + [technology used] + [quantified result]". Every bullet must have a number. Top 2 bullets must match JD's top requirements. No generic phrases like "responsible for".],
     "DSSI Solutions India Pvt Ltd": [4-6 bullets, same formula & rules],
     "Nexa Office InfoSystems LLP": [4-6 bullets, same formula & rules],
     "Kasadara Technology Solutions": [4-6 bullets, same formula & rules]
  }}
- "projects": [
     Max 3 projects. Each project object must have:
     "name": "Project name",
     "tech_stack": "tech stack on one line",
     "bullets": [2-3 bullets with metrics]
  ]
- "ats_report": {{
     "match_score": estimated percentage (0-100),
     "top_matched_keywords": [8-10 keywords],
     "missing_skills": [list of skills from JD candidate does not have],
     "suggestions": [1-3 suggestions for improvement]
  }}

Return ONLY valid JSON. Do not include markdown code block formatting (like ```json)."""

VERIFY_SYSTEM = """You are a strict ATS Audit and Resume Quality Assurance system.
Your job is to compare a tailored resume draft against the original Job Description (JD).

Verify and correct:
1. Ensure the exact job title from the JD is mirrored in the headline.
2. Check the Professional Summary: is it 4-5 lines? Does it start with "[Job Title from JD] with 4+ years..."? Does it have 2-3 measurable metrics? Does it end with value?
3. Check the Skills section: are skills grouped by the standard categories? Are JD keywords first? Are irrelevant skills removed?
4. Check Work Experience bullets: does each role have 4-6 bullets? Does every single bullet contain a number metric? Do the top 2 bullets match the JD requirements? Do they use strong action verbs?
5. Check Projects: max 3 projects, name + tech stack on one line, 2-3 bullets with metrics.
6. Check JCode: if Rust/Systems are in the JD, is JCode included?
7. Ensure NO fabricated skills or changes to company/dates.

If any section violates these rules, rewrite and correct it.
Return the corrected full JSON block in the exact same format:
{
  "job_title_headline": "...",
  "professional_summary": "...",
  "skills_by_category": { ... },
  "work_experience": { ... },
  "projects": [ ... ],
  "ats_report": {
     "match_score": 98,
     "top_matched_keywords": [...],
     "missing_skills": [...],
     "suggestions": [...]
  }
}
Return ONLY valid JSON. Do not include markdown code block formatting."""


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
{json.dumps(tailored.get("skills_by_category", {}))}

PROPOSED WORK EXPERIENCE:
{json.dumps(tailored.get("work_experience", {}))}

PROPOSED PROJECTS:
{json.dumps(tailored.get("projects", []))}

JOB DESCRIPTION:
{jd[:3000]}

{JCODE_PORTFOLIO}

Compare the proposed draft against the JD and our strict guidelines. Rewrite and correct any section that violates the rules (e.g. missing numbers in bullets, summary not matching formula, table headings, etc.). Return the final complete JSON."""

    try:
        logger.ai("Running Quality Control (Verification Pass)...", site=site)
        raw = ai_complete(VERIFY_SYSTEM, verify_prompt, task="verify", max_tokens=2048)
        
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
            
        audit = json.loads(raw)
        
        # Merge verifier's revised blocks back into tailored
        for key in ["job_title_headline", "professional_summary", "skills_by_category", "work_experience", "projects", "ats_report"]:
            if key in audit:
                tailored[key] = audit[key]
        logger.ai("Corrected resume draft based on verification feedback.", site=site)
        
    except Exception as e:
        logger.error(f"QC verification failed: {e}. Proceeding with original draft.", site=site)
        
    return tailored


def build_clean_resume(tailored: dict, output_path: str):
    doc = Document()
    
    # Set Margins to 1 inch (standard ATS friendly)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
    # Helper to add paragraph with styling
    def add_styled_paragraph(text="", style_name='Normal', font_name='Calibri', font_size=10.5, bold=False, italic=False, align=WD_ALIGN_PARAGRAPH.LEFT, space_before=0, space_after=3, line_spacing=1.15):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = line_spacing
        if text:
            run = p.add_run(text)
            run.font.name = font_name
            run.font.size = Pt(font_size)
            run.bold = bold
            run.italic = italic
        return p
        
    # Helper to add section headings (ATS rules: standard, no special characters, no graphics)
    def add_section_heading(title):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(title)
        run.bold = True
        run.font.name = 'Calibri'
        run.font.size = Pt(12)
        
    # 1. HEADER
    # Full name (large, bold)
    add_styled_paragraph("SIVA SHANKAR", font_size=18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    # Headline (job title mirrored from JD)
    headline = tailored.get("job_title_headline", "Senior Software Engineer")
    add_styled_paragraph(headline.upper(), font_size=11, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    # Contact Details
    contact_line = "+91 6383149155   •   sivashankar.avi6@gmail.com   •   https://www.linkedin.com/in/siva-shankar-4a7849226/   •   https://github.com/shivan2603   •   https://shivan2603.github.io/sivashankar-portfolio/"
    add_styled_paragraph(contact_line, font_size=10, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    # Location
    add_styled_paragraph("Chennai, India | Open to Remote/Hybrid", font_size=10, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)
    
    # 2. PROFESSIONAL SUMMARY
    add_section_heading("Professional Summary")
    add_styled_paragraph(tailored.get("professional_summary", ""), font_size=10.5)
    
    # 3. TECHNICAL SKILLS
    add_section_heading("Technical Skills")
    skills_cat = tailored.get("skills_by_category", {})
    categories_order = ["Backend", "Frontend", "Cloud", "Databases", "DevOps", "Security", "Testing", "Methodology"]
    
    all_cats = list(skills_cat.keys())
    for cat in categories_order:
        if cat in skills_cat:
            skills_list = skills_cat[cat]
            if skills_list:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.line_spacing = 1.15
                run_cat = p.add_run(f"{cat}: ")
                run_cat.bold = True
                run_cat.font.name = 'Calibri'
                run_cat.font.size = Pt(10.5)
                
                run_skills = p.add_run(", ".join(skills_list))
                run_skills.font.name = 'Calibri'
                run_skills.font.size = Pt(10.5)
                
    for cat in all_cats:
        if cat not in categories_order:
            skills_list = skills_cat[cat]
            if skills_list:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.line_spacing = 1.15
                run_cat = p.add_run(f"{cat}: ")
                run_cat.bold = True
                run_cat.font.name = 'Calibri'
                run_cat.font.size = Pt(10.5)
                
                run_skills = p.add_run(", ".join(skills_list))
                run_skills.font.name = 'Calibri'
                run_skills.font.size = Pt(10.5)
                
    # 4. WORK EXPERIENCE
    add_section_heading("Work Experience")
    roles = [
        {
            "company": "LTIMindtree",
            "dates": "Jun 2025 – Present",
            "title": "Senior Software Engineer  |  Client: Deloitte — Enterprise Tax Platform",
            "tech": ".NET Core 8  •  ASP.NET Web API  •  Angular  •  Azure OpenAI GPT-4  •  Microservices  •  CQRS  •  pgvector  •  OpenTelemetry  •  Redis  •  SQL Server",
            "key": "LTIMindtree"
        },
        {
            "company": "DSSI Solutions India Pvt Ltd",
            "dates": "Nov 2024 – May 2025",
            "title": "Senior Software Engineer  |  Financial Procurement Platform",
            "tech": ".NET 7  •  Clean Architecture  •  CQRS  •  YARP Reverse Proxy  •  Docker  •  Azure App Services  •  RabbitMQ  •  Redis  •  JWT  •  AES-256  •  Agile/Scrum",
            "key": "DSSI Solutions India Pvt Ltd"
        },
        {
            "company": "Nexa Office InfoSystems LLP",
            "dates": "Jul 2024 – Nov 2024",
            "title": "Senior Software Engineer — Contract / Consultant  |  Enterprise Document Management",
            "tech": ".NET Core  •  ASP.NET Web API  •  Angular  •  Redux/NgRx  •  Docker  •  SQL Server  •  OAuth2/OIDC  •  Material-UI",
            "key": "Nexa Office InfoSystems LLP"
        },
        {
            "company": "Kasadara Technology Solutions",
            "dates": "Jul 2022 – Jun 2024",
            "title": "Software Engineer  |  US Government & SaaS Enterprise Platforms",
            "tech": ".NET Core  •  ASP.NET MVC  •  C#  •  Angular  •  Vue.js  •  Entity Framework Core  •  Go  •  WCF  •  Agile  •  FIPS Compliance",
            "key": "Kasadara Technology Solutions"
        }
    ]
    
    work_exp = tailored.get("work_experience", {})
    for role in roles:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        run_comp = p.add_run(role["company"])
        run_comp.bold = True
        run_comp.font.name = 'Calibri'
        run_comp.font.size = Pt(11)
        
        # Right-aligned dates
        p.paragraph_format.tab_stops.add_tab_stop(Inches(6.5), 2)
        run_date = p.add_run(f"\t{role['dates']}")
        run_date.bold = True
        run_date.font.name = 'Calibri'
        run_date.font.size = Pt(11)
        
        add_styled_paragraph(role["title"], font_size=10.5, italic=True, space_after=2)
        add_styled_paragraph(role["tech"], font_size=10, space_after=3)
        
        bullets = work_exp.get(role["key"]) or work_exp.get(role["company"]) or []
        for b in bullets:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(18)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            run_b = p.add_run(f"• {b}")
            run_b.font.name = 'Calibri'
            run_b.font.size = Pt(10.5)
            
    # 5. PROJECTS
    add_section_heading("Projects")
    projects_list = tailored.get("projects", [])
    for proj in projects_list:
        proj_name = proj.get("name") or proj.get("title") or ""
        proj_tech = proj.get("tech_stack") or proj.get("tech") or ""
        proj_bullets = proj.get("bullets") or proj.get("description") or []
        if isinstance(proj_bullets, str):
            proj_bullets = [proj_bullets]
            
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(2)
        run_name = p.add_run(proj_name)
        run_name.bold = True
        run_name.font.name = 'Calibri'
        run_name.font.size = Pt(11)
        
        if proj_tech:
            run_t = p.add_run(f" — {proj_tech}")
            run_t.italic = True
            run_t.font.name = 'Calibri'
            run_t.font.size = Pt(10)
            
        for b in proj_bullets:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(18)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            run_b = p.add_run(f"• {b}")
            run_b.font.name = 'Calibri'
            run_b.font.size = Pt(10.5)
            
    # 6. CERTIFICATIONS
    add_section_heading("Certifications")
    cert_list = [
        "Microsoft Azure Developer Associate (AZ-204)  |  Microsoft  |  March 18, 2024  |  Credential ID: 1KA2C7-B08024",
        "Top Performer Award  |  Nexa Office InfoSystems LLP  |  2024  |  Outstanding delivery & technical leadership"
    ]
    for cert in cert_list:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Pt(18)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        run_c = p.add_run(f"• {cert}")
        run_c.font.name = 'Calibri'
        run_c.font.size = Pt(10.5)
        
    # 7. EDUCATION
    add_section_heading("Education")
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    run_deg = p.add_run("B.E. Electronics & Communication Engineering")
    run_deg.bold = True
    run_deg.font.name = 'Calibri'
    run_deg.font.size = Pt(11)
    
    p.paragraph_format.tab_stops.add_tab_stop(Inches(6.5), 2)
    run_year = p.add_run("\t2018 – 2022")
    run_year.bold = True
    run_year.font.name = 'Calibri'
    run_year.font.size = Pt(11)
    
    add_styled_paragraph("Kathir College of Engineering, Coimbatore (Anna University)  |  GPA: 8.6 / 10", font_size=10.5, space_after=4)
    
    doc.save(output_path)


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
{job_description[:4000]}
</job_description>

{JCODE_PORTFOLIO}

Return ONLY the JSON matching the format instructions."""

    try:
        raw = ai_complete(TAILOR_SYSTEM, user_prompt, task="tailor", max_tokens=2500)

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        tailored = json.loads(raw)
        
        # Run self-correction verification pass
        tailored = verify_and_correct(tailored, job_description, job_title, company, site)
        match_score = tailored.get("ats_report", {}).get("match_score", 90)

        # Build tailored clean .docx
        filename = f"Siva_Shankar_{safe_role}_{safe_company}_Resume.docx"
        out_path = os.path.join(TAILORED_TODAY, filename)
        
        build_clean_resume(tailored, out_path)
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
        import traceback
        traceback.print_exc()
        out_path = os.path.join(TAILORED_TODAY, f"Siva_Shankar_{safe_role}_{safe_company}_Resume.docx")
        # Fallback copy
        doc = Document(BASE_RESUME_DOCX)
        doc.save(out_path)
        return {"resume_path": out_path, "match_score": 85, "tailored": {}, "ats_report": {}}
