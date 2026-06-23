"""
resume_research_agent.py — 1000x Resume Intelligence Module
════════════════════════════════════════════════════════════
Adds 4 advanced AI agents to the resume tailoring pipeline:

  Agent 0.5: Company Research Agent
    - Deep-researches company tech stack, culture, product domain
    - Extracts JD language to mirror in resume bullets

  Agent 1.5: Project Expander Agent
    - Takes project name + tech tags → writes full architecture rationale
    - Produces measurable impact bullets from scratch

  Agent 4.5: Bullet Quality Scorer + Rewriter
    - Grades every bullet 1–10 on specificity + impact + JD alignment
    - Rewrites bullets scoring < 7 to be sharper and metric-driven

  Agent 4.75: Consistency Enforcer
    - Fixes verb tenses (past for old roles, present for current)
    - Removes filler phrases: "responsible for", "assisted in", "helped with"
    - Deduplicates metrics so no number appears twice across the resume
"""

import re
import json
from bot.ai_router import ai_complete

# ─── SYSTEM PROMPTS ─────────────────────────────────────────────────────────

COMPANY_RESEARCH_SYSTEM = """You are the Company Research Agent in the JCode Multi-Agent Swarm.
Your job is to analyse the Job Description and extract deep intelligence about the COMPANY and ROLE
that will make this candidate's resume sound perfectly tailored — as if they studied this company
for weeks before applying.

Analyse:

1. COMPANY TECH STACK: What technologies does this company actually use?
   - Read between the lines: e.g. "Azure-first" companies use Functions, APIM, CosmosDB
   - "Legacy modernization" companies use .NET Framework → .NET Core migration patterns
   - "Fintech" companies care about PCI-DSS, audit trails, idempotency

2. COMPANY CULTURE DNA: Pick 4-5 culture signals from the JD
   - Keywords like: "ownership", "delivery-focused", "collaborative", "customer-first", "clean code"
   - These become the tone of the resume bullets (e.g. "ownership" → "Led end-to-end delivery of...")

3. COMPETITIVE DIFFERENTIATORS: What would make THIS candidate stand out for THIS company?
   - Based on what the JD values most, what are the top 3 things to lead with?
   - e.g. If JD values "performance optimization" → lead with sub-100ms latency bullet
   - If JD values "team leadership" → lead with mentoring + ADR bullet

4. JD EXACT PHRASES TO MIRROR: Pick the 4 most distinctive phrases from the JD
   - These are phrases NOT everyone uses — specific to this company's language
   - e.g. "mission-critical enterprise platform" or "cloud-native microservices at scale"
   - The resume should echo these exact phrases naturally in summary and bullets

5. RESUME ANGLE: Based on all above, what is the #1 narrative angle?
   - e.g. "Position as a performance-obsessed backend engineer"
   - Or: "Position as a cloud-native architect with enterprise-scale delivery experience"

Return ONLY valid JSON (no markdown):
{
  "company_tech_inference": ["Azure Functions", "Cosmos DB", "APIM", "Docker"],
  "company_domain_detail": "Cloud-native B2B SaaS serving enterprise procurement teams",
  "culture_dna": ["ownership", "delivery-focused", "collaborative", "pragmatic"],
  "top_3_differentiators": [
    "Sub-100ms API latency at enterprise scale using Redis + OpenTelemetry",
    "Led CQRS microservices architecture across 12+ services in production",
    "Azure-certified developer (AZ-204) with hands-on cloud-native delivery"
  ],
  "jd_mirror_phrases": [
    "mission-critical enterprise platform",
    "cloud-native microservices at scale",
    "deliver measurable business outcomes",
    "high-performance distributed systems"
  ],
  "resume_narrative_angle": "Position as a performance-obsessed cloud-native .NET engineer who delivers measurable enterprise outcomes",
  "opening_power_verb": "Architected",
  "summary_tone": "achievement-first with specific metrics"
}"""


