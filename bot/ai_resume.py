"""
ai_resume.py — Multi-AI resume tailoring using ai_router.py with Self-Correction Loop and clean DOCX generation
Primary: Groq Llama 3.3 70B | ATS Check: HuggingFace Mistral | Fallback: Gemini
"""
import os, re, json, time
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from bot.config import GROQ_API_KEY, BASE_RESUME_DOCX, TAILORED_TODAY
from bot.utils import logger
from bot.ai_router import ai_complete, check_resume_ats

# ─── AGENT SYSTEM PROMPTS ──────────────────────────────────────────────────

ANALYZER_SYSTEM = """You are the Analyzer Agent in the JCode Multi-Agent Swarm.
Your job is to perform a deep analysis of the Job Description (JD).

Extract and return a JSON containing:
1. "must_haves": [list of critical required skills/tools/languages],
2. "nice_to_haves": [list of preferred or bonus skills],
3. "soft_skills": [list of collaboration/leadership terms],
4. "company_domain": "e.g. fintech, cloud, tax, procurement",
5. "company_name": "name of company",
6. "job_title": "exact job title from JD",
7. "exact_phrases": [3-5 key phrases used in the JD to mirror]

Return ONLY valid JSON. Do not include markdown code block formatting."""

RERANKER_SYSTEM = """You are the Reranker Agent in the JCode Multi-Agent Swarm.
Your job is to match the candidate's skills against the JD's Must-Haves and Nice-to-Haves, performing precision reranking.
Group the candidate's actual skills into standard categories, placing JD-matching keywords FIRST in each list, and removing irrelevant categories.

Allowable candidate skills to categorize:
- Backend: .NET Core 7/8, C#, ASP.NET Web API, EF Core, CQRS, Clean Architecture, Microservices, YARP Reverse Proxy, SignalR, gRPC, WCF, Repository Pattern, Unit of Work
- AI / ML: Azure OpenAI GPT-4, Semantic Kernel, LangChain (.NET), Vector Embeddings, pgvector, Azure AI Search, Azure Form Recognizer, GitHub Copilot, Prompt Engineering
- Cloud: Azure App Services, Azure SQL, Azure Redis Cache, Azure DevOps, Azure Blob Storage, Application Insights, ARM Templates
- Frontend: Angular 15+, React, TypeScript, RxJS, NgRx/Redux, Material-UI, Tailwind CSS, Vue.js, Lazy Loading, Code Splitting
- Databases: SQL Server, PostgreSQL, MySQL, Oracle, Redis, pgvector, LINQ Optimisation, Stored Procedures, Full-Text Indexing
- DevOps & CI/CD: Docker, Azure DevOps YAML, GitHub Actions, Git Flow, SonarQube, OpenTelemetry, Grafana K6, Serilog
- Security: JWT, OAuth2, OIDC, AES-256 Encryption, RBAC, IP Whitelisting, X.509 Certificate Rotation, mTLS, PCI-DSS, OWASP Top 10, FIPS Compliance
- Messaging: RabbitMQ, Redis Pub/Sub, Async Workflows, Event-Driven Architecture, Polly Circuit Breakers
- Testing: xUnit, NUnit, Moq, Integration Testing, TDD, Grafana K6 Load Testing
- Methodology: Agile/Scrum, Sprint Planning, Code Reviews, Architectural Decision Records (ADRs), Team Mentoring

Return a JSON with "skills_by_category" containing lists for: Backend, Frontend, Cloud, Databases, DevOps, Security, Testing, Methodology.
Return ONLY valid JSON. Do not include markdown formatting."""

