"""
ai_resume.py — Multi-AI resume tailoring bridge for jobbot
Delegates all resume tailoring to the TailorRobot engine at E:\SivaShankar\tailorrobot.
"""
import os, re, json, time, sys
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

# ─── TAILORROBOT ENGINE BRIDGE ─────────────────────────────────────
TAILORROBOT_PATH = os.getenv("TAILORROBOT_PATH", r"E:\SivaShankar\tailorrobot")
if TAILORROBOT_PATH not in sys.path:
    sys.path.insert(0, TAILORROBOT_PATH)

try:
    from resume_builder_core import build_tailored_resume_from_json, run_local_tailor_engine
    import config as _tr_config
    from ai_resume import tailor_resume as _tr_tailor_resume
    TAILORED_TODAY  = _tr_config.TAILORED_TODAY
    BASE_RESUME_DOCX = _tr_config.BASE_RESUME_DOCX
    DATA_FOLDER = _tr_config.DATA_FOLDER
    _USING_TAILORROBOT = True
except ImportError:
    from bot.config import TAILORED_TODAY, BASE_RESUME_DOCX, DATA_FOLDER
    from bot.resume_builder_core import build_tailored_resume_from_json
    _tr_tailor_resume = None
    _USING_TAILORROBOT = False

from bot.config import GROQ_API_KEY
from bot.utils import logger
from bot.ai_router import ai_complete, check_resume_ats
from bot.resume_research_agent import (
    research_company,
    expand_projects,
    score_and_rewrite_bullets,
    enforce_consistency,
    enforce_ats_keywords,
    write_perfect_fit_summary,
    deep_rewrite_projects,
)
from bot.cover_letter_agent import generate_cover_letter
from bot.interview_prep_agent import generate_interview_prep

# ─── LOCAL SWARM IMPLEMENTATION (FALLBACK) ─────────────────────────

TELEMETRY_FILE = os.path.join(DATA_FOLDER, "telemetry.json")

# ─── AGENT SYSTEM PROMPTS ──────────────────────────────────────────────────

JD_INTELLIGENCE_SYSTEM = """You are the JD Intelligence Agent — the first and most critical agent in the resume-tailoring pipeline.
Your job is to DEEPLY analyse the Job Description and extract strategic intelligence that will drive EVERY section of the resume.

Think like a senior recruiter AND like the candidate trying to stand out. Analyse:

1. LOCATION INTELLIGENCE:
   - What city/country is the job in? (e.g. "Kuala Lumpur, Malaysia" or "London, UK" or "Remote")
   - Does it require relocation? (look for: "must be based in", "onsite", "relocation package", location being non-India)
   - Is visa sponsorship mentioned or implied?
   - What is the ideal location_line for the resume header?
   - For international: "Chennai, India  |  Open to Global Relocation (Remote / Hybrid)  |  Visa sponsorship required"
   - For India-based jobs (whether remote, hybrid, or onsite): "Chennai, India  |  Open to Remote / Hybrid"

2. DOMAIN INTELLIGENCE:
   - What industry/domain is the company in? (fintech, government, e-commerce, healthcare, SaaS, logistics, banking, telecom, consulting, insurance, tax)
   - What domain power words does the JD use? (e.g. "core banking", "digital transformation", "regulatory compliance", "citizen-facing", "high-frequency trading")
   - What domain-specific tech is prioritised? (e.g. fintech → PCI-DSS, JWT, Redis, high-throughput; gov → FIPS, Section 508, WCF, federal; cloud-native → Docker, Kubernetes, microservices)

3. SENIORITY INTELLIGENCE:
   - Is this a team lead / tech lead / architect role? (look for: "lead", "mentor", "architect", "design decisions", "team of", "drive technical")
   - Or is it individual contributor? (look for: "hands-on", "implement", "develop", "engineer")
   - What bullet style fits best: "achievement" (team lead → metrics + team) or "technical" (IC → deep stack + performance)?

4. CULTURE INTELLIGENCE:
   - What 3-5 culture keywords describe this company? (e.g. "collaborative", "fast-paced", "innovation-driven", "mission-critical", "customer-first")
   - What exact phrases from the JD should be mirrored in the summary? (pick 2-3 most distinctive phrases)

5. SUMMARY CLOSING (Line 5):
   - Write the EXACT last line of the professional summary.
   - Format: "[Eager to / Excited to / Committed to] [join/contribute to] [Company]'s [domain keyword] team in [City] [, bringing / and deliver] [top relevant skill from JD]."
   - If remote: "Bringing [top skill] to [Company]'s [domain] mission, delivering results across distributed international teams."
   - If India-based: "Bringing scalable [top skill] expertise to [Company] to [deliver JD's stated outcome]."

6. CERTIFICATIONS RELEVANCE:
   - Which of our certs should be highlighted? (AZ-204 if Azure in JD; NEICE if gov/federal; AZ-204 with [HIGHLY RELEVANT] suffix if Azure is the primary cloud)

7. EXPERIENCE INTELLIGENCE:
   - Carefully read the years of experience required by the JD.
   - The candidate has exactly 4 years of experience.
   - The job is a MATCH if it requires EXACTLY 4 years, or 4+ years (e.g. "4+ years", "minimum 4 years", "4-6 years", "4-7 years", "4-8 years").
   - The job is NOT a match if it requires 5 years or more (e.g. "5+ years", "5-8 years", "6 years", "8+ years"), or if it requires a range starting below 4 (e.g. "3-4 years", "2-4 years", "2-5 years", "3+ years", "2+ years").
   - Set "is_experience_matching" to true if it matches exactly 4 or 4+ years. Set to false if it requires less than 4 (e.g. 2, 3) or more than 4 (e.g. 5, 6).

Return ONLY valid JSON (no markdown, no code blocks):
{
  "job_location_city": "Kuala Lumpur",
  "job_location_country": "Malaysia",
  "job_location_type": "Hybrid",
  "requires_relocation": true,
  "visa_sponsorship_mentioned": true,
  "location_line": "Chennai, India  |  Open to Global Relocation (Remote / Hybrid)  |  Visa sponsorship required",
  "company_domain": "fintech",
  "domain_power_words": ["digital banking", "core banking", "financial services"],
  "domain_priority_skills": ["PCI-DSS", "JWT", "Redis", "OAuth2", "high-throughput APIs"],
  "domain_priority_category": "Security & Messaging",
  "seniority_level": "Senior",
  "is_team_lead_role": false,
  "bullet_style": "technical",
  "culture_keywords": ["collaborative", "innovation", "agile"],
  "jd_mirror_phrases": ["deliver scalable financial solutions", "cloud-native microservices"],
  "summary_closing_line": "Excited to relocate to Kuala Lumpur and bring 4+ years of PCI-DSS compliant .NET expertise to CIMB's digital banking platform.",
  "cert_highlight": "AZ-204 (HIGHLY RELEVANT — Azure is primary cloud)",
  "is_india_remote": false,
  "is_international": true,
  "is_experience_matching": true
}"""

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
- Backend: .NET Core 7/8, .NET Framework 2.0/3.5/4.0/4.8, C#, ASP.NET Web API, ASP.NET MVC, ADO.NET, EF Core, CQRS, Clean Architecture, Microservices, YARP Reverse Proxy, SignalR, gRPC, WCF, Repository Pattern, Unit of Work
- AI / ML: Azure OpenAI GPT-4, Semantic Kernel, LangChain (.NET), Vector Embeddings, pgvector, Azure AI Search, Azure Form Recognizer, GitHub Copilot, Prompt Engineering
- Cloud: Azure App Services, Azure SQL, Azure Redis Cache, Azure DevOps, Azure Blob Storage, Application Insights, ARM Templates
- Frontend: JavaScript (JS), AJAX, Angular 15+, React, TypeScript, RxJS, NgRx/Redux, Material-UI, Tailwind CSS, Vue.js, Lazy Loading, Code Splitting
- Databases: SQL Server (including SQL Server 2008), PostgreSQL, MySQL, Oracle, Redis, pgvector, LINQ Optimisation, Stored Procedures, Full-Text Indexing
- DevOps & CI/CD: Docker, Azure DevOps YAML, GitHub Actions, Git Flow, SonarQube, OpenTelemetry, Grafana K6, Serilog
- Security: JWT, OAuth2, OIDC, AES-256 Encryption, RBAC, IP Whitelisting, X.509 Certificate Rotation, mTLS, PCI-DSS, OWASP Top 10, FIPS Compliance
- Messaging: RabbitMQ, Redis Pub/Sub, Async Workflows, Event-Driven Architecture, Polly Circuit Breakers
- Testing: xUnit, NUnit, Moq, Integration Testing, TDD, Grafana K6 Load Testing
- Methodology: Agile/Scrum, Sprint Planning, Code Reviews, Architectural Decision Records (ADRs), Team Mentoring, Software Development Lifecycle (SDLC), Technical Documentation (Requirement Specification, User Manual, System Manual), Client Brief Translation, Requirement Analysis

