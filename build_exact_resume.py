"""
build_exact_resume.py  v2
─────────────────────────────────────────────────────────────────
Resume: Senior Software Engineer (.Net, Cloud) @ Exact — FIXED
Fixes applied via resume_builder_core:
  All 10 ATS issues from the review are permanently resolved.
─────────────────────────────────────────────────────────────────
"""
import sys, os, requests
sys.stdout.reconfigure(encoding="utf-8")

from bot.resume_builder_core import (
    ResumeConfig, build_resume_docx, ats_self_check,
    select_resume_design, quality_gate_check
)

# ─── CONFIG ───────────────────────────────────────────────────
OUTPUT_DIR  = r"E:\SivaShankar\aTresume\17-06-2026"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "Siva_Shankar_Senior_SE_Exact_NET_Cloud_v2.docx")

JOB_TITLE   = "Senior Software Engineer (.Net, Cloud)"   # [F4] exact JD title
COMPANY     = "Exact"

# ─── LOAD API KEYS ────────────────────────────────────────────
OPENROUTER_KEY = GROQ_KEY = None
env_path = r"E:\SivaShankar\tailorrobot\.env"
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("OPENROUTER_API_KEY="):
                OPENROUTER_KEY = line.split("=",1)[1].strip().strip('"\'')
            elif line.startswith("GROQ_API_KEY="):
                GROQ_KEY = line.split("=",1)[1].strip().strip('"\'')

# ─── JD TEXT ──────────────────────────────────────────────────
JD_TEXT = """
Senior / Software Engineer (.NET, Cloud) at Exact (Delft, Netherlands — Hybrid)

Exact provides cloud-based business software (ERP, accounting, CRM, HR) for 650,000+ SMB entrepreneurs.

MUST-HAVE:
- C# and .NET Core / .NET 6/7/8
- ASP.NET Web API / RESTful API development
- Microsoft Azure: App Services, Azure SQL, Blob Storage, DevOps
- CI/CD pipelines: Azure DevOps or GitHub Actions
- SQL Server — relational database design and query optimization
- Clean Architecture / SOLID / Domain-Driven Design (DDD)
- Microservices and event-driven architecture
- OAuth2 / OpenID Connect / JWT
- Agile / Scrum, code reviews, mentoring junior developers
- Application performance optimization, Redis caching

NICE-TO-HAVE:
- Entity Framework Core, RabbitMQ / Azure Service Bus
- Docker / containerization, Angular or React
- CQRS / Event Sourcing, xUnit / NUnit
- SonarQube, OpenTelemetry / observability

KEY JD PHRASES (use verbatim):
- "PaaS services and cloud deployment platforms"
- "improve, design, code and test"
- "international team environment"
"""

# ─── AI SUMMARY GENERATION ────────────────────────────────────
SYSTEM_PROMPT = f"""You are an expert ATS resume writer. Write a 5-line professional summary for this exact role.

RULES (all mandatory):
1. Line 1: Start with EXACT title: "{JOB_TITLE}" + years + top 3 JD keywords
2. Lines 2-3: 2 strongest QUANTIFIED achievements (use the real numbers below)
3. Line 4: Use these EXACT JD phrases naturally word-for-word:
   - "PaaS services and cloud deployment platforms"
   - "improve, design, code and test"
4. Line 5: End with: "Bringing scalable .NET and cloud expertise to {COMPANY} to help build world-class ERP and accounting software used by businesses globally."

Return ONLY the 5 plain text lines. No labels, no markdown, no JSON.
TOKEN RULE: Do NOT shorten or truncate. Write every line in full detail."""

USER_PROMPT = f"""JD: {JD_TEXT[:600]}

REAL ACHIEVEMENTS:
- LTIMindtree: 15+ .NET Core 8 microservices, sub-200ms p99 API response, 35% audit throughput improvement
- DSSI: 12+ microservices, 300+ RPS at 99.98% uptime SLA, 3x throughput via RabbitMQ, 99.5% Redis cache hit rate
- 4+ years experience, AZ-204 Azure Developer Associate certified
- Mentored 4-6 junior engineers, led code reviews, reduced onboarding from 4 weeks to 10 days

Write the 5-line summary now:"""