TAILOR_SYSTEM = """You are the Tailor Agent in the JCode Multi-Agent Swarm.
Your job is to rewrite the candidate's Professional Summary and Work Experience bullets based on the Analyzer's findings and the Reranker's sorted skills.

Follow these rules strictly:
1. PROFESSIONAL SUMMARY: 5 lines max.
   - Line 1: "[Exact JD job title] with 4+ years of experience in [top 3 MUST-HAVE keywords from JD]"
   - Line 2-3: 2 strongest achievements from base resume matching JD's priorities.
   - Line 4: Mirror 2-3 exact phrases from JD.
   - Line 5: "Bringing value to [COMPANY NAME from JD] through [specific skill from JD]"
2. WORK EXPERIENCE BULLETS:
   - Write 4-6 bullets per role using: "[Strong past-tense verb] + [what I did, using JD's exact phrasing] + [specific tech] + [quantified result with number]".
   - First 2 bullets of LTIMindtree must directly use the top 2 MUST-HAVE keywords from the JD.
   - EVERY single bullet must contain a number metric (%, ms, x, users, RPS, $, hours saved).
   - Enhance mentoring/code review/architecture bullets if mentioned in the JD must-haves.
3. PROJECTS:
   - Select max 3 projects from: e-ProcureZen, AI Tax Document Analyser, Nexa Vault, SSO Application, NEICE. Frame tech stack using JD preferred terms. Do NOT invent new projects.

Return ONLY a JSON block containing:
- "job_title_headline": "Exact Job Title from JD"
- "professional_summary": "rewritten summary"
- "work_experience": {
     "LTIMindtree": [bullets],
     "DSSI Solutions India Pvt Ltd": [bullets],
     "Nexa Office InfoSystems LLP": [bullets],
     "Kasadara Technology Solutions": [bullets]
  },
- "projects": [{"name": "...", "tech_stack": "...", "bullets": [...]}]

Return ONLY valid JSON."""

VERIFIER_SYSTEM = """You are the Verifier Agent in the JCode Multi-Agent Swarm.
Your job is to compare the draft against the original JD and enforce strict compliance.

Verify and correct:
1. Exact Job Title mirrored in headline.
2. Professional Summary matches 5-line formula, has top 3 must-haves, achievements, and company value sentence.
3. Every single experience bullet contains a number metric.
4. Top 2 bullets of LTIMindtree use top 2 must-haves.
5. No projects or skills are fabricated (projects must strictly be from: e-ProcureZen, AI Tax Document Analyser, Nexa Vault, SSO Application, or NEICE).

If any rule is violated, correct the section.
Return the corrected full JSON containing:
{
  "job_title_headline": "...",
  "professional_summary": "...",
  "skills_by_category": { ... },
  "work_experience": { ... },
  "projects": [ ... ],
  "ats_report": {
     "match_score": 98,
     "matched_keywords": [...],
     "missing_with_equivalents": [...],
     "true_gaps": [...],
     "experience_gap_compensation": "...",
     "top_3_standout_points": [...],
     "recruiter_weak_point": "..."
  }
}
Return ONLY valid JSON."""

# ─── MAIN COORDINATOR WORKFLOW ─────────────────────────────────────────────

