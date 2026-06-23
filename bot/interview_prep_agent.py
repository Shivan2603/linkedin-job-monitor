"""
interview_prep_agent.py — Auto Interview Prep Sheet Generator
═══════════════════════════════════════════════════════════════
For every job applied to, auto-generates a full interview preparation sheet:
  - Top 10 likely technical interview questions (based on JD)
  - Model answers grounded in candidate's real experience
  - Top 5 behavioral questions (STAR format answers)
  - 5 smart questions to ask the interviewer
  - Salary negotiation talking points
  - Key company research points to mention
  - Red flags / likely hard questions and how to handle them
"""

import os, json
from bot.ai_router import ai_complete

INTERVIEW_PREP_SYSTEM = """You are the Interview Preparation Agent — you generate a comprehensive,
role-specific interview preparation sheet so the candidate walks in fully prepared and
comes across as the most qualified person in the room.

You will receive the job title, company, JD, and candidate facts.
Generate a complete interview prep sheet with:

1. TECHNICAL QUESTIONS (10 questions):
   - Questions likely to be asked based on the JD's tech stack
   - Each question gets a MODEL ANSWER grounded in the candidate's real experience
   - Answers use the STAR format where applicable (Situation → Task → Action → Result)
   - Include specific metrics from the candidate's actual work
   - Format: {"question": "...", "model_answer": "..."}

2. BEHAVIORAL QUESTIONS (5 questions):
   - Classic behavioral questions mapped to the JD's soft skill requirements
   - STAR format answers using the candidate's real stories
   - Format: {"question": "...", "star_answer": {"situation": "...", "task": "...", "action": "...", "result": "..."}}

3. QUESTIONS TO ASK INTERVIEWER (5 questions):
   - Smart, strategic questions that show deep research and senior thinking
   - NOT generic questions — must be specific to this company and role
   - Mix of: technical depth, team dynamics, growth opportunity, company direction
   - A candidate who asks great questions gets hired

4. SALARY NEGOTIATION:
   - Target range to state: "20-30 LPA for India / $80,000-$120,000 for international"
   - 3 key talking points to justify the range
   - How to handle: "What's your current salary?" (always redirect to market rate)
   - Script for counter-offer scenario

5. RED FLAGS / HARD QUESTIONS:
   - Questions the interviewer might ask that are tricky given the candidate's profile
   - For each red flag: the concern + how to reframe positively
   - Common red flags: "You've only been at LTIMindtree 1 year", "You're based in India for a UK role", "4 years is junior for this senior role"

6. KEY TALKING POINTS:
   - Top 3 things to ALWAYS bring up even if not asked
   - Opening statement (30-second elevator pitch for this specific role)
   - Closing statement (what to say when "Do you have any final questions?")

CANDIDATE FACTS (for grounding answers):
- Name: Siva Shankar V, Senior Software Engineer, 4+ years
- LTIMindtree: Client Deloitte, .NET Core 8, Azure OpenAI, Microservices, CQRS, pgvector, Redis, OpenTelemetry
  → sub-100ms p99 latency, 60% manual effort saved, 45% DB load reduction, 85% test coverage, 38% query latency reduction
- DSSI Solutions: .NET 7, Clean Architecture, CQRS, YARP, Docker, RabbitMQ
  → 12+ microservices, 99.98% uptime, 3x throughput, 65% image size reduction, 100+ hours saved, 40% defect reduction
- Nexa Office: .NET Core, Angular, AES-256, OAuth2/OIDC, mTLS
  → 35% page load improvement, 25% search acceleration
- Kasadara: .NET Framework, WCF, ADO.NET, Go, US Gov FIPS compliance, Section 508
  → 40% memory reduction, 2x processing speed
- AZ-204 Azure Certified
- Notice: Serving notice, LWD 14 August 2026

Return ONLY valid JSON:
{
  "role_summary": "One line: why this candidate is perfect for this role",
  "elevator_pitch": "30-second pitch for this specific role at this company",
  "technical_questions": [
    {"question": "...", "model_answer": "..."},
    ...
  ],
  "behavioral_questions": [
    {
      "question": "...",
      "star_answer": {
        "situation": "...",
        "task": "...",
        "action": "...",
        "result": "..."
      }
    },
    ...
  ],
  "questions_to_ask": [
    {"question": "...", "why_smart": "..."},
    ...
  ],
  "salary_talking_points": ["...", "...", "..."],
  "salary_current_deflection": "When asked about current salary, say: '...'",
  "red_flags_and_rebuttals": [
    {"concern": "...", "reframe": "..."},
    ...
  ],
  "must_mention_points": ["...", "...", "..."],
  "closing_statement": "..."
}"""