PROJECT_EXPANDER_SYSTEM = """You are the Project Expander Agent in the JCode Multi-Agent Swarm.
Your job is to take a project NAME and its technology tags, then write a DEEP, FRESH project entry
that demonstrates architectural thinking and measurable impact — as if the candidate is presenting
at a technical interview.

You will receive:
- Project name and tech stack
- JD context (what the company values)
- Company intelligence (what tech they use, their culture)

Your output for EACH project must include:
1. A crisp one-line description of WHAT the project does and WHY it exists
2. An architecture rationale bullet: WHY those specific tech choices were made
   (e.g. "Selected pgvector over managed vector DB to keep tax data within security boundary")
3. An impact bullet: measurable outcome using numbers, percentages, or scale
   (e.g. "Reduced document lookup time from 2.3s to 190ms — a 92% improvement")
4. A JD-alignment bullet: maps the project to the JD's specific requirements

CRITICAL RULES:
- ONLY use technologies listed in the project's tech_stack — never add new ones
- ALL metrics must come from the CANDIDATE BASE FACTS — never invent numbers
- Architecture rationale must sound like a senior engineer explaining a real trade-off
- Use strong action verbs: Architected, Engineered, Designed, Implemented, Deployed

Return ONLY valid JSON:
{
  "expanded_projects": [
    {
      "name": "Project Name",
      "tech_stack": "C# · .NET Core · Azure OpenAI · pgvector · Semantic Kernel",
      "description": "AI-powered tax document analysis system that automates semantic extraction of structured data from unstructured legal documents.",
      "bullets": [
        "Deployed local pgvector indexing over managed vector DB to keep sensitive tax data strictly within the security boundary, eliminating cross-network query overhead.",
        "Engineered Semantic Kernel orchestrations with Azure OpenAI GPT-4 to extract structured tax data, reducing manual review time by 60% across 1,000+ weekly document submissions.",
        "Implemented OpenTelemetry context propagation to trace LLM orchestration latency end-to-end, achieving sub-200ms p99 semantic lookup performance."
      ]
    }
  ]
}"""


BULLET_SCORER_SYSTEM = """You are the Bullet Quality Scorer and Rewriter Agent in the JCode Multi-Agent Swarm.
Your job is to audit every bullet point across all work experience sections and rewrite any that are weak.

SCORING CRITERIA (1–10 per bullet):
- Specificity (1–3): Does it contain a number, %, or concrete scale?
  (3 = has specific metric, 2 = has scale without number, 1 = vague/generic)
- Impact (1–4): Is the OUTCOME stated? Does it show business value?
  (4 = clear outcome + business value, 3 = outcome only, 2 = task only, 1 = responsibility description)
- JD Alignment (1–3): Does it use at least one of the JD's must-have keywords?
  (3 = multiple JD keywords, 2 = one JD keyword, 1 = no JD keyword)

TOTAL SCORE = Specificity + Impact + JD Alignment (max 10)

REWRITE RULES (for bullets scoring < 7):
- Start with a strong action verb (Engineered, Architected, Deployed, Optimized, Led, Secured, Designed)
- Add a specific metric if one exists in the CANDIDATE BASE FACTS (never invent)
- Replace vague words: "various" → specific count, "multiple" → actual number
- Remove all filler: "responsible for", "worked on", "helped with", "assisted in", "involved in"
- End with the outcome/impact (what it enabled or improved)

TENSE RULES:
- Current role (LTIMindtree): Present tense ("Optimize", "Lead", "Instrument")
- All past roles: Past tense ("Engineered", "Led", "Deployed")

Return ONLY valid JSON:
{
  "scored_bullets": {
    "LTIMindtree": [
      {"original": "...", "score": 8, "rewritten": null},
      {"original": "...", "score": 5, "rewritten": "Optimized 30+ ASP.NET Web API endpoints by eliminating N+1 query loops, achieving sub-100ms p99 latency under peak enterprise load validated via OpenTelemetry."}
    ],
    "DSSI Solutions": [...],
    "Nexa Office InfoSystems": [...],
    "Kasadara Technology Solutions": [...]
  }
}"""


CONSISTENCY_ENFORCER_SYSTEM = """You are the Consistency Enforcer Agent in the JCode Multi-Agent Swarm.
Your job is to do a final pass over all resume bullets and the professional summary to enforce 4 rules:

RULE 1 — FILLER REMOVAL:
Replace or remove these weak phrases completely:
- "responsible for" → use the action directly
- "helped with" → use "Contributed to" or reframe with ownership
- "assisted in" → eliminate — state the contribution directly
- "worked on" → state WHAT was built/achieved
- "involved in" → eliminate — state the specific role
- "was tasked with" → use action verb directly

RULE 2 — METRIC DEDUPLICATION:
Each metric/number should appear at most ONCE across the entire resume.
Scan for duplicated percentages (e.g. "38%" appearing twice) or duplicated counts
(e.g. "12 microservices" appearing in both bullets and projects).
If a metric is duplicated, vary it: change "38%" to "over a third" or adjust the framing.

RULE 3 — TENSE CONSISTENCY:
- LTIMindtree (current role): ALL bullets must be present tense
- DSSI, Nexa, Kasadara: ALL bullets must be past tense
- Summary: Write in third person present (no "I", no "my")
- Projects: Past tense (completed work)

RULE 4 — OPENING VERB VARIETY:
No two bullets within the same role should start with the same verb.
If two bullets both start with "Implemented", change one to "Deployed" or "Configured" or "Engineered".

Return the FULL corrected JSON with the same schema as the Tailor output — all four work_experience entries
and the professional_summary. Only change what needs fixing. Return ONLY valid JSON.
{
  "professional_summary": "...",
  "work_experience": [
    {
      "company": "LTIMindtree",
      "dates": "Jun 2025 – Present",
      "role_title": "...",
      "tech_stack_line": "...",
      "bullets": ["...", "...", "...", "..."],
      "key": "LTIMindtree"
    },
    ...
  ]
}"""