def call_groq(system: str, user: str) -> str:
    if not GROQ_KEY:
        raise Exception("No Groq key")
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": 800,
        "temperature": 0.15
    }
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      headers=headers, json=payload, timeout=45)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def call_openrouter(system: str, user: str) -> str:
    if not OPENROUTER_KEY:
        raise Exception("No OpenRouter key")
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/shivan2603",
        "X-Title": "TailorRobot"
    }
    for model in ["meta-llama/llama-3.3-70b-instruct:free", "google/gemma-2-9b-it:free"]:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                              headers=headers,
                              json={"model": model,
                                    "messages": [{"role":"system","content":system},
                                                 {"role":"user","content":user}],
                                    "max_tokens": 800, "temperature": 0.15},
                              timeout=60)
            r.raise_for_status()
            txt = r.json()["choices"][0]["message"]["content"].strip()
            if txt and len(txt) > 50:
                print(f"  [AI] OpenRouter: {model}")
                return txt
        except Exception as e:
            print(f"  [WARN] OpenRouter {model}: {e}")
    raise Exception("All OpenRouter models failed")


def generate_summary() -> str:
    try:
        txt = call_openrouter(SYSTEM_PROMPT, USER_PROMPT)
        print("  [AI] Summary from OpenRouter")
        return txt
    except Exception as e:
        print(f"  [WARN] OpenRouter: {e}")
    try:
        txt = call_groq(SYSTEM_PROMPT, USER_PROMPT)
        print("  [AI] Summary from Groq")
        return txt
    except Exception as e:
        print(f"  [WARN] Groq: {e}")

    # Deterministic fallback — all phrases enforced by resume_builder_core anyway
    return (
        f"{JOB_TITLE} with 4+ years of expertise in C#, .NET Core 8, ASP.NET Web API, "
        "Clean Architecture, and Microsoft Azure cloud-native application development. "
        "Architected 15+ production microservices for Deloitte's enterprise tax platform achieving "
        "sub-200ms p99 API response time across 10M+ records; engineered a system at DSSI handling "
        "300+ RPS at 99.98% uptime SLA validated under Grafana K6 with 500 concurrent users. "
        "Delivered PaaS services and cloud deployment platforms using Azure App Services, Azure DevOps "
        "CI/CD, Redis, RabbitMQ, OAuth2/OIDC — working across international, cross-functional team "
        "environments to improve, design, code and test high-throughput microservices at enterprise scale. "
        "AZ-204 Azure Developer Associate certified; mentored 4–6 engineers reducing onboarding from "
        "4 weeks to 10 days through structured ADRs and code review culture."
    )


# ─── BASE RESUME DATA ─────────────────────────────────────────
CANDIDATE = {
    "name": "SIVA SHANKAR",
    "phone": "+91 6383149155",
    "email": "sivashankar.avi6@gmail.com",
    "linkedin": "https://www.linkedin.com/in/siva-shankar-4a7849226/",
    "github": "https://github.com/shivan2603",
    "portfolio": "https://shivan2603.github.io/sivashankar-portfolio/",
    "location": "Chennai, India  |  Open to Remote / Hybrid",
}

# [F5] PaaS phrase is ENFORCED by resume_builder_core.validate_skills()
# Just list the Cloud skills naturally — the core will prepend PaaS entry
SKILLS = {
    "Backend": [
        ".NET Core 8 / .NET 7", "C#", "ASP.NET Web API", "RESTful APIs",
        "CQRS", "Clean Architecture", "Domain-Driven Design (DDD)", "SOLID Principles",
        "Microservices", "Entity Framework Core", "YARP Reverse Proxy",
        "Polly Circuit Breakers", "SignalR", "gRPC", "WCF"
    ],
    # [F5] validate_skills() will prepend: "PaaS (Azure App Services · Azure SQL · Azure Blob Storage) · Cloud Deployment Platforms"
    "Cloud & DevOps": [
        "Microsoft Azure", "Azure App Services", "Azure SQL / SQL Server",
        "Azure Blob Storage", "Azure DevOps (CI/CD YAML)", "Azure Service Bus",
        "Application Insights", "Azure Key Vault", "Azure OpenAI",
        "Azure Form Recognizer", "GitHub Actions", "Docker",
        "SonarQube", "OpenTelemetry"
    ],
    "Databases": [
        "SQL Server", "PostgreSQL", "Azure SQL", "Redis (Distributed Cache)",
        "pgvector", "LINQ Optimisation", "Stored Procedures", "Full-Text Indexing"
    ],
    "Security": [
        "OAuth2", "OpenID Connect (OIDC)", "JWT", "RBAC",
        "AES-256 Encryption", "PCI-DSS", "FIPS Compliance",
        "OWASP Top 10", "IP Whitelisting"
    ],
    "Messaging & Architecture": [
        "RabbitMQ", "Azure Service Bus", "Redis Pub/Sub",
        "Event-Driven Architecture", "Async Workflows"
    ],
    "Frontend": [
        "Angular 15+", "TypeScript", "RxJS", "NgRx/Redux",
        "Material-UI", "Vue.js", "React"
    ],
    "Testing": [
        "xUnit", "NUnit", "Moq", "Integration Testing",
        "TDD", "Grafana K6 Load Testing"
    ],
    "AI / ML": [
        "Azure OpenAI GPT-4", "Semantic Kernel", "Vector Embeddings",
        "pgvector", "Azure AI Search", "Prompt Engineering"
    ],
    "Methodology": [
        "Agile / Scrum", "Git Flow", "Code Reviews",
        "Architectural Decision Records (ADRs)", "Team Mentoring", "Sprint Planning"
    ],
}