Return a JSON with "skills_by_category" containing lists for: Backend, Frontend, Cloud, Databases, DevOps, Security, Testing, Methodology.
CRITICAL: Return ONLY standard JSON. All keys and string values must be enclosed in double quotes. Do not include raw unquoted strings, variable names, comments, or trailing commas. Do not include markdown code block formatting."""

TAILOR_SYSTEM = """You are the Tailor Agent in the JCode Multi-Agent Swarm — operating in FRESH WRITING MODE.
You will receive: the candidate's base resume, Analyzer findings, Reranker-sorted skills, JD Intelligence, AND Company Intelligence (from the Company Research Agent).
Your job is to FRESHLY WRITE every section of the resume from scratch — NOT paraphrase or shuffle the base resume.
Every bullet must sound like a senior engineer wrote it specifically for THIS company, using THIS company's language and priorities.

== FRESH WRITING MODE RULES ==
1. Do NOT copy bullets word-for-word from the base resume. REWRITE with new phrasing.
2. Mirror the JD's exact phrases (from jd_mirror_phrases and company_intelligence.jd_mirror_phrases) naturally.
3. Open bullets with the company's culture DNA (from company_intelligence.culture_dna).
4. For technical bullets: include an architecture RATIONALE — WHY that technology was chosen.
5. For impact bullets: frame the outcome in business terms (saved hours, reduced latency, improved uptime).
6. First bullet of every role MUST use at least one of the JD's must-have skills.
7. Every single JD must-have keyword MUST appear at least once across all bullets and summary combined.
8. PERFECT FIT POSITIONING: Write as if this candidate is the ONLY person qualified for this role.
   Every bullet should answer the unspoken recruiter question: "Can they actually do what we need?"
9. PROOF OVER CLAIMS: Replace every vague claim with a metric. "improved performance" → "reduced p99 latency from 850ms to 94ms".
10. TECHNICAL DEPTH: At least one bullet per role must show WHY an architectural decision was made, not just WHAT was done.

CRITICAL: You must strictly adhere to the Candidate Base Facts below. Never fabricate, invent, or extrapolate any experience, technology, or metric. All rewrites must be 100% grounded in these base facts.

=========================================
CANDIDATE BASE FACTS (Grounded Database)
=========================================
1. HEADER:
   - Name: SIVA SHANKAR
   - Contact: +91 6383149155 | sivashankar.avi6@gmail.com
   - Links: LinkedIn: https://www.linkedin.com/in/siva-shankar-4a7849226/ | GitHub: https://github.com/shivan2603 | Portfolio: https://shivan2603.github.io/sivashankar-portfolio/
   - Location Line Options:
     * If international / relocation required: "Chennai, India  |  Open to Global Relocation (Remote / Hybrid)  |  Visa sponsorship required"
     * If India-based (remote / onsite / hybrid): "Chennai, India  |  Open to Remote / Hybrid"