def generate_interview_prep(
    job_title: str,
    company: str,
    job_description: str,
    jd_context: dict,
    company_intelligence: dict,
    analysis: dict,
    output_path: str,
    parse_json_safely=None
) -> str:
    """
    Generate a full interview preparation sheet as a .txt file.
    Returns the path to the saved file.
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

    print(f"    [InterviewPrep] Generating interview prep sheet for {company}...")

    try:
        prompt = (
            f"Job Title: {job_title}\n"
            f"Company: {company}\n"
            f"Company Domain: {jd_context.get('company_domain', 'technology')}\n"
            f"Is Team Lead: {jd_context.get('is_team_lead_role', False)}\n"
            f"Is International: {jd_context.get('is_international', False)}\n"
            f"Location: {jd_context.get('job_location_city', 'Unknown')}\n"
            f"JD Must-Haves: {analysis.get('must_haves', [])}\n"
            f"JD Exact Phrases: {analysis.get('exact_phrases', [])}\n"
            f"Company Culture: {company_intelligence.get('culture_dna', [])}\n"
            f"Top Differentiators: {company_intelligence.get('top_3_differentiators', [])}\n\n"
            f"JD:\n{job_description[:3000]}\n\n"
            f"Generate a complete interview prep sheet with 10 technical Qs, 5 behavioral Qs, "
            f"5 smart questions to ask, salary guidance, red flags, and key talking points."
        )
        raw = ai_complete(INTERVIEW_PREP_SYSTEM, prompt, task="analyze", max_tokens=4000)
        prep = parse_json_safely(raw)
    except Exception as e:
        print(f"    [InterviewPrep] AI generation failed: {e}")
        prep = {}

    # Build the text output
    try:
        content = _format_prep_sheet(prep, job_title, company)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"    [InterviewPrep] Saved: {output_path}")
        return output_path
    except Exception as e:
        print(f"    [InterviewPrep] Save failed: {e}")
        return ""


def _format_prep_sheet(prep: dict, job_title: str, company: str) -> str:
    """Format the interview prep JSON into a readable text document."""
    lines = []

    def h1(text): lines.append(f"\n{'═'*70}\n  {text.upper()}\n{'═'*70}")
    def h2(text): lines.append(f"\n{'─'*60}\n  {text}\n{'─'*60}")
    def item(label, text): lines.append(f"\n  ► {label}:\n    {text}")
    def bullet(text): lines.append(f"    • {text}")
    def blank(): lines.append("")

    h1(f"Interview Prep Sheet: {job_title} @ {company}")
    lines.append(f"  Generated by JCode Interview Prep Agent")
    lines.append(f"  Candidate: Siva Shankar V | sivashankar.avi6@gmail.com")

    if prep.get("role_summary"):
        blank()
        lines.append(f"  ROLE MATCH: {prep['role_summary']}")

    # Elevator Pitch
    if prep.get("elevator_pitch"):
        h2("30-SECOND ELEVATOR PITCH (memorize this)")
        lines.append(f"\n  \"{prep['elevator_pitch']}\"")

    # Technical Questions
    tech_qs = prep.get("technical_questions", [])
    if tech_qs:
        h2(f"TECHNICAL QUESTIONS ({len(tech_qs)} likely questions)")
        for i, q in enumerate(tech_qs, 1):
            blank()
            lines.append(f"  Q{i}. {q.get('question', '')}")
            lines.append(f"      MODEL ANSWER:")
            answer = q.get("model_answer", "")
            # Word-wrap at ~80 chars
            words = answer.split()
            line = "      "
            for word in words:
                if len(line) + len(word) > 80:
                    lines.append(line)
                    line = "      " + word + " "
                else:
                    line += word + " "
            if line.strip():
                lines.append(line)

    # Behavioral Questions
    beh_qs = prep.get("behavioral_questions", [])
    if beh_qs:
        h2(f"BEHAVIORAL QUESTIONS ({len(beh_qs)} STAR format answers)")
        for i, q in enumerate(beh_qs, 1):
            blank()
            lines.append(f"  B{i}. {q.get('question', '')}")
            star = q.get("star_answer", {})
            if star:
                lines.append(f"      SITUATION: {star.get('situation', '')}")
                lines.append(f"      TASK:      {star.get('task', '')}")
                lines.append(f"      ACTION:    {star.get('action', '')}")
                lines.append(f"      RESULT:    {star.get('result', '')}")

    # Questions to ask
    ask_qs = prep.get("questions_to_ask", [])
    if ask_qs:
        h2("SMART QUESTIONS TO ASK THE INTERVIEWER")
        lines.append("  (Asking great questions = +30% hire rate)")
        for i, q in enumerate(ask_qs, 1):
            blank()
            lines.append(f"  Q{i}. {q.get('question', '')}")
            if q.get("why_smart"):
                lines.append(f"       [Why smart: {q['why_smart']}]")

    # Salary
    salary_pts = prep.get("salary_talking_points", [])
    if salary_pts:
        h2("SALARY NEGOTIATION")
        lines.append("  Target: 20-30 LPA (India) / $80,000-$120,000 (International)")
        blank()
        lines.append("  KEY TALKING POINTS:")
        for pt in salary_pts:
            bullet(pt)
        deflection = prep.get("salary_current_deflection", "")
        if deflection:
            blank()
            lines.append(f"  WHEN ASKED CURRENT SALARY:\n  \"{deflection}\"")

    # Red flags
    red_flags = prep.get("red_flags_and_rebuttals", [])
    if red_flags:
        h2("RED FLAGS & HOW TO HANDLE THEM")
        for rf in red_flags:
            blank()
            lines.append(f"  CONCERN: {rf.get('concern', '')}")
            lines.append(f"  REFRAME: {rf.get('reframe', '')}")

    # Must-mention
    must_mention = prep.get("must_mention_points", [])
    if must_mention:
        h2("MUST MENTION (even if not asked)")
        for pt in must_mention:
            bullet(pt)

    # Closing
    if prep.get("closing_statement"):
        h2("CLOSING STATEMENT (when interview ends)")
        lines.append(f"\n  \"{prep['closing_statement']}\"")

    h1("END OF PREP SHEET — GO GET THE JOB, SIVA!")

    return "\n".join(lines)