# ─── AGENT FUNCTIONS ─────────────────────────────────────────────────────────

def research_company(company: str, job_title: str, jd_text: str,
                     parse_json_safely=None) -> dict:
    """
    Agent 0.5: Company Research Agent.
    Deep-researches the company and JD to extract competitive intelligence.
    Returns a company_intelligence dict.
    """
    if parse_json_safely is None:
        # Inline minimal JSON extractor as fallback
        def parse_json_safely(raw):
            import json, re
            raw = raw.strip()
            m = re.search(r'(\{.*\})', raw, re.DOTALL)
            candidate = m.group(1).strip() if m else raw
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                return {}

    try:
        prompt = (
            f"Company: {company}\n"
            f"Job Title: {job_title}\n\n"
            f"Full JD:\n{jd_text[:4000]}"
        )
        raw = ai_complete(COMPANY_RESEARCH_SYSTEM, prompt, task="analyze", max_tokens=900)
        result = parse_json_safely(raw)
        print(f"    [CompanyResearch] Narrative angle: {result.get('resume_narrative_angle', 'N/A')[:80]}")
        return result
    except Exception as e:
        print(f"    [CompanyResearch] Failed (using defaults): {e}")
        return {
            "company_tech_inference": [],
            "company_domain_detail": "enterprise software",
            "culture_dna": ["delivery-focused", "collaborative"],
            "top_3_differentiators": [
                "Sub-100ms API latency using Redis + OpenTelemetry",
                "CQRS microservices across 12+ production services",
                "AZ-204 certified Azure developer"
            ],
            "jd_mirror_phrases": [],
            "resume_narrative_angle": "Performance-obsessed cloud-native .NET engineer",
            "opening_power_verb": "Architected",
            "summary_tone": "achievement-first"
        }


def expand_projects(
    project_names: list,
    jd_context: dict,
    company_intelligence: dict,
    parse_json_safely=None
) -> list:
    """
    Agent 1.5: Project Expander Agent.
    Expands project names into full architectural narratives with impact bullets.
    Returns a list of expanded project dicts.
    """
    if parse_json_safely is None:
        def parse_json_safely(raw):
            import json, re
            raw = raw.strip()
            m = re.search(r'(\{.*\})', raw, re.DOTALL)
            candidate = m.group(1).strip() if m else raw
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                return {}

    # Build the grounded project database to pass to the AI
    PROJECT_FACTS = {
        "AI Tax Document Analyser": {
            "tech_stack": "C# · .NET Core · Azure OpenAI GPT-4 · pgvector · Semantic Kernel · OpenTelemetry",
            "domain": "AI/ML, enterprise tax automation",
            "allowed_metrics": [
                "60% reduction in manual migration effort",
                "sub-200ms semantic document lookup",
                "35% faster weekly triage",
                "85% test coverage with xUnit"
            ]
        },
        "e-ProcureZen": {
            "tech_stack": "C# · .NET 7 · Clean Architecture · CQRS · YARP Reverse Proxy · RabbitMQ · Redis · Docker · Azure App Services",
            "domain": "financial procurement, B2B SaaS",
            "allowed_metrics": [
                "3x message processing throughput via RabbitMQ",
                "99.98% system uptime SLA",
                "12+ production microservices",
                "65% container image size reduction"
            ]
        },
        "Nexa Vault": {
            "tech_stack": ".NET Core · Angular · AES-256 Encryption · OAuth2/OIDC · Docker · SQL Server · mTLS · X.509",
            "domain": "enterprise document management, security",
            "allowed_metrics": [
                "35% page load improvement",
                "25% search lookup acceleration",
                "100+ manual hours saved"
            ]
        },
        "SSO Application": {
            "tech_stack": "ASP.NET Core · OAuth2 · OIDC · JWT · mTLS · X.509 · In-Memory Distributed Cache",
            "domain": "identity, enterprise security",
            "allowed_metrics": [
                "40% reduction in login-related support tickets",
                "centralized authentication across multiple enterprise apps"
            ]
        },
        "NEICE": {
            "tech_stack": ".NET Framework 4.x · WCF · SQL Server · FIPS Compliance · RBAC · ADO.NET · Section 508",
            "domain": "US government platform, federal compliance",
            "allowed_metrics": [
                "8+ ASP.NET MVC modules",
                "FIPS-compliant cryptographic providers",
                "multi-agency federal data transfer"
            ]
        }
    }

    # Filter to only the requested projects
    selected_facts = {}
    for name in project_names:
        for key, val in PROJECT_FACTS.items():
            if key.lower() in name.lower() or name.lower() in key.lower():
                selected_facts[key] = val
                break

    if not selected_facts:
        return []

    try:
        prompt = (
            f"JD Domain: {jd_context.get('company_domain', 'technology')}\n"
            f"JD Must-Have Technologies: {jd_context.get('domain_priority_skills', [])}\n"
            f"Company Culture: {company_intelligence.get('culture_dna', [])}\n"
            f"JD Mirror Phrases: {company_intelligence.get('jd_mirror_phrases', [])}\n"
            f"Resume Narrative Angle: {company_intelligence.get('resume_narrative_angle', '')}\n\n"
            f"Projects to expand:\n{json.dumps(selected_facts, indent=2)}\n\n"
            f"Write deeply expanded project entries for ALL {len(selected_facts)} projects. "
            f"Each project MUST have exactly 3 bullets: "
            f"(1) architecture rationale bullet - WHY those exact tech choices were made as trade-offs, "
            f"(2) impact/metric bullet - quantified outcome using ONLY the allowed_metrics listed, "
            f"(3) JD-alignment bullet - maps the project capability to the JD's primary requirement. "
            f"Use ONLY the allowed_metrics listed. Do NOT invent new numbers."
        )
        raw = ai_complete(PROJECT_EXPANDER_SYSTEM, prompt, task="tailor", max_tokens=3000)
        result = parse_json_safely(raw)
        expanded = result.get("expanded_projects", [])
        print(f"    [ProjectExpander] Expanded {len(expanded)} project(s) with architecture rationale.")
        return expanded
    except Exception as e:
        print(f"    [ProjectExpander] Failed (using base project facts): {e}")
        return []


