from langchain_core.messages import SystemMessage, HumanMessage
import re
from urllib.parse import urlparse

from Graph.state import State
from Graph.structured_data import QAReport, QAIssue

# ✅ FIX #6 (completed): Import shared auto-fix utilities.
# completion_validator.py was already updated to use apply_all_fixes(),
# but this file was missed — it still had the same ~20 lines of inline
# fix logic that Fixes.py was created to replace.
# Also removed the double-fix: completion_validator runs before this node
# in the graph, so by the time qa_agent_node runs, fixes are already applied.
from Graph.Fixes import apply_all_fixes

from .utils import logger, llm_quality, _job, _emit

QA_AGENT_SYSTEM = """You are an elite Quality Assurance (QA) Editor for a top-tier publishing platform.
Your job is to read the provided blog post and conduct a rigorous final audit before publication.

You must evaluate the content on three dimensions:
1. FACTS & ACCURACY: Are there hallucinations? Did the writer invent claims not supported by the evidence?
2. COMPLETENESS & STRUCTURE: Does it flow logically? Did the writer adequately address the initial plan's goals? Are there missing sections?
3. READABILITY & TONE: Is the writing engaging, professional, and free of robotic cliches (e.g., "In conclusion", "It is important to note")?

INSTRUCTIONS:
- Calibrate scores against the rubric below — do NOT default to 5-7 for average work.
- A blog with solid evidence, clear structure, and professional tone should score 8+.
- Only score below 6 if there are genuine factual errors, major gaps, or poor readability.
- If you find CRITICAL issues (false facts, major hallucinated claims, or significantly incomplete sections), set the verdict to NEEDS_REVISION.
- Return a structured QA Report answering these exact dimensions.

SCORING RUBRIC (use these anchors):
- 9-10: Exceptional. Factually tight, compelling narrative, zero fluff, strong evidence integration.
- 7-8:  Good / Solid. Accurate, well-structured, professional tone. Minor room for polish.
- 5-6:  Acceptable but flawed. Some weak claims, slightly robotic phrasing, or thin evidence.
- 3-4:  Poor. Noticeable hallucinations, missing sections, or confusing flow.
- 1-2:  Unusable. Major factual errors or incoherent structure.
"""

# ✅ FIX: Raised from 12,000 to 30,000 characters.
# A standard 2,500-word blog is ~15,000 chars. The old limit meant the second
# half of every blog was never audited — hallucinations and structural problems
# in later sections passed through completely unchecked.
_QA_AUDIT_CHAR_LIMIT = 30_000