JOBS = [
    {
        "company": "LTIMindtree",
        "dates": "Jun 2025 – Present",
        # [F4] No emoji in title
        "title": "Senior Software Engineer  |  Client: Deloitte — Enterprise Tax Platform",
        "tech": ".NET Core 8  •  ASP.NET Web API  •  Angular  •  Azure OpenAI GPT-4  •  Microservices  •  CQRS  •  pgvector  •  OpenTelemetry  •  Redis  •  SQL Server",
        "bullets": [
            # [F6] First 2 bullets hit top 2 MUST-HAVEs: .NET Core / ASP.NET Web API
            "Architected and deployed 15+ .NET Core 8 microservices following Clean Architecture, "
            "CQRS, and Domain-Driven Design (DDD) for Deloitte's enterprise tax platform — serving "
            "2M+ tax records with sub-200ms p99 API response time validated via OpenTelemetry distributed tracing.",

            "Engineered RESTful ASP.NET Web API contracts with versioning, Swagger/OpenAPI documentation, "
            "and xUnit integration tests — maintained 100% API contract stability across 8 quarterly "
            "releases for a platform processing 10M+ tax documents annually.",

            # [F6] 4-verb phrase is ENFORCED by resume_builder_core; included here natively too
            "Worked across the full engineering lifecycle to improve, design, code and test 30+ "
            "ASP.NET Core microservice endpoints — achieving sub-100ms p99 latency under peak "
            "Deloitte audit load, validated via OpenTelemetry distributed tracing.",

            "Built Azure DevOps YAML CI/CD pipelines with SonarQube quality gates and automated "
            "xUnit/NUnit test runs — achieved 98% pipeline success rate and reduced production "
            "defect rate by 40% across 6 quarterly releases.",

            "Implemented JWT + OAuth2/OIDC token-based authentication with RBAC and AES-256 "
            "field-level encryption for sensitive tax data — achieved OWASP Top 10 compliance "
            "across all 15+ API endpoints.",

            "Integrated Azure OpenAI GPT-4 + Semantic Kernel with pgvector semantic search over "
            "10M+ tax documents — achieved 35% improvement in audit reviewer throughput, replacing "
            "keyword search with vector-similarity retrieval at sub-200ms latency.",

            # [F7] international phrase injected here too
            "Led code reviews for a 6-member cross-functional team across international, "
            "cross-functional team environments; introduced Architectural Decision Records (ADRs) "
            "and clean-code standards — reduced new engineer onboarding from 4 weeks to 10 days.",
        ]
    },
    {
        "company": "DSSI Solutions India Pvt Ltd",
        "dates": "Nov 2024 – May 2025",
        "title": "Senior Software Engineer  |  Financial Procurement Platform",
        "tech": ".NET 7  •  Clean Architecture  •  CQRS  •  YARP Reverse Proxy  •  Docker  •  Azure App Services  •  RabbitMQ  •  Redis  •  JWT  •  AES-256  •  Agile/Scrum",
        "bullets": [
            "Architected 12+ production-grade microservices using .NET 7, Clean Architecture, and CQRS "
            "with YARP Reverse Proxy — system handles 300+ RPS at 99.98% uptime SLA, validated under "
            "Grafana K6 load testing with 500 concurrent users.",

            "Containerised all 12 services using Docker multi-stage builds and deployed on Azure App "
            "Services with zero-downtime rolling updates via Azure DevOps CI/CD (YAML) — achieved "
            "98% pipeline success rate and 65% reduction in Docker image sizes.",

            "Orchestrated RabbitMQ async messaging across 8 procurement microservices — improved "
            "system throughput by 3x under peak load vs synchronous HTTP chaining; implemented "
            "Polly circuit breakers preventing cascading failures.",

            "Built enterprise authentication layer with JWT + RBAC + IP Whitelisting and AES-256 "
            "encrypted API responses — reduced unauthorised access attempts by 72% and achieved "
            "PCI-DSS compliance for a financial procurement platform.",

            "Achieved 99.5% Redis Distributed Cache hit rate with 300ms average API response time "
            "using Generic Repository Pattern with Unit of Work — enabled 80% code reuse across "
            "all microservices.",

            "Mentored 4 junior engineers on .NET 7 Clean Architecture and CQRS; led Agile/Scrum "
            "ceremonies using Git Flow — reduced production bugs by 40% through SonarQube-enforced "
            "quality gates and structured code review processes.",
        ]
    },
    {
        "company": "Nexa Office InfoSystems LLP",
        "dates": "Jul 2024 – Nov 2024",
        "title": "Senior Software Engineer — Contract / Consultant  |  Enterprise Document Management",
        "tech": ".NET Core  •  ASP.NET Web API  •  Angular  •  Redux/NgRx  •  Docker  •  SQL Server  •  OAuth2/OIDC  •  Material-UI",
        "bullets": [
            "Decomposed a legacy monolithic DMS into 6 .NET Core microservices deployed via Docker — "
            "reduced deployment time from 2 hours to under 20 minutes and improved release frequency "
            "from monthly to weekly.",

            "Developed ASP.NET Web API integration endpoints connecting 3 third-party services with "
            "Swagger/OpenAPI documentation — eliminated 3 manual data-sync processes and reduced "
            "support tickets by 25% within 30 days of go-live.",

            "Designed and delivered enterprise-wide SSO using .NET MVC + Angular + OAuth2/OIDC — "
            "eliminated login friction for 500+ users across 8 internal applications and reduced "
            "authentication support tickets by 40%.",

            "Built Angular SPAs with Redux/NgRx state management and Material-UI with lazy loading — "
            "improved UI task-completion time by 30% across 500+ enterprise users.",
        ]
    },
    {
        "company": "Kasadara Technology Solutions",
        "dates": "Jul 2022 – Jun 2024",
        "title": "Software Engineer  |  US Government & SaaS Enterprise Platforms",
        "tech": ".NET Core  •  ASP.NET MVC  •  C#  •  Angular  •  Vue.js  •  Entity Framework Core  •  Go  •  WCF  •  Agile  •  FIPS Compliance",
        "bullets": [
            "Engineered 8+ Angular + ASP.NET MVC modules for the NEICE US Government health platform "
            "with RBAC and FIPS-compliant security protocols — achieving on-time delivery serving "
            "10,000+ government users with zero compliance breaches.",

            "Optimised SQL Server architecture via Entity Framework Core migrations, LINQ tuning, and "
            "indexed stored procedures — improved data retrieval efficiency by 30% across multi-tenant "
            "SaaS schemas handling high query volumes.",

            "Built FACILITEASY Asset Management Software (Vue.js + .NET + EF Core) with indexed "
            "stored procedures and no-tracking queries — achieved 30% improvement in report-generation "
            "speed across 200+ concurrent business users.",

            "Developed a real-time chat platform using Go + Angular + .NET Core + WebSockets + Redis "
            "Pub/Sub — supported 200+ concurrent connections at sub-50ms message-delivery latency "
            "via multi-instance Redis fanout architecture.",
        ]
    }
]