def score_and_rewrite_bullets(
    work_experience: list,
    jd_must_haves: list,
    company_intelligence: dict,
    parse_json_safely=None
) -> list:
    """
    Agent 4.5: Bullet Quality Scorer + Rewriter.
    Scores all bullets 1–10 and rewrites weak ones (score < 7).
    Returns improved work_experience list.
    """
    if parse_json_safely is None:
        def parse_json_safely(raw):
            import json, re
            raw = raw.strip()
            m = re.search(r'(\{.*\})', raw, re.DOTALL)
            candidate = m.group(1).strip() if m else raw
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                return {}

    try:
        # Build bullet map
        bullet_map = {}
        for job in work_experience:
            comp = job.get("company", "Unknown")
            bullet_map[comp] = job.get("bullets", [])

        prompt = (
            f"JD Must-Have Skills: {jd_must_haves}\n"
            f"Company Culture DNA: {company_intelligence.get('culture_dna', [])}\n"
            f"JD Mirror Phrases: {company_intelligence.get('jd_mirror_phrases', [])}\n\n"
            f"Bullets to score and rewrite:\n{json.dumps(bullet_map, indent=2)}\n\n"
            f"Score each bullet and rewrite any scoring below 7. "
            f"Use ONLY metrics from these ALLOWED FACTS:\n"
            f"- LTIMindtree: 38% latency reduction, 60% manual effort saved, 45% DB load reduction, "
            f"50% MTTR reduction, 35% faster triage, 85% test coverage, sub-100ms p99 latency, sub-200ms semantic lookup\n"
            f"- DSSI: 3x throughput, 99.98% uptime, 40% defect reduction, 65% image size reduction, 100+ hours saved\n"
            f"- Nexa: 35% page load improvement, 25% search acceleration\n"
            f"- Kasadara: 40% memory reduction, 2x processing speed, 30% query improvement\n"
        )
        raw = ai_complete(BULLET_SCORER_SYSTEM, prompt, task="verify", max_tokens=2000)
        scored = parse_json_safely(raw)

        # Merge rewrites back into work_experience
        scored_bullets = scored.get("scored_bullets", {})
        rewrite_count = 0
        for job in work_experience:
            comp = job.get("company", "")
            if comp in scored_bullets:
                new_bullets = []
                for item in scored_bullets[comp]:
                    orig = item.get("original", "")
                    score = item.get("score", 10)
                    rewritten = item.get("rewritten")
                    if score < 7 and rewritten:
                        new_bullets.append(rewritten)
                        rewrite_count += 1
                    else:
                        # Keep the original but prefer rewritten if provided
                        new_bullets.append(rewritten if rewritten else orig)
                if new_bullets:
                    job["bullets"] = new_bullets

        print(f"    [BulletScorer] Rewrote {rewrite_count} weak bullet(s) for higher impact.")
        return work_experience

    except Exception as e:
        print(f"    [BulletScorer] Failed (keeping current bullets): {e}")
        return work_experience