def verify_citations(blog_text: str, evidence: list) -> list[dict]:
    """
    Parse all markdown links in the blog post and verify them against the research evidence.
    Returns a list of dictionaries describing any citation issues found.
    """
    issues = []
    # Find all inline markdown links: [Link Text](URL)
    links = re.findall(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', blog_text)
    if not links:
        return issues

    # Extract all valid domains and exact URLs from research evidence
    valid_urls = set()
    valid_domains = set()
    for item in evidence:
        url = item.url if hasattr(item, 'url') else (item.get('url') if isinstance(item, dict) else '')
        if url:
            url_clean = url.strip().lower()
            valid_urls.add(url_clean)
            try:
                parsed = urlparse(url_clean)
                netloc = parsed.netloc
                if netloc:
                    valid_domains.add(netloc)
                    # Also add domain without 'www.'
                    if netloc.startswith('www.'):
                        valid_domains.add(netloc[4:])
            except Exception:
                pass

    for link_text, link_url in links:
        link_url_clean = link_url.strip().lower()
        
        # Verify if exact URL is valid
        if link_url_clean in valid_urls:
            continue
            
        # Verify if domain matches
        try:
            parsed = urlparse(link_url_clean)
            netloc = parsed.netloc
            domain = netloc
            if domain.startswith('www.'):
                domain = domain[4:]
        except Exception:
            netloc = ""
            domain = ""

        if netloc in valid_domains or domain in valid_domains:
            continue
            
        # If it doesn't match any evidence URL or domain, it is hallucinated!
        issues.append({
            "claim": f"Link '[{link_text}]({link_url})'",
            "issue_type": "hallucination",
            "severity": "critical",
            "recommendation": (
                f"The URL '{link_url}' is not in the research evidence. "
                "Only cite verified sources from the research phase. "
                "Replace this link with a valid citation from your search results or remove it."
            )
        })
    return issues


def qa_agent_node(state: State) -> dict:
    _emit(_job(state), "qa_agent", "started", "Running comprehensive QA audit (Facts + Quality)...")
    logger.info("🕵️ QUALITY ASSURANCE AUDIT ---")

    plan = state.get("plan")
    final_text = state.get("final", "")

    # Combine sections if final somehow doesn't exist yet
    if not final_text:
        raw_sections = state.get("sections", [])
        sections = list(raw_sections)
        sections.sort(key=lambda x: x[0] if isinstance(x, (tuple, list)) and len(x) > 0 else 0)
        final_text = "\n\n".join([str(s[1]) for s in sections if isinstance(s, (tuple, list)) and len(s) > 1])

    # Run automated citation check
    evidence = state.get("evidence", [])
    citation_issues = verify_citations(final_text, evidence)

    # --- 1. STRUCTURAL PRE-CHECKS (lexical only — no auto-fixing here) ---
    # Auto-fixes were already applied by completion_validator upstream.
    # This block only detects and reports remaining structural issues for the report.
    lexical_issues = []

    if plan:
        import re as _re
        expected_sections = len(plan.tasks)
        actual_sections = len(_re.findall(r'^#{2,4} ', final_text, _re.MULTILINE))
        if actual_sections < expected_sections:
            lexical_issues.append(f"Missing sections (Expected {expected_sections}, found {actual_sections})")

    # --- 2. LLM QA AUDIT ---
    checker = llm_quality.with_structured_output(QAReport)

    evidence_summary = "\n".join([
        f"- {e.title} ({e.url})\n  Content: {e.snippet[:500]}..."
        for e in evidence[:15]
    ])

    # Include revision context so QA doesn't re-flag already-addressed issues
    revision_count = state.get("revision_count", 0)
    fixed_claims = state.get("qa_fixed_claims", [])

    revision_context = ""
    if revision_count > 0:
        revision_context = (
            f"\n\nIMPORTANT CONTEXT: This blog has already undergone {revision_count} revision(s). "
            f"The following issues were already addressed and MUST NOT be re-flagged:\n"
        )
        for claim in fixed_claims:
            revision_context += f"  - ALREADY FIXED: {claim}\n"
        revision_context += (
            "\nOnly flag genuinely NEW issues. If a claim was previously flagged and the "
            "surrounding text has been rewritten, consider it resolved.\n"
        )

    # Inject citation validation results into human prompt
    citation_warning = ""
    if citation_issues:
        citation_warning = (
            "\n\n⚠️ CRITICAL WARNING: The automated citation scanner detected unverified/fabricated outbound links "
            "not supported by the research evidence. These must be flagged as critical issues:\n"
        )
        for issue in citation_issues:
            citation_warning += f"  - Link: {issue['claim']}\n    Feedback: {issue['recommendation']}\n"
        citation_warning += (
            "\nYou MUST include these citation errors in the issues list of your QA report "
            "and set the verdict to NEEDS_REVISION.\n"
        )

    report = checker.invoke([
        SystemMessage(content=QA_AGENT_SYSTEM),
        HumanMessage(content=(
            f"BLOG CONTENT TO AUDIT:\n{final_text[:_QA_AUDIT_CHAR_LIMIT]}\n\n"
            f"EVIDENCE USED IN RESEARCH:\n{evidence_summary}"
            f"{revision_context}"
            f"{citation_warning}"
        ))
    ])

    # --- 3. INTEGRATE AUTOMATED OVERRIDES ---
    if citation_issues:
        # Guarantee verdict is NEEDS_REVISION and score is capped
        report.verdict = "NEEDS_REVISION"
        report.overall_score = min(report.overall_score, 6.0)

        # Inject citation issues if not already present in report
        for issue_dict in citation_issues:
            exists = any(
                issue_dict["claim"] in (existing.claim or "")
                for existing in report.issues
            )
            if not exists:
                report.issues.append(QAIssue(
                    claim=issue_dict["claim"],
                    issue_type="hallucination",
                    severity="critical",
                    recommendation=issue_dict["recommendation"]
                ))

    # --- 4. FORMAT REPORT ---
    report_text = "QA AUDIT REPORT\n"
    report_text += "=" * 60 + "\n"
    report_text += f"Overall Score: {report.overall_score}/10\n"
    report_text += f"Verdict: {report.verdict}\n\n"

    report_text += "Metrics:\n"
    report_text += f"- Depth: {report.depth_score}/10\n"
    report_text += f"- Structure: {report.structure_score}/10\n"
    report_text += f"- Readability: {report.readability_score}/10\n\n"

    if report.strengths:
        report_text += "Strengths:\n"
        for s in report.strengths:
            report_text += f"• {s}\n"
        report_text += "\n"

    if lexical_issues:
        report_text += "⚠️ Structural Issues Detected:\n"
        for iss in lexical_issues:
            report_text += f"• {iss}\n"
        report_text += "\n"

    if report.issues:
        report_text += f"Content Issues Found: {len(report.issues)}\n"
        for i, issue in enumerate(report.issues, 1):
            report_text += f"{i}. [{issue.issue_type}] {issue.claim}\n"
            report_text += f"   -> Fix: {issue.recommendation}\n\n"
    else:
        report_text += "✅ No content issues found!\n"

    logger.info(f"📊 Overall Score: {report.overall_score}/10 | Verdict: {report.verdict}")
    _emit(
        _job(state), "qa_agent", "completed",
        f"QA Score: {report.overall_score}/10 — {report.verdict}",
        {
            "score": report.overall_score,
            "verdict": report.verdict,
            "issues": len(report.issues) if report.issues else 0
        }
    )

    issues_list = [
        {
            "claim": issue.claim,
            "issue_type": issue.issue_type,
            "severity": issue.severity,
            "recommendation": issue.recommendation,
        }
        for issue in report.issues
    ] if report.issues else []

    return {
        "final": final_text,
        "qa_report": report_text,
        "qa_verdict": report.verdict,
        "qa_issues": issues_list,
        "qa_score": report.overall_score,
    }