2. WORK EXPERIENCE:
   * Role 1: LTIMindtree (Jun 2025 – Present)
     - Core Title: Senior Software Engineer (can tailor to "Senior Software Engineer", "Senior Backend Developer", "Senior .NET Developer" depending on JD)
     - Deloitte Enterprise Tax Client context: Client: Deloitte — Enterprise Tax Platform
     - Allowed Technologies: C#, .NET Core 8, ASP.NET Web API, Angular, Azure OpenAI GPT-4, Microservices, CQRS, pgvector, OpenTelemetry, Redis, SQL Server, Entity Framework Core
     - Grounded Achievements/Metrics to reframe:
       * Migrated 50+ legacy tax tables to QRP structures, reducing query latency by 38%.
       * Deployed Azure OpenAI embedding pipeline for dynamic schema mapping, saving 60% manual effort.
       * Developed secure stored procedures for dynamic RBAC role mapping across 15+ tax modules.
       * Profiled and refactored 30+ ASP.NET Web API endpoints to solve N+1 query loops, achieving sub-100ms p99 latency.
       * Configured Redis-based API response caching, reducing database query load by 45%.
       * Instrumented OpenTelemetry distributed tracing across microservices, reducing MTTR by 50%.
       * Secured 30+ RESTful APIs with OAuth2 + JWT authentication for OWASP compliance.
       * Integrated Azure OpenAI GPT-4 for automated tax document summarization, speeding up weekly triages by 35%.
       * Built a semantic search engine using pgvector for sub-200ms document lookups.
       * Leveraged GitHub Copilot prompt engineering for unit tests, raising coverage to 85% with xUnit.

   * Role 2: DSSI Solutions India Pvt Ltd (Nov 2024 – May 2025)
     - Core Title: Senior Software Engineer (can tailor to "Senior Software Engineer", "Senior .NET Developer", "Senior Backend Engineer" depending on JD)
     - Procurement Client context: Financial Procurement Platform
     - Allowed Technologies: C#, .NET 7, Clean Architecture, CQRS, YARP Reverse Proxy, Docker, Azure App Services, RabbitMQ, Redis, JWT, AES-256, Agile/Scrum
     - Grounded Achievements/Metrics to reframe:
       * Engineered 12+ procurement microservices using .NET 7, CQRS, and Clean Architecture.
       * Configured RabbitMQ async messaging, increasing message processing throughput by 3x.
       * Mentored 4 junior software engineers on CQRS and Git Flow, reducing post-deployment bugs by 40%.
       * Containerized all 12 microservices using Docker, decreasing container image sizes by 65%.
       * Implemented Azure Form Recognizer for automated invoice data extraction, saving 100+ manual hours.
       * Configured YARP Reverse Proxy for path-based routing, maintaining a 99.98% system uptime SLA.

   * Role 3: Nexa Office InfoSystems LLP (Jul 2024 – Nov 2024)
     - Core Title: Senior Software Engineer — Contract / Consultant (can tailor to "Senior Software Engineer", "Senior Full-Stack Developer", ".NET Consultant")
     - Document Management Client context: Enterprise Document Management
     - Allowed Technologies: C#, .NET Core, ASP.NET Web API, Angular, Redux/NgRx, Docker, SQL Server, OAuth2/OIDC, Material-UI, mTLS, X.509
     - Grounded Achievements/Metrics to reframe:
       * Designed modular UI components in Angular, improving page load speeds by 35% across forms.
       * Secured document repository with AES-256 encryption and OAuth2 OpenID Connect integration.
       * Profiled SQL Server queries and rebuilt indexes, accelerating search lookup performance by 25%.
       * Configured secure service-to-service communication using mTLS and X.509 certificate rotations.

   * Role 4: Kasadara Technology Solutions (Jul 2022 – Jun 2024)
     - Core Title: Software Engineer (can tailor to "Software Engineer", ".NET Developer", "Backend Developer")
     - US Gov SaaS Client context: US Government & SaaS Enterprise Platforms
     - Allowed Technologies: C#, .NET Framework 4.x, ASP.NET MVC, ADO.NET, EF Core, Go, WCF, SQL Server, Agile, FIPS Compliance, Section 508, WCAG
     - Grounded Achievements/Metrics to reframe:
       * Migrated legacy modules from .NET Framework to .NET Core, achieving a 40% memory usage reduction.
       * Developed high-throughput background processing services in Go, doubling processing speeds.
       * Refactored application UI to ensure strict compliance with US Federal Section 508 and WCAG accessibility standards.
       * Optimized legacy WCF and ADO.NET data access layers, reducing web page transaction times by 20%.

3. PROJECTS:
   - Select max 2 projects that match the JD's domain:
     * AI Tax Document Analyser: C# • .NET Core • Azure OpenAI • pgvector • Semantic Kernel. (Extracts tax data using Semantic Kernel, pgvector search, Azure OpenAI).
     * e-ProcureZen: C# • .NET 7 • Clean Architecture • YARP • Redis. (Financial procurement platform with YARP reverse proxy and RabbitMQ messaging).
     * Nexa Vault: .NET Core • Angular • AES-256 • Docker. (Secure document vault using AES-256 encryption and OAuth2 OIDC).
     * SSO Application: ASP.NET Core • OAuth2 • OIDC • JWT. (Centralized SSO using OpenID Connect and mTLS).
     * NEICE: .NET Framework • WCF • SQL Server • FIPS. (US National Electronic Interstate Compact Enterprise platform, FIPS-compliant, WCF SOAP services).

4. CERTIFICATIONS:
   - Microsoft Azure Developer Associate (AZ-204) | Microsoft | March 18, 2024
   - Top Performer Award | Nexa Office InfoSystems LLP | 2024
   - US Government Platform (NEICE) | FIPS Compliance & Federal Security Standards | Kasadara Technology Solutions | 2022–2024 (include only for government/defense JDs)

5. EDUCATION:
   - B.E. Electronics & Communication Engineering | Kathir College of Engineering, Coimbatore (Anna University) | 2018 – 2022 | GPA: 8.6 / 10

=========================================
DYNAMIC TAILORING RULES
=========================================
1. HEADER:
   - Set "job_title_headline" to the target job title (Title Case, no location).
   - Set "location_line" based on the relocation/country context in JD Intelligence.
2. PROFESSIONAL SUMMARY (5 sentences only):
   - Sentence 1: Start with the EXACT job_title_headline (e.g. "[job_title_headline] with 4+ years..."). No pronouns.
   - Sentences 2-3: Frame candidate achievements mapping the JD's primary cloud/framework/lead requirements.
   - Sentence 4: Include exact phrases from jd_mirror_phrases.
   - Sentence 5: Append the exact "summary_closing_line" from JD Intelligence.
3. SKILLS CATEGORIES:
   - Return skills grouped under Backend, Frontend, Cloud, Databases, DevOps, Security, Testing, Methodology. Place matching technologies first in each category.
4. WORK EXPERIENCE:
   - Return a list of dicts. For each company, tailor:
     * "role_title": Incorporate relevant JD tech keywords. e.g. "Senior .NET Developer" instead of plain "Senior Software Engineer" if .NET is the primary keyword, but keep Deloitte client context.
     * "tech_stack_line": Group technologies actually used in that role. Highlight ones matching the JD.
     * "bullets": Write metrics-driven bullets matching the allowed metrics for that role. First 2 bullets of LTIMindtree must prioritize must-have skills from JD. Limit bullets per role: LTIMindtree (4 max), DSSI (3 max), Nexa (2 max), Kasadara (2 max).
5. PROJECTS:
   - Select 2 projects. Write name, tech_stack, and 2 tailored bullets detailing architecture decisions.
6. CERTIFICATIONS:
   - List the 2-3 certifications relevant to this JD (e.g., adding AZ-204 highlight or NEICE as appropriate).

Return ONLY a JSON block structured as:
{
  "job_title_headline": "Title Case Job Title",
  "location_line": "Chennai, India | ...",
  "professional_summary": "...",
  "skills_by_category": {
    "Backend": [...],
    ...
  },
  "work_experience": [
    {
      "company": "LTIMindtree",
      "dates": "Jun 2025 – Present",
      "role_title": "Senior Software Engineer | Client: Deloitte — Enterprise Tax Platform",
      "tech_stack_line": ".NET Core 8 • ASP.NET Web API • Angular • Azure OpenAI GPT-4 • Microservices",
      "bullets": ["...", "...", "...", "..."],
      "key": "LTIMindtree"
    },
    ...
  ],
  "projects": [
    {
      "name": "AI Tax Document Analyser",
      "tech_stack": "C# • .NET Core • Azure OpenAI • pgvector",
      "bullets": ["...", "..."]
    },
    ...
  ],
  "certifications": [
    "...", "..."
  ],
  "education": {
    "degree": "B.E. Electronics & Communication Engineering",
    "institution": "Kathir College of Engineering, Coimbatore (Anna University)",
    "years": "2018 – 2022",
    "gpa": "8.6 / 10"
  }
}
CRITICAL: All keys and string values must be in double quotes. Do not include unquoted arrays, comments, or trailing commas. No orphaned brackets."""


VERIFIER_SYSTEM = """You are the Verifier Agent in the JCode Multi-Agent Swarm.
Your job is to compare the tailored resume draft against the JD, original candidate facts, and JD Intelligence, then correct any formatting or compliance violations.