def enforce_consistency(
    professional_summary: str,
    work_experience: list,
    parse_json_safely=None
) -> dict:
    """
    Agent 4.75: Consistency Enforcer.
    Fixes tenses, removes filler words, deduplicates metrics, varies opening verbs.
    Returns dict with corrected summary + work_experience.
    """
    if parse_json_safely is None:
        def parse_json_safely(raw):
            import json, re
            raw = raw.strip()
            m = re.search(r'(\{.*\})', raw, re.DOTALL)
            candidate = m.group(1).strip() if m else raw
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                return {}

    # Quick programmatic filler removal (before AI pass)
    FILLER_REPLACEMENTS = [
        (r'\bresponsible for\b', ''),
        (r'\bhelped (?:to |with )', ''),
        (r'\bassisted in\b', ''),
        (r'\bworked on\b', 'Built'),
        (r'\binvolved in\b', ''),
        (r'\bwas tasked with\b', ''),
    ]

    def remove_fillers(text: str) -> str:
        for pattern, replacement in FILLER_REPLACEMENTS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        # Clean up double spaces
        text = re.sub(r'  +', ' ', text).strip()
        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]
        return text

    # Programmatic pre-clean
    for job in work_experience:
        job["bullets"] = [remove_fillers(b) for b in job.get("bullets", [])]

    # Now run AI enforcer
    try:
        prompt = (
            f"Professional Summary:\n{professional_summary}\n\n"
            f"Work Experience:\n{json.dumps(work_experience, indent=2)}\n\n"
            f"Apply all 4 consistency rules: filler removal, metric deduplication, "
            f"tense consistency, and opening verb variety. "
            f"LTIMindtree = current role (present tense). All others = past tense."
        )
        raw = ai_complete(CONSISTENCY_ENFORCER_SYSTEM, prompt, task="verify", max_tokens=2000)
        result = parse_json_safely(raw)

        enforced_summary = result.get("professional_summary", professional_summary)
        enforced_exp = result.get("work_experience", work_experience)

        # Validate it returned proper structure
        if not isinstance(enforced_exp, list) or len(enforced_exp) == 0:
            enforced_exp = work_experience

        print(f"    [ConsistencyEnforcer] Applied tense, filler, dedup, and verb variety rules.")
        return {
            "professional_summary": enforced_summary,
            "work_experience": enforced_exp
        }

    except Exception as e:
        print(f"    [ConsistencyEnforcer] Failed (using pre-cleaned version): {e}")
        return {
            "professional_summary": professional_summary,
            "work_experience": work_experience
        }


# ═══════════════════════════════════════════════════════════════════════════
# POWER AGENTS — "IMPOSSIBLE TO REJECT" TIER
# ═══════════════════════════════════════════════════════════════════════════

ATS_INJECTOR_SYSTEM = """You are the ATS Keyword Enforcer Agent — the most critical agent in the pipeline.
Your job is GUARANTEEING that every single must-have keyword from the JD appears at least once across
the entire resume. This is non-negotiable. A recruiter's ATS system will auto-reject any resume missing
even one of these keywords.

HOW TO INJECT MISSING KEYWORDS:
1. Scan the full resume JSON for each must-have keyword.
2. If a keyword is MISSING, inject it into the most semantically relevant location:
   - Technical keywords → into the most relevant bullet point (weave naturally into the sentence)
   - Soft skills → into summary or a methodology bullet
   - Certifications/tools → into the skills section or a relevant bullet
3. Injection must be NATURAL — it must read like it was always there, not bolted on.
4. NEVER fabricate new metrics or experiences — only inject the keyword where the existing content supports it.
5. After injection, mark it as "covered".

INJECTION EXAMPLES:
- Missing "Clean Architecture": Add to a DSSI bullet: "...using Clean Architecture principles and CQRS pattern..."
- Missing "Azure DevOps": Add to skills or a DevOps bullet: "...deployed via Azure DevOps CI/CD pipelines..."
- Missing "RESTful APIs": Weave into an LTIMindtree bullet: "...profiling 30+ RESTful API endpoints..."
- Missing "Agile/Scrum": Add to summary or methodology: "...across Agile/Scrum delivery sprints..."

OUTPUT RULES:
- Return the COMPLETE updated resume JSON with ALL must-have keywords now present
- Include a coverage_report showing which keywords were already there vs. injected
- Every single must-have keyword must be in the output
- Return ONLY valid JSON:
{
  "professional_summary": "...",
  "skills_by_category": { ... },
  "work_experience": [{ "company": "...", "dates": "...", "role_title": "...", "tech_stack_line": "...", "bullets": [...], "key": "..." }, ...],
  "projects": [{ "name": "...", "tech_stack": "...", "bullets": [...] }, ...],
  "certifications": [...],
  "coverage_report": {
    "already_covered": ["C#", ".NET Core", ...],
    "injected": ["keyword1 → injected into LTIMindtree bullet 2", ...],
    "final_ats_score": 100
  }
}"""