def extract_resume_text(docx_path: str) -> str:
    doc = Document(docx_path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

def parse_json_safely(raw: str) -> dict:
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()
    return json.loads(raw.strip())

def tailor_resume(job_title: str, company: str, job_description: str, site: str = "ai") -> dict:
    logger.ai(f"[JCode Swarm] Starting Multi-Agent Coordinator Workflow...", site=site)
    base_text = extract_resume_text(BASE_RESUME_DOCX)
    
    # ─── STEP 1: ANALYZER AGENT ───
    logger.ai("[JCode Coordinator] Launching Analyzer Agent...", site=site)
    try:
        raw_analysis = ai_complete(ANALYZER_SYSTEM, f"Analyze this JD:\n{job_description[:4000]}", task="analyze", max_tokens=1000)
        analysis = parse_json_safely(raw_analysis)
        logger.success(f"    [Analyzer] Extracted {len(analysis.get('must_haves', []))} must-haves.", site=site)
    except Exception as e:
        analysis = {"must_haves": [job_title], "nice_to_haves": [], "exact_phrases": []}
        logger.warn(f"    [Analyzer] Failed: {e}", site=site)

    # ─── STEP 2: RERANKER AGENT ───
    logger.ai("[JCode Coordinator] Launching Reranker Agent...", site=site)
    try:
        rerank_prompt = f"Rerank candidate skills based on Must-Haves: {analysis.get('must_haves')} and Nice-to-Haves: {analysis.get('nice_to_haves')}"
        raw_skills = ai_complete(RERANKER_SYSTEM, rerank_prompt, task="rerank", max_tokens=1200)
        skills_ranked = parse_json_safely(raw_skills)
        logger.success("    [Reranker] Precision skills reranking completed.", site=site)
    except Exception as e:
        skills_ranked = {"skills_by_category": {}}
        logger.warn(f"    [Reranker] Failed: {e}", site=site)

    # ─── STEP 3: TAILOR AGENT ───
    logger.ai("[JCode Coordinator] Launching Tailor Agent...", site=site)
    try:
        tailor_prompt = f"""Tailor candidate resume:
<resume>
{base_text}
</resume>
Analyzer Findings:
{json.dumps(analysis)}
Reranked Skills:
{json.dumps(skills_ranked)}
"""
        raw_tailored = ai_complete(TAILOR_SYSTEM, tailor_prompt, task="tailor", max_tokens=2500)
        draft = parse_json_safely(raw_tailored)
        draft["skills_by_category"] = skills_ranked.get("skills_by_category", {})
        logger.success("    [Tailor] Generated initial tailored resume draft.", site=site)
    except Exception as e:
        draft = {}
        logger.error(f"    [Tailor] Failed: {e}", site=site)

    # ─── STEP 4: VERIFIER AGENT (AUDIT LOOP) ───
    logger.ai("[JCode Coordinator] Launching Verifier Agent (Audit Loop)...", site=site)
    try:
        verify_prompt = f"""Audit and correct this resume draft:
Job Title: {job_title}
Company: {company}
Draft Summary: {draft.get('professional_summary')}
Draft Experience: {json.dumps(draft.get('work_experience'))}
Draft Projects: {json.dumps(draft.get('projects'))}
JD Details:
{job_description[:3000]}
"""
        raw_verified = ai_complete(VERIFIER_SYSTEM, verify_prompt, task="verify", max_tokens=2048)
        final_tailored = parse_json_safely(raw_verified)
        logger.success("    [Verifier] Resume audit completed and corrections applied.", site=site)
    except Exception as e:
        final_tailored = draft
        logger.warn(f"    [Verifier] Failed, using initial draft: {e}", site=site)

    # ─── STEP 5: BUILD CLEAN DOCX ───
    filename = f"Siva_Shankar_{re.sub(r'[^\\w\\-]', '_', job_title)[:20]}_{re.sub(r'[^\\w\\-]', '_', company)[:20]}_Resume.docx"
    out_path = os.path.join(TAILORED_TODAY, filename)
    
    try:
        build_clean_resume(final_tailored, out_path)
        logger.success(f"[JCode Coordinator] Document saved successfully to: {out_path}", site=site)
    except Exception as e:
        logger.error(f"[ERROR] Document creation failed: {e}", site=site)
        doc = Document(BASE_RESUME_DOCX)
        doc.save(out_path)

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
        "match_score": final_tailored.get("ats_report", {}).get("match_score", 90),
        "tailored":    final_tailored,
        "ats_report":  ats_report
    }

def build_clean_resume(tailored: dict, output_path: str):
    doc = Document()
    
    # Set Margins to 1 inch
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
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
        
    def add_section_heading(title):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(title)
        run.bold = True
        run.font.name = 'Calibri'
        run.font.size = Pt(12)
        
    # 1. HEADER
    add_styled_paragraph("SIVA SHANKAR", font_size=18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    headline = tailored.get("job_title_headline", "Senior Software Engineer")
    add_styled_paragraph(headline.upper(), font_size=11, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    contact_line = "+91 6383149155   •   sivashankar.avi6@gmail.com   •   https://www.linkedin.com/in/siva-shankar-4a7849226/   •   https://github.com/shivan2603   •   https://shivan2603.github.io/sivashankar-portfolio/"
    add_styled_paragraph(contact_line, font_size=10, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
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