# [F9] Exactly 3 projects — most relevant to Exact JD (ERP/cloud/.NET)
PROJECTS = [
    {
        "name": "e-ProcureZen — AI-Enhanced B2B Procurement Platform",
        "tech": ".NET Core · ASP.NET Web API · Angular · YARP · RabbitMQ · Docker · Azure OpenAI · Azure Form Recognizer · Redis · JWT/OAuth2 · AES-256 · PCI-DSS",
        "bullets": [
            "Architected a cloud-native procurement platform with 12+ microservices on Azure App "
            "Services (PaaS) handling 300+ RPS at 99.98% uptime SLA; integrated Azure OpenAI for "
            "intelligent vendor recommendations and Azure Form Recognizer to eliminate 90% of manual "
            "invoice data entry.",
            "Achieved 40% lower API latency via YARP Reverse Proxy + Redis Distributed Caching; "
            "PCI-DSS compliant via JWT + OAuth2/OIDC + AES-256 encrypted responses — validated "
            "under Grafana K6 load tests with 500 concurrent users.",
        ]
    },
    {
        "name": "AI Tax Document Analyser — Semantic Search & LLM Summarisation Engine",
        "tech": "Azure OpenAI GPT-4 · .NET Core · pgvector · Azure AI Search · Semantic Kernel · OpenTelemetry · Application Insights",
        "bullets": [
            "Built an LLM-powered summarisation and anomaly-detection pipeline over 10M+ tax records "
            "at sub-200ms p99 response time; replaced keyword-based search with vector-similarity "
            "lookup achieving 35% improvement in audit reviewer throughput.",
            "Implemented OpenTelemetry distributed tracing with Application Insights dashboards — "
            "full observability across 15+ microservices with real-time alerting and SLA reporting.",
        ]
    },
    {
        "name": "Nexa Vault — Multi-Tenant Document Management System",
        "tech": ".NET Core · Angular · Azure Blob Storage · Redis · SQL Server Full-Text Index · AES-256 · Swagger/OpenAPI · RBAC · OAuth2/OIDC",
        "bullets": [
            "Multi-tenant enterprise DMS managing 50,000+ files with version control, RBAC vault "
            "access, and full audit-trail logging; achieved 35% faster document retrieval via "
            "SQL Server full-text indexing + Redis metadata caching.",
            "Delivered enterprise-wide SSO using .NET MVC + Angular + OAuth2/OIDC integrating "
            "8 internal applications — reduced authentication support tickets by 40% and login "
            "latency to sub-200ms under concurrent load.",
        ]
    }
]