PERFECT_FIT_NARRATOR_SYSTEM = """You are the Perfect Fit Narrator Agent — the agent that transforms a good resume into an IRRESISTIBLE one.
Your job is to rewrite the Professional Summary and strengthen the narrative arc of the entire resume
so that any recruiter reading it thinks: "This person was literally made for this role."

PERFECT FIT NARRATIVE STRATEGY:
1. OPENING HOOK (Sentence 1): Don't just state the job title. Open with the candidate's most impressive
   achievement DIRECTLY matching the JD's #1 requirement. Format:
   "[Job Title] who [past achievement that directly proves the JD requirement]."
   Example: "Senior .NET Developer who architected 12+ production microservices achieving 99.98% uptime — exactly the cloud-native reliability [Company] demands."

2. PROOF STACK (Sentences 2-3): Stack 2 more JD-specific proof points. Each sentence must:
   - Reference a specific metric from the candidate's base facts
   - Mirror a specific phrase or requirement from the JD
   - Show progression (broader impact in sentence 3 than sentence 2)

3. DIFFERENTIATOR (Sentence 4): State the ONE thing that makes this candidate different from all other
   .NET developers. This should be the hardest-to-replicate achievement:
   - Azure AI/OpenAI work at enterprise scale (most .NET devs don't have this)
   - US government platform compliance (FIPS/Section 508)
   - AZ-204 certification + hands-on Azure deployment pipeline experience

4. CLOSING CALL-TO-ACTION (Sentence 5): The exact summary_closing_line from JD Intelligence.
   This must be the exact line — do not paraphrase.

ADDITIONAL NARRATIVE RULES:
- The summary must FEEL like a mini cover letter — personal, targeted, and urgent
- Use the word "you" zero times. No pronouns at all. Third-person professional voice.
- Every sentence must make the recruiter nod and think "yes, this is what we need"
- The word count must be 70-90 words. No more. Dense and punchy.
- After rewriting summary, also return top_5_why_hire: 5 bullet points the recruiter could use to
  justify hiring this candidate to their manager. These are the "sell bullets" — not in the DOCX but
  useful for cover letters.

Return ONLY valid JSON:
{
  "perfect_summary": "...",
  "top_5_why_hire": [
    "Proven cloud-native .NET architect with 12+ microservices in production at 99.98% uptime.",
    "AZ-204 certified Azure developer with hands-on deployment pipeline experience.",
    "...",
    "...",
    "..."
  ]
}"""


PROJECT_DEEP_REWRITER_SYSTEM = """You are the Project Deep Rewriter Agent — you completely re-narrate the candidate's projects
to make them sound like they were built specifically to solve the same problems as the target company.

PROJECT DEEP REWRITE RULES:

1. PROJECT TITLE REFRAMING: You MAY rename the project to use industry-standard terminology that
   resonates with the JD. Examples:
   - For a fintech JD: "e-ProcureZen" → "High-Throughput Financial Transaction Processing Platform"
   - For an AI JD: "AI Tax Document Analyser" → "Enterprise AI Document Intelligence Engine"
   - For a security JD: "Nexa Vault" → "Zero-Trust Enterprise Document Security Platform"
   - For a government JD: "NEICE" → "Multi-Agency Federal Data Exchange Platform (NEICE)"
   NOTE: Only reframe if it makes the project sound MORE relevant. Keep original if already strong.

2. DESCRIPTION LINE: One tight sentence — WHAT the project does + WHY it matters to THIS company's domain.
   Must use JD mirror phrases naturally.

3. ARCHITECTURE BULLET (bullet 1): Write as a senior architect explaining a real design decision.
   Format: "Selected [Technology A] over [Technology B] because [specific technical reason that matters to THIS JD]."
   This shows technical depth and deliberate decision-making — exactly what senior hiring managers look for.

4. IMPACT BULLET (bullet 2): Business outcome with a specific metric.
   Format: "[Action verb] [what was built] achieving [specific measurable result] — [business significance]."
   Use ONLY metrics from the allowed facts. Never invent numbers.

5. JD ALIGNMENT BULLET (bullet 3): Directly address a JD requirement.
   Format: "Addressed [JD requirement] by [specific technical approach], demonstrating direct readiness for [Company]'s [domain challenge]."

ALLOWED PROJECT FACTS (metrics to use):
- AI Tax Doc Analyser: 60% manual effort reduction, sub-200ms semantic lookup, 35% faster triage, 85% test coverage
- e-ProcureZen: 3x throughput, 99.98% uptime, 12+ microservices, 65% image size reduction, 100+ hours saved
- Nexa Vault: 35% page load improvement, 25% search acceleration
- SSO Application: 40% reduction in login support tickets, enterprise-wide SSO
- NEICE: 8+ modules, FIPS-compliant, multi-agency federal data transfer

CRITICAL: Only use tech in the project's actual tech stack. Never add technologies not listed.

Return ONLY valid JSON:
{
  "rewritten_projects": [
    {
      "name": "Reframed Project Title (Original Name)",
      "tech_stack": "Original tech stack preserved",
      "description": "One sentence: what it does and why it matters",
      "bullets": [
        "Architecture rationale bullet...",
        "Impact bullet with metric...",
        "JD alignment bullet..."
      ]
    }
  ]
}"""