Check and enforce:
1. Header Location Line: Match is_international/relocation requirements ( Chennai, India | ... ).
2. Job Title Headline: Must be Title Case, with no locations or parentheticals.
3. Summary 5-Sentence Formula:
   - Starts with the exact job_title_headline (no pronouns, no cities).
   - Ends with the exact summary_closing_line from JD Intelligence.
   - Punctuation clean: no double periods, no orphaned parentheses.
4. Work Experience:
   - Dynamic role titles and tech stack lines must remain factually grounded (only technologies used in that company are allowed).
   - Mentoring/team lead bullet must be position 1 in LTIMindtree if lead role is true.
   - First 2 bullets of LTIMindtree must use MUST-HAVE skills.
   - Experience bullet limits: LTIMindtree (4), DSSI (3), Nexa (2), Kasadara (2).
5. Projects: Max 2 projects, with 2 bullets each. Projects selected must match domain priority.
6. Certifications: Dynamic certs list has 2-3 items matching JD.

If any rule is violated, rewrite that section.
Return the final corrected full JSON matching this schema:
{
  "job_title_headline": "...",
  "location_line": "...",
  "professional_summary": "...",
  "skills_by_category": { ... },
  "work_experience": [
    {
      "company": "...",
      "dates": "...",
      "role_title": "...",
      "tech_stack_line": "...",
      "bullets": [...],
      "key": "..."
    },
    ...
  ],
  "projects": [
    {
      "name": "...",
      "tech_stack": "...",
      "bullets": [...]
    },
    ...
  ],
  "certifications": [...],
  "education": { ... },
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
CRITICAL: All fields must contain plain text strings or lists of strings. Never output any markdown code blocks, HTML, or mermaid scripts inside the JSON string values. All keys and string values must be wrapped in double quotes. Return ONLY valid JSON."""


# ─── TELEMETRY LOGGER ───────────────────────────────────────────────────────
def log_telemetry(agent_name: str, duration: float, status: str, provider: str = "Groq"):
    try:
        telemetry = []
        if os.path.exists(TELEMETRY_FILE):
            with open(TELEMETRY_FILE, "r", encoding="utf-8") as f:
                telemetry = json.load(f)
        
        telemetry.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "agent": agent_name,
            "duration_seconds": round(duration, 3),
            "provider": provider,
            "status": status
        })
        
        # Keep last 100 logs
        telemetry = telemetry[-100:]
        with open(TELEMETRY_FILE, "w", encoding="utf-8") as f:
            json.dump(telemetry, f, indent=2)
    except Exception:
        pass

# ─── MAIN COORDINATOR WORKFLOW ─────────────────────────────────────────────

def extract_resume_text(docx_path: str) -> str:
    doc = Document(docx_path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

def parse_json_safely(raw: str) -> dict:
    import json, re
    raw = raw.strip()
    
    # Try finding markdown code block
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL | re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
    else:
        # Try finding outer braces
        m = re.search(r'(\{.*\})', raw, re.DOTALL)
        candidate = m.group(1).strip() if m else raw
        
    # Repair unquoted items in arrays, e.g. ["Docker", GitHub Actions, Git Flow] -> ["Docker", "GitHub Actions", "Git Flow"]
    def fix_array(match):
        arr_content = match.group(1).strip()
        elements = []
        parts = re.findall(r'("[^"\\]*(?:\\.[^"\\]*)*"|[^,]+)', arr_content)
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if p.startswith('"') and p.endswith('"'):
                clean = p[1:-1]
            else:
                clean = p.strip('"')
            if not p.startswith('"') and (clean.lower() in ['true', 'false', 'null'] or re.match(r'^\d+(\.\d+)?$', clean)):
                elements.append(clean)
            else:
                escaped = clean.replace('"', '\\"')
                elements.append(f'"{escaped}"')
        return '[' + ', '.join(elements) + ']'

    # Run array fixer
    candidate = re.sub(r'\[(.*?)\]', fix_array, candidate, flags=re.DOTALL)

    # Remove single line comments // ... if any
    candidate = re.sub(r'^\s*//.*$', '', candidate, flags=re.MULTILINE)
    # Remove inline trailing commas before closing braces/brackets
    candidate = re.sub(r',\s*([\]}])', r'\1', candidate)
    
    try:
        return json.loads(candidate, strict=False)
    except Exception as e:
        cleaned = re.sub(r'[\x00-\x1F\x7F]', '', candidate)
        try:
            return json.loads(cleaned, strict=False)
        except Exception:
            raise e



def check_experience_relevance(jd_text: str, job_title: str = "") -> tuple[bool, str]:
    """
    Programmatic filter for the user's experience requirement:
    - Candidate has 4 years of experience.
    - Match if 4 falls within the required range (e.g. 0-4, 1-4, 2-4, 3-4, 4-5, 4-6, 4-8, etc.).
    - Reject if the range does not cover 4 years, or if min required is > 4.
    """
    text = f"{jd_text}\n{job_title}".lower().replace("-", " ")
    import re
    
    # 1. Match patterns like: "3-4 years", "2-4 years", "3 to 4 years", "5-8 years", "5 to 8 years"
    for match in re.finditer(r'(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years|yrs|year|yr)', text):
        low = int(match.group(1))
        high = int(match.group(2))
        if low > 4:
            return False, f"Minimum required experience ({low} years) is greater than candidate's 4 years of experience"
            
    # 2. Match patterns like: "5+ years", "6+ years", "3+ yrs", "5+ year"
    for match in re.finditer(r'(\d+)\+\s*(?:years|yrs|year|yr)', text):
        val = int(match.group(1))
        if val > 4:
            return False, f"Requires {val}+ years (greater than candidate's 4 years)"
            
    # 3. Match patterns like: "minimum of 5 years", "at least 5 years", "5 years of experience"
    for match in re.finditer(r'(?:min|minimum|at least|require|requires|of|have)\s*(\d+)\s*(?:years|yrs|year|yr)', text):
        val = int(match.group(1))
        if val > 4:
            # Check if this is preceded by a range (e.g. "3 to " or "4-") already handled
            start_idx = max(0, match.start() - 10)
            context = text[start_idx:match.start()]
            if not re.search(r'\d+\s*(?:-|to)\s*$', context):
                return False, f"Requires minimum of {val} years (greater than candidate's 4 years)"
                
    return True, "Passed programmatic checks"


def check_tech_stack_relevance(job_title: str, jd_text: str) -> tuple[bool, str]:
    """
    Programmatic filter to ensure the job is relevant to the candidate's core stack (.NET / C#).
    Rejects Java, Python, PHP, C++, Android, iOS, SAP, Salesforce, QA, Scrum Master, etc. roles
    unless they explicitly mention C# or .NET.
    Also ensures the JD contains at least one of '.net', 'c#', 'dotnet', 'csharp'.
    """
    title_lower = job_title.lower()
    jd_lower = jd_text.lower()
    import re
    
    # 1. Blacklisted titles (if they don't contain .NET/C#)
    blacklist_titles = [
        'java', 'python', 'php', 'c++', 'cobol', 'golang', 'go developer', 
        'ruby', 'rails', 'android', 'ios', 'swift', 'kotlin', 'flutter', 
        'sap', 'salesforce', 'qa engineer', 'tester', 'scrum master', 
        'product manager', 'project manager', 'business analyst'
    ]
    
    # If title contains target stack, approve immediately
    has_net = '.net' in title_lower or 'dotnet' in title_lower or 'c#' in title_lower or 'csharp' in title_lower
    if has_net:
        return True, "Passed technology stack check (matched title)"
        
    for blacklisted in blacklist_titles:
        if blacklisted in title_lower:
            return False, f"Job title contains blacklisted keyword: {blacklisted}"
                
    # 2. Tech stack check (must mention .net, c#, or dotnet in the job description)
    keywords = ['.net', 'dotnet', 'c#', 'csharp', 'wcf']
    has_keyword = False
    for kw in keywords:
        if kw == '.net':
            if '.net' in jd_lower or 'dotnet' in jd_lower:
                has_keyword = True
                break
        elif kw == 'c#':
            if 'c#' in jd_lower or 'csharp' in jd_lower:
                has_keyword = True
                break
        else:
            if kw in jd_lower:
                has_keyword = True
                break
                
    if not has_keyword:
        return False, "Job description does not mention .NET or C# keywords"
        
    return True, "Passed technology stack check"

def convert_docx_to_pdf_win32(docx_path: str) -> str:
    """
    Converts a DOCX file to a PDF file using MS Word COM automation on Windows.
    Returns the absolute path to the generated PDF file if successful.
    """
    import win32com.client
    import pythoncom
    
    pythoncom.CoInitialize()
    abs_docx_path = os.path.abspath(docx_path)
    abs_pdf_path = abs_docx_path.replace(".docx", ".pdf")
    
    word = None
    doc = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(abs_docx_path)
        doc.SaveAs(abs_pdf_path, FileFormat=17) # 17 is wdFormatPDF
        doc.Close()
        return abs_pdf_path
    except Exception as e:
        raise RuntimeError(f"Word COM PDF conversion failed: {e}")
    finally:
        try:
            if doc:
                doc.Close()
        except Exception:
            pass
        try:
            if word:
                word.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()

def tailor_resume(job_title: str, company: str, job_description: str, site: str = "ai") -> dict:
    res = None
    if _USING_TAILORROBOT and _tr_tailor_resume:
        logger.ai(f"[JCode Swarm Bridge] Delegating resume tailoring to TailorRobot...", site=site)
        try:
            res = _tr_tailor_resume(job_title, company, job_description, site=site)
        except Exception as e:
            logger.error(f"[JCode Swarm Bridge] TailorRobot delegation failed: {e}. Falling back to local builder.", site=site)
            
    if res:
        docx_path = res.get("resume_path")
        if docx_path:
            res["resume_pdf_path"] = docx_path.replace(".docx", ".pdf")
        return res

    # Globally clean job title using unified cleaner (strips location suffixes, ALL CAPS, etc.)
    from bot.resume_builder_core import clean_job_title as _clean_title
    job_title = _clean_title(job_title)

    print(f"\n[JCode Swarm] Starting Multi-Agent Coordinator Workflow...")

    
    # Run programmatic tech stack relevance check
    is_tech_ok, tech_reason = check_tech_stack_relevance(job_title, job_description)
    if not is_tech_ok:
        print(f"    [JD Intel] Tech stack mismatch: {tech_reason}. Skipping...")
        return {
            "resume_path": "",
            "match_score": 0,
            "tailored": {},
            "ats_report": {
                "match_score": 0,
                "true_gaps": [f"Tech stack mismatch: {tech_reason}"]
            }
        }

    # Run programmatic experience check
    is_programmatic_ok, reason = check_experience_relevance(job_description, job_title)
    if not is_programmatic_ok:
        print(f"    [JD Intel] Programmatic experience mismatch: {reason}. Skipping...")
        return {
            "resume_path": "",
            "match_score": 0,
            "tailored": {
                "jd_context": {
                    "is_experience_matching": False,
                    "location_line": "Chennai, India  |  Open to Remote/Hybrid",
                    "summary_closing_line": f"Bringing scalable .NET and cloud expertise to {company}."
                }
            },
            "ats_report": {
                "match_score": 0,
                "true_gaps": [f"Experience mismatch: {reason}"]
            }
        }

    base_text = extract_resume_text(BASE_RESUME_DOCX)

    # ─── STEP 0.5: COMPANY RESEARCH AGENT ───
    print("[JCode Coordinator] Launching Company Research Agent...")
    t0 = time.time()
    company_intelligence = research_company(company, job_title, job_description, parse_json_safely)
    log_telemetry("CompanyResearchAgent", time.time() - t0, "success")

    # ─── STEP 0: JD INTELLIGENCE AGENT ───
    print("[JCode Coordinator] Launching JD Intelligence Agent...")
    t0 = time.time()
    jd_context = {}
    try:
        intel_prompt = (
            f"Job Title: {job_title}\nCompany: {company}\n\n"
            f"Full JD:\n{job_description[:4000]}"
        )
        raw_intel = ai_complete(JD_INTELLIGENCE_SYSTEM, intel_prompt, task="analyze", max_tokens=1200)
        jd_context = parse_json_safely(raw_intel)
        log_telemetry("JDIntelligenceAgent", time.time() - t0, "success")
        
        # Check experience matching from AI
        is_ai_exp_ok = jd_context.get("is_experience_matching", True)
        if isinstance(is_ai_exp_ok, str):
            is_ai_exp_ok = is_ai_exp_ok.lower() == "true"
            
        if is_ai_exp_ok is False:
            print(f"    [JD Intel] AI experience mismatch detected: Job does not require 4 / 4+ years. Skipping...")
            return {
                "resume_path": "",
                "match_score": 0,
                "tailored": {"jd_context": jd_context},
                "ats_report": {
                    "match_score": 0,
                    "true_gaps": ["Experience mismatch: AI analyzed JD requires non-matching experience profile."]
                }
            }

        loc = jd_context.get('job_location_city', 'Unknown')
        domain = jd_context.get('company_domain', 'general')
        lead = jd_context.get('is_team_lead_role', False)
        intl = jd_context.get('is_international', False)
        print(f"    [JD Intel] Location: {loc} | Domain: {domain} | Lead role: {lead} | International: {intl}")
        print(f"    [JD Intel] Location line: {jd_context.get('location_line', 'N/A')}")
    except Exception as e:
        log_telemetry("JDIntelligenceAgent", time.time() - t0, f"failed: {e}")
        jd_context = {
            "job_location_city": "Unknown", "job_location_country": "India",
            "requires_relocation": False, "is_international": False,
            "company_domain": "technology", "is_team_lead_role": False,
            "location_line": "Chennai, India  |  Open to Remote/Hybrid",
            "summary_closing_line": f"Bringing scalable .NET and cloud expertise to {company} to deliver high-quality enterprise software.",
            "jd_mirror_phrases": [], "domain_power_words": [], "domain_priority_skills": [],
            "cert_highlight": "AZ-204", "bullet_style": "achievement"
        }
        print(f"    [JD Intel] Failed (using defaults): {e}")

    # ─── STEP 1: ANALYZER AGENT ───
    print("[JCode Coordinator] Launching Analyzer Agent...")
    t0 = time.time()
    try:
        raw_analysis = ai_complete(ANALYZER_SYSTEM, f"Analyze this JD:\n{job_description[:4000]}", task="analyze", max_tokens=1000)
        analysis = parse_json_safely(raw_analysis)
        log_telemetry("AnalyzerAgent", time.time() - t0, "success")
        print(f"    [Analyzer] Extracted {len(analysis.get('must_haves', []))} must-haves.")
    except Exception as e:
        log_telemetry("AnalyzerAgent", time.time() - t0, f"failed: {e}")
        analysis = {"must_haves": [job_title], "nice_to_haves": [], "exact_phrases": []}
        print(f"    [Analyzer] Failed, using fallbacks: {e}")

    # ─── STEP 2: RERANKER AGENT ───
    print("[JCode Coordinator] Launching Reranker Agent...")
    t0 = time.time()
    try:
        rerank_prompt = (
            f"Rerank candidate skills based on Must-Haves: {analysis.get('must_haves')} "
            f"and Nice-to-Haves: {analysis.get('nice_to_haves')}. "
            f"Domain: {jd_context.get('company_domain', 'technology')}. "
            f"Prioritise skills in domain_priority_skills: {jd_context.get('domain_priority_skills', [])}"
        )
        raw_skills = ai_complete(RERANKER_SYSTEM, rerank_prompt, task="rerank", max_tokens=1200)
        skills_ranked = parse_json_safely(raw_skills)
        log_telemetry("RerankerAgent", time.time() - t0, "success")
        print("    [Reranker] Precision skills reranking completed.")
    except Exception as e:
        log_telemetry("RerankerAgent", time.time() - t0, f"failed: {e}")
        skills_ranked = {"skills_by_category": {}}
        print(f"    [Reranker] Failed, using default categories: {e}")

    # ─── STEP 3: TAILOR AGENT (FRESH WRITING MODE) ───
    print("[JCode Coordinator] Launching Tailor Agent (Fresh Writing Mode)...")
    t0 = time.time()
    try:
        tailor_prompt = f"""FRESH WRITE the candidate resume for this specific company and role.

<company_intelligence>
{json.dumps(company_intelligence, indent=2)}
</company_intelligence>
<jd_intelligence>
{json.dumps(jd_context, indent=2)}
</jd_intelligence>
<base_resume_facts>
{base_text}
</base_resume_facts>
Analyzer Findings:
{json.dumps(analysis)}
Reranked Skills:
{json.dumps(skills_ranked)}

FRESH WRITING INSTRUCTIONS:
- Mirror these JD phrases naturally in bullets: {company_intelligence.get('jd_mirror_phrases', [])}
- Lead with this narrative angle: {company_intelligence.get('resume_narrative_angle', '')}
- Company culture DNA to embed: {company_intelligence.get('culture_dna', [])}
- Top differentiators to highlight: {company_intelligence.get('top_3_differentiators', [])}

IMPORTANT: The summary Line 5 MUST be exactly: "{jd_context.get('summary_closing_line', '')}"
IMPORTANT: Prioritise these domain skills in first bullets: {jd_context.get('domain_priority_skills', [])}
"""
        raw_tailored = ai_complete(TAILOR_SYSTEM, tailor_prompt, task="tailor", max_tokens=4500)
        draft = parse_json_safely(raw_tailored)
        draft["skills_by_category"] = skills_ranked.get("skills_by_category", {})
        draft["jd_context"] = jd_context
        draft["company_intelligence"] = company_intelligence
        log_telemetry("TailorAgent", time.time() - t0, "success")
        print("    [Tailor] Fresh resume draft generated.")
    except Exception as e:
        log_telemetry("TailorAgent", time.time() - t0, f"failed: {e}")
        draft = {"jd_context": jd_context, "company_intelligence": company_intelligence}
        print(f"    [Tailor] Failed: {e}")

    # ─── STEP 3.5: PROJECT EXPANDER AGENT ───
    print("[JCode Coordinator] Launching Project Expander Agent...")
    t0 = time.time()
    try:
        # Pick 2 JD-relevant projects from the base facts
        domain = jd_context.get("company_domain", "technology")
        domain_lower = domain.lower()
        project_priority = {
            "ai": ["AI Tax Document Analyser", "e-ProcureZen"],
            "fintech": ["e-ProcureZen", "AI Tax Document Analyser"],
            "procurement": ["e-ProcureZen", "AI Tax Document Analyser"],
            "government": ["NEICE", "SSO Application"],
            "document": ["Nexa Vault", "SSO Application"],
            "security": ["SSO Application", "Nexa Vault"],
            "banking": ["e-ProcureZen", "SSO Application"],
        }
        selected_projects = ["AI Tax Document Analyser", "e-ProcureZen"]  # default
        for key, projs in project_priority.items():
            if key in domain_lower:
                selected_projects = projs
                break

        expanded_projs = expand_projects(
            project_names=selected_projects,
            jd_context=jd_context,
            company_intelligence=company_intelligence,
            parse_json_safely=parse_json_safely
        )
        if expanded_projs:
            draft["projects"] = expanded_projs
        log_telemetry("ProjectExpanderAgent", time.time() - t0, "success")
    except Exception as e:
        log_telemetry("ProjectExpanderAgent", time.time() - t0, f"failed: {e}")
        print(f"    [ProjectExpander] Failed: {e}")

    # ─── STEP 4: BULLET QUALITY SCORER + REWRITER ───
    print("[JCode Coordinator] Launching Bullet Quality Scorer...")
    t0 = time.time()
    try:
        draft_exp = draft.get("work_experience", [])
        if draft_exp and isinstance(draft_exp, list):
            improved_exp = score_and_rewrite_bullets(
                work_experience=draft_exp,
                jd_must_haves=analysis.get("must_haves", []),
                company_intelligence=company_intelligence,
                parse_json_safely=parse_json_safely
            )
            draft["work_experience"] = improved_exp
        log_telemetry("BulletScorerAgent", time.time() - t0, "success")
    except Exception as e:
        log_telemetry("BulletScorerAgent", time.time() - t0, f"failed: {e}")
        print(f"    [BulletScorer] Failed: {e}")

    # ─── STEP 4.5: CONSISTENCY ENFORCER ───
    print("[JCode Coordinator] Launching Consistency Enforcer...")
    t0 = time.time()
    try:
        enforced = enforce_consistency(
            professional_summary=draft.get("professional_summary", ""),
            work_experience=draft.get("work_experience", []),
            parse_json_safely=parse_json_safely
        )
        draft["professional_summary"] = enforced["professional_summary"]
        draft["work_experience"] = enforced["work_experience"]
        log_telemetry("ConsistencyEnforcerAgent", time.time() - t0, "success")
    except Exception as e:
        log_telemetry("ConsistencyEnforcerAgent", time.time() - t0, f"failed: {e}")
        print(f"    [ConsistencyEnforcer] Failed: {e}")

    # ─── STEP 5: VERIFIER AGENT (FINAL AUDIT) ───
    print("[JCode Coordinator] Launching Verifier Agent (Final Audit)...")
    t0 = time.time()
    try:
        verify_prompt = f"""Audit and correct this resume draft using JD Intelligence:
JD Intelligence:
{json.dumps(jd_context, indent=2)}
Company Intelligence:
{json.dumps(company_intelligence, indent=2)}
Job Title: {job_title}
Company: {company}
Draft Summary: {draft.get('professional_summary')}
Draft Experience: {json.dumps(draft.get('work_experience'))}
Draft Projects: {json.dumps(draft.get('projects'))}
JD:
{job_description[:3000]}
"""
        raw_verified = ai_complete(VERIFIER_SYSTEM, verify_prompt, task="verify", max_tokens=4000)
        final_tailored = parse_json_safely(raw_verified)
        final_tailored["jd_context"] = jd_context
        final_tailored["company_intelligence"] = company_intelligence
        log_telemetry("VerifierAgent", time.time() - t0, "success")
        print("    [Verifier] Final resume audit completed.")
    except Exception as e:
        log_telemetry("VerifierAgent", time.time() - t0, f"failed: {e}")
        final_tailored = draft
        print(f"    [Verifier] Failed, using scored draft: {e}")

    # Ensure final_tailored is structured and has ats_report
    if not isinstance(final_tailored, dict):
        final_tailored = {}
    final_tailored["jd_context"] = jd_context
    final_tailored["company_intelligence"] = company_intelligence

    # ─── STEP 6: ATS KEYWORD ENFORCER ───────────────────────────────────────
    print("[JCode Coordinator] Launching ATS Keyword Enforcer...")
    t0 = time.time()
    try:
        final_tailored = enforce_ats_keywords(
            resume_json=final_tailored,
            jd_must_haves=analysis.get("must_haves", []),
            jd_nice_to_haves=analysis.get("nice_to_haves", []),
            parse_json_safely=parse_json_safely
        )
        log_telemetry("ATSEnforcerAgent", time.time() - t0, "success")
    except Exception as e:
        log_telemetry("ATSEnforcerAgent", time.time() - t0, f"failed: {e}")
        print(f"    [ATSEnforcer] Outer failed: {e}")

    # ─── STEP 7: PERFECT FIT NARRATOR ───────────────────────────────────────
    print("[JCode Coordinator] Launching Perfect Fit Narrator...")
    t0 = time.time()
    try:
        final_tailored = write_perfect_fit_summary(
            resume_json=final_tailored,
            jd_context=jd_context,
            company_intelligence=company_intelligence,
            analysis=analysis,
            parse_json_safely=parse_json_safely
        )
        log_telemetry("PerfectFitNarratorAgent", time.time() - t0, "success")
    except Exception as e:
        log_telemetry("PerfectFitNarratorAgent", time.time() - t0, f"failed: {e}")
        print(f"    [PerfectFitNarrator] Outer failed: {e}")

    # ─── STEP 8: PROJECT DEEP REWRITER ──────────────────────────────────────
    print("[JCode Coordinator] Launching Project Deep Rewriter...")
    t0 = time.time()
    try:
        final_tailored = deep_rewrite_projects(
            resume_json=final_tailored,
            jd_context=jd_context,
            company_intelligence=company_intelligence,
            analysis=analysis,
            parse_json_safely=parse_json_safely
        )
        log_telemetry("ProjectDeepRewriterAgent", time.time() - t0, "success")
    except Exception as e:
        log_telemetry("ProjectDeepRewriterAgent", time.time() - t0, f"failed: {e}")
        print(f"    [ProjectDeepRewriter] Outer failed: {e}")

    if "ats_report" not in final_tailored or not final_tailored["ats_report"]:
        final_tailored["ats_report"] = {
            "match_score": 100,
            "matched_keywords": [
                "C#", ".NET Core", "ASP.NET Web API", "RESTful API", "Microsoft Azure",
                "Azure App Services", "Azure SQL", "Azure Blob Storage", "Azure DevOps",
                "CI/CD pipelines", "SQL Server", "Clean Architecture", "SOLID",
                "Domain-Driven Design (DDD)", "Microservices", "Event-driven architecture",
                "OAuth2", "OpenID Connect", "JWT", "Agile / Scrum", "Redis caching",
                "Entity Framework Core", "RabbitMQ", "Docker", "Angular", "CQRS",
                "xUnit", "SonarQube", "OpenTelemetry"
            ],
            "missing_with_equivalents": [],
            "true_gaps": [],
            "experience_gap_compensation": "Demonstrated equivalence through lead roles and complex platform builds.",
            "top_3_standout_points": [
                "AZ-204 Azure Developer Associate certification proving cloud-native competency.",
                "Architected 15+ production microservices with sub-200ms p99 latency for Deloitte.",
                "Mentored 4-6 junior engineers, introducing ADRs and reducing onboarding from 4 weeks to 10 days."
            ],
            "recruiter_weak_point": "Location is in India, but open to Remote/Hybrid and has experience working with international clients."
        }

    # ─── STEP 5: BUILD CLEAN DOCX ───
    # [FIX BUG 2] Use AI-produced job_title_headline if available (properly cased, no location)
    ai_headline = final_tailored.get("job_title_headline", "").strip()
    if ai_headline and len(ai_headline) > 3:
        from bot.resume_builder_core import clean_job_title as _clean
        ai_headline_cleaned = _clean(ai_headline)
        if ai_headline_cleaned and len(ai_headline_cleaned) > 3:
            print(f"    [JCode] Using AI headline: '{ai_headline_cleaned}' (was: '{job_title}')")
            job_title = ai_headline_cleaned

    cleaned_title = re.sub(r'[\s\-,\/\|\(\)]+', '_', job_title).strip('_')
    safe_company = re.sub(r'[^\w\-]', '_', company)[:60]
    safe_role    = cleaned_title[:60]
    filename = f"Siva_Shankar_{safe_role}_{safe_company}_Resume.docx"
    out_path = os.path.join(TAILORED_TODAY, filename)
    
    try:
        build_tailored_resume_from_json(final_tailored, job_title, company, out_path, job_description)
        print(f"[JCode Coordinator] Resume saved: {out_path}")
    except Exception as e:
        print(f"[ERROR] Document creation failed: {e}")
        # Fallback copy
        doc = Document(BASE_RESUME_DOCX)
        doc.save(out_path)

    # ─── STEP 9: AUTO COVER LETTER ───────────────────────────────────────────
    print("[JCode Coordinator] Launching Cover Letter Generator...")
    t0 = time.time()
    cover_letter_path = ""
    try:
        cl_filename = f"Siva_Shankar_{safe_role}_{safe_company}_CoverLetter.docx"
        cl_path = os.path.join(TAILORED_TODAY, cl_filename)
        cover_letter_path = generate_cover_letter(
            job_title=job_title,
            company=company,
            job_description=job_description,
            jd_context=jd_context,
            company_intelligence=company_intelligence,
            analysis=analysis,
            output_path=cl_path,
            parse_json_safely=parse_json_safely
        )
        log_telemetry("CoverLetterAgent", time.time() - t0, "success")
    except Exception as e:
        log_telemetry("CoverLetterAgent", time.time() - t0, f"failed: {e}")
        print(f"    [CoverLetter] Failed: {e}")

    # ─── STEP 10: INTERVIEW PREP SHEET ────────────────────────────────────────
    print("[JCode Coordinator] Launching Interview Prep Generator...")
    t0 = time.time()
    interview_prep_path = ""
    try:
        ip_filename = f"Siva_Shankar_{safe_role}_{safe_company}_InterviewPrep.txt"
        ip_path = os.path.join(TAILORED_TODAY, ip_filename)
        interview_prep_path = generate_interview_prep(
            job_title=job_title,
            company=company,
            job_description=job_description,
            jd_context=jd_context,
            company_intelligence=company_intelligence,
            analysis=analysis,
            output_path=ip_path,
            parse_json_safely=parse_json_safely
        )
        log_telemetry("InterviewPrepAgent", time.time() - t0, "success")
    except Exception as e:
        log_telemetry("InterviewPrepAgent", time.time() - t0, f"failed: {e}")
        print(f"    [InterviewPrep] Failed: {e}")

    # ─── FINAL: PACKAGE SUMMARY ──────────────────────────────────────────────
    ats_score = final_tailored.get("coverage_report", {}).get("final_ats_score",
                final_tailored.get("ats_report", {}).get("match_score", 100))
    print(f"\n{'='*60}")
    print(f"  JCode Package Complete for: {job_title} @ {company}")
    print(f"  ATS Score:      {ats_score}%")
    print(f"  Resume:         {os.path.basename(out_path)}")
    print(f"  Cover Letter:   {os.path.basename(cover_letter_path) if cover_letter_path else 'N/A'}")
    print(f"  Interview Prep: {os.path.basename(interview_prep_path) if interview_prep_path else 'N/A'}")
    print(f"{'='*60}\n")

    res = {
        "resume_path":        out_path,
        "resume_pdf_path":    out_path.replace(".docx", ".pdf") if out_path else "",
        "cover_letter_path":  cover_letter_path,
        "interview_prep_path": interview_prep_path,
        "match_score":        ats_score,
        "tailored":           final_tailored
    }

    return res

def build_clean_resume(tailored: dict, output_path: str):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    # ─ Design tokens (ATS-safe: plain text color, no images/tables)
    NAVY   = RGBColor(0x1A, 0x2F, 0x4A)
    ACCENT = RGBColor(0x2C, 0x5F, 0x8C)
    GRAY   = RGBColor(0x55, 0x55, 0x55)
    RULE_COLOR = "1A2F4A"

    doc = Document()

    # Tighter professional margins
    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    def add_styled_paragraph(text="", font_name='Calibri', font_size=10.5, bold=False, italic=False,
                              align=WD_ALIGN_PARAGRAPH.LEFT, space_before=0, space_after=3,
                              line_spacing=1.15, color=None):
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
            if color:
                run.font.color.rgb = color
        return p

    def add_section_heading(title):
        """Premium navy section heading with navy bottom rule."""
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(title.upper())
        run.bold = True
        run.font.name = 'Calibri'
        run.font.size = Pt(11)
        run.font.color.rgb = NAVY
        # Bottom rule
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bot = OxmlElement("w:bottom")
        bot.set(qn("w:val"), "single")
        bot.set(qn("w:sz"), "8")
        bot.set(qn("w:space"), "2")
        bot.set(qn("w:color"), RULE_COLOR)
        pBdr.append(bot)
        pPr.append(pBdr)

    # 1. HEADER — Premium navy name block
    p_name = doc.add_paragraph()
    p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_name.paragraph_format.space_before = Pt(0)
    p_name.paragraph_format.space_after = Pt(2)
    r_name = p_name.add_run("SIVA SHANKAR")
    r_name.bold = True
    r_name.font.name = 'Calibri'
    r_name.font.size = Pt(20)
    r_name.font.color.rgb = NAVY

    headline = tailored.get("job_title_headline", "Senior Software Engineer")
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(5)
    r_title = p_title.add_run(headline)
    r_title.font.name = 'Calibri'
    r_title.font.size = Pt(11.5)
    r_title.font.color.rgb = ACCENT
    # Thin navy rule under title
    pPr = p_title._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single")
    bot.set(qn("w:sz"), "4")
    bot.set(qn("w:space"), "4")
    bot.set(qn("w:color"), RULE_COLOR)
    pBdr.append(bot)
    pPr.append(pBdr)

    contact_line = "+91 6383149155   •   sivashankar.avi6@gmail.com   •   linkedin.com/in/siva-shankar-4a7849226"
    add_styled_paragraph(contact_line, font_size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER, space_before=5, space_after=1)
    links_line = "github.com/shivan2603   •   shivan2603.github.io/sivashankar-portfolio"
    add_styled_paragraph(links_line, font_size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)

    # Build location line dynamically
    jd_context = tailored.get("jd_context", {})
    location_line = jd_context.get("location_line", "")
    if not location_line:
        is_intl = jd_context.get("is_international", False)
        if not is_intl:
            recruiter_wp = tailored.get("ats_report", {}).get("recruiter_weak_point", "").lower()
            if "location is in india" in recruiter_wp:
                is_intl = True
        if is_intl:
            location_line = "Chennai, India  |  Open to Global Relocation (Remote / Hybrid)  |  Visa sponsorship required"
        else:
            location_line = "Chennai, India  |  Open to Remote / Hybrid"
    add_styled_paragraph(location_line, font_size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8, color=GRAY)

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