CERTIFICATIONS = [
    # AZ-204 listed first — directly matches JD
    "Microsoft Azure Developer Associate (AZ-204)  |  Microsoft  |  March 18, 2024  |  Credential ID: 1KA2C7-B08024",
    "Top Performer Award  |  Nexa Office InfoSystems LLP  |  2024  |  Outstanding delivery and technical leadership",
]

EDUCATION = {
    "degree": "B.E. Electronics & Communication Engineering",
    "institution": "Kathir College of Engineering, Coimbatore (Anna University)",
    "years": "2018 – 2022",
    "gpa": "8.6 / 10"
}


# ─── MAIN ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  TAILOR ROBOT v2 — Senior SE (.NET, Cloud) @ Exact")
    print("  All 10 ATS fixes applied via resume_builder_core")
    print("=" * 65)

    print("\n[Step 1] Generating AI-powered Professional Summary...")
    summary = generate_summary()
    print(f"\n  SUMMARY:\n  {summary[:250]}...\n")

    print("[Step 2b] Auto-selecting design for this JD + location...")
    design = select_resume_design(JD_TEXT, COMPANY, "Eindhoven Netherlands")
    print(f"  → Design {design} selected")

    print("[Step 2c] Running 4-stage quality gate...")
    issues = quality_gate_check(summary, JOBS, PROJECTS, COMPANY)
    if issues:
        print(f"  [QUALITY GATE] {len(issues)} issue(s):")
        for issue in issues:
            print(f"    {issue}")
    else:
        print("  [QUALITY GATE] ✅ Zero issues — world-class content confirmed")

    print("[Step 3] Building ATS-safe DOCX (all 10 fixes enforced)...")
    config = ResumeConfig(
        job_title=JOB_TITLE,
        company=COMPANY,
        output_file=OUTPUT_FILE,
        jd_text=JD_TEXT,
        summary=summary,
        skills=SKILLS,
        jobs=JOBS,
        projects=PROJECTS,
        certifications=CERTIFICATIONS,
        education=EDUCATION,
        candidate=CANDIDATE,
        design=design,
    )
    output_path = build_resume_docx(config)

    print("[Step 4] Running ATS self-check & match report...")
    ats_self_check(config, output_path)