# ─── NEW AGENT FUNCTIONS ─────────────────────────────────────────────────────

def enforce_ats_keywords(
    resume_json: dict,
    jd_must_haves: list,
    jd_nice_to_haves: list,
    parse_json_safely=None
) -> dict:
    """
    Agent: ATS Keyword Enforcer.
    Guarantees EVERY must-have keyword from the JD appears at least once.
    Scans and injects missing keywords naturally into the most relevant location.
    Returns updated resume_json with coverage_report.
    """
    if parse_json_safely is None:
        def parse_json_safely(raw):
            import json, re
            raw = raw.strip()
            m = re.search(r'(\{.*\})', raw, re.DOTALL)
            candidate = m.group(1).strip() if m else raw
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                return {}

    # First do a quick programmatic scan to see what's already covered
    resume_text = json.dumps(resume_json).lower()
    already_covered = []
    missing = []
    for kw in jd_must_haves:
        if kw.lower() in resume_text:
            already_covered.append(kw)
        else:
            missing.append(kw)

    if not missing:
        print(f"    [ATSEnforcer] All {len(jd_must_haves)} must-have keywords already covered. ATS score: 100%")
        resume_json["coverage_report"] = {
            "already_covered": already_covered,
            "injected": [],
            "final_ats_score": 100
        }
        return resume_json

    print(f"    [ATSEnforcer] {len(already_covered)} covered, {len(missing)} missing: {missing[:5]}{'...' if len(missing)>5 else ''}")

    try:
        prompt = (
            f"JD Must-Have Keywords (ALL must appear in the resume):\n{jd_must_haves}\n\n"
            f"JD Nice-to-Have Keywords:\n{jd_nice_to_haves}\n\n"
            f"MISSING keywords not yet in the resume:\n{missing}\n\n"
            f"Current Resume JSON:\n{json.dumps(resume_json, indent=2)[:6000]}\n\n"
            f"Inject ALL missing keywords naturally. Return the complete updated resume JSON."
        )
        raw = ai_complete(ATS_INJECTOR_SYSTEM, prompt, task="verify", max_tokens=4000)
        result = parse_json_safely(raw)

        # Merge injected content back
        if result.get("work_experience"):
            resume_json["work_experience"] = result["work_experience"]
        if result.get("professional_summary"):
            resume_json["professional_summary"] = result["professional_summary"]
        if result.get("skills_by_category"):
            resume_json["skills_by_category"] = result["skills_by_category"]
        if result.get("projects"):
            resume_json["projects"] = result["projects"]
        if result.get("coverage_report"):
            resume_json["coverage_report"] = result["coverage_report"]

        # Re-verify coverage after injection
        resume_text_new = json.dumps(resume_json).lower()
        final_covered = [kw for kw in jd_must_haves if kw.lower() in resume_text_new]
        final_score = round(len(final_covered) / max(len(jd_must_haves), 1) * 100)
        print(f"    [ATSEnforcer] Final ATS keyword score: {final_score}% ({len(final_covered)}/{len(jd_must_haves)} must-haves)")
        if "coverage_report" not in resume_json:
            resume_json["coverage_report"] = {"final_ats_score": final_score}
        else:
            resume_json["coverage_report"]["final_ats_score"] = final_score

        return resume_json

    except Exception as e:
        print(f"    [ATSEnforcer] Failed: {e}")
        return resume_json


def write_perfect_fit_summary(
    resume_json: dict,
    jd_context: dict,
    company_intelligence: dict,
    analysis: dict,
    parse_json_safely=None
) -> dict:
    """
    Agent: Perfect Fit Narrator.
    Rewrites the professional summary to position the candidate as the PERFECT and ONLY choice.
    Also generates top_5_why_hire selling points.
    """
    if parse_json_safely is None:
        def parse_json_safely(raw):
            import json, re
            raw = raw.strip()
            m = re.search(r'(\{.*\})', raw, re.DOTALL)
            candidate = m.group(1).strip() if m else raw
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                return {}

    try:
        prompt = (
            f"Job Title: {jd_context.get('seniority_level','Senior')} {analysis.get('job_title','Software Engineer')}\n"
            f"Company: {analysis.get('company_name','the company')}\n"
            f"Company Domain: {jd_context.get('company_domain','technology')}\n"
            f"JD Must-Haves: {analysis.get('must_haves',[])}\n"
            f"JD Mirror Phrases: {company_intelligence.get('jd_mirror_phrases',[])}\n"
            f"Top 3 Differentiators: {company_intelligence.get('top_3_differentiators',[])}\n"
            f"Narrative Angle: {company_intelligence.get('resume_narrative_angle','')}\n"
            f"Summary Closing Line (EXACT, do not change): {jd_context.get('summary_closing_line','')}\n\n"
            f"Current summary draft:\n{resume_json.get('professional_summary','')}\n\n"
            f"Rewrite this into a 70-90 word Perfect Fit summary. The recruiter must think "
            f"'this person was made for this role.' Include the exact closing line unchanged."
        )
        raw = ai_complete(PERFECT_FIT_NARRATOR_SYSTEM, prompt, task="tailor", max_tokens=700)
        result = parse_json_safely(raw)

        perfect_summary = result.get("perfect_summary", "")
        if perfect_summary and len(perfect_summary) > 50:
            resume_json["professional_summary"] = perfect_summary
            print(f"    [PerfectFitNarrator] Summary rewritten ({len(perfect_summary.split())} words).")
        else:
            print(f"    [PerfectFitNarrator] Summary rewrite too short, keeping current.")

        resume_json["top_5_why_hire"] = result.get("top_5_why_hire", [])
        return resume_json

    except Exception as e:
        print(f"    [PerfectFitNarrator] Failed: {e}")
        return resume_json


def deep_rewrite_projects(
    resume_json: dict,
    jd_context: dict,
    company_intelligence: dict,
    analysis: dict,
    parse_json_safely=None
) -> dict:
    """
    Agent: Project Deep Rewriter.
    Completely re-narrates projects to match JD domain perfectly.
    Can reframe project names, re-angle architecture decisions, re-write all bullets.
    """
    if parse_json_safely is None:
        def parse_json_safely(raw):
            import json, re
            raw = raw.strip()
            m = re.search(r'(\{.*\})', raw, re.DOTALL)
            candidate = m.group(1).strip() if m else raw
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                return {}

    current_projects = resume_json.get("projects", [])
    if not current_projects:
        print(f"    [ProjectDeepRewriter] No projects to rewrite.")
        return resume_json

    try:
        prompt = (
            f"Target Company Domain: {jd_context.get('company_domain','technology')}\n"
            f"JD Must-Have Keywords: {analysis.get('must_haves',[])}\n"
            f"JD Exact Phrases to Mirror: {company_intelligence.get('jd_mirror_phrases',[])}\n"
            f"Company Culture DNA: {company_intelligence.get('culture_dna',[])}\n"
            f"Company Tech Inference: {company_intelligence.get('company_tech_inference',[])}\n"
            f"Resume Narrative Angle: {company_intelligence.get('resume_narrative_angle','')}\n\n"
            f"Projects to deep-rewrite:\n{json.dumps(current_projects, indent=2)}\n\n"
            f"Completely re-narrate each project. Reframe names if it makes them more JD-relevant. "
            f"Write architecture rationale, impact, and JD-alignment bullets from scratch. "
            f"Use ONLY metrics from the allowed facts in your instructions."
        )
        raw = ai_complete(PROJECT_DEEP_REWRITER_SYSTEM, prompt, task="tailor", max_tokens=1500)
        result = parse_json_safely(raw)

        rewritten = result.get("rewritten_projects", [])
        if rewritten and isinstance(rewritten, list) and len(rewritten) > 0:
            resume_json["projects"] = rewritten
            print(f"    [ProjectDeepRewriter] Rewrote {len(rewritten)} project(s) with JD-aligned narrative.")
        else:
            print(f"    [ProjectDeepRewriter] No valid output, keeping current projects.")

        return resume_json

    except Exception as e:
        print(f"    [ProjectDeepRewriter] Failed: {e}")
        return resume_json
