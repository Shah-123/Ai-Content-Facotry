"""
Automated Revision Agent
========================
When the QA agent detects critical issues (hallucinated stats, fabricated
case studies, factual errors), this node rewrites ONLY the problematic
paragraphs and returns the cleaned text for re-audit.

Graph position:
    qa_agent → _after_qa (critical + revision_count < MAX) → revision_node → qa_agent (loop)

Max 2 revision loops to prevent infinite cycles and excessive API cost.
After 2 failed revisions, the pipeline proceeds with the DRAFT flag.
"""

from langchain_core.messages import SystemMessage, HumanMessage

from Graph.state import State
from .utils import logger, _job, _emit

# Maximum number of revision attempts before giving up and proceeding with DRAFT.
MAX_REVISIONS = 2

REVISION_SYSTEM = """You are a surgical content editor. Your job is to fix SPECIFIC factual 
issues flagged by a quality audit — nothing else.

RULES:
1. You will receive the FULL blog post, a list of CRITICAL issues, and the ORIGINAL EVIDENCE.
2. For each flagged issue:
   - FIRST, search the AVAILABLE EVIDENCE for a real fact that can replace the bad claim.
   - If you find matching evidence → REWRITE the sentence using that evidence with a proper
     inline citation in the format: [Source Title](URL).
   - If NO evidence supports the claim → REMOVE the sentence entirely and smooth the 
     surrounding paragraph so it flows naturally.
   - If the claim references a non-existent study/tool/company → REMOVE the reference 
     and replace with a general, defensible statement about the concept.
3. DO NOT change any part of the blog that is NOT flagged.
4. DO NOT add new sections, headings, or paragraphs.
5. DO NOT change the tone, style, or structure.
6. DO NOT invent replacement statistics or facts — ONLY use what is in the evidence.
7. Preserve all Markdown formatting exactly (##, **, [], images).
8. Return the COMPLETE blog post with your targeted fixes applied.

Think of yourself as a fact-checker with the original research in hand. For every flagged 
claim, either cite a real source or remove the claim entirely. Never guess."""


def _parse_sections_by_h2(md_text: str) -> list[dict]:
    """Parses markdown into preamble and H2 section blocks: [{title, header, body}]."""
    lines = md_text.splitlines()
    sections = []
    current_title = "Preamble"
    current_header = ""
    current_lines = []

    for line in lines:
        if line.startswith("## "):
            if current_lines or current_title != "Preamble":
                sections.append({
                    "title": current_title,
                    "header": current_header,
                    "body": "\n".join(current_lines).strip()
                })
            current_title = line[3:].strip()
            current_header = line
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines or current_title != "Preamble":
        sections.append({
            "title": current_title,
            "header": current_header,
            "body": "\n".join(current_lines).strip()
        })

    return sections


def revision_node(state: State) -> dict:
    """
    Rewrites sections of the blog that QA flagged with critical issues.
    Performs targeted section-level revisions whenever specific sections are identified.

    Reads: state["final"], state["qa_issues"], state["evidence"], state["revision_count"]
    Writes: state["final"] (updated), state["revision_count"] (incremented)
    """
    revision_num = state.get("revision_count", 0) + 1
    job_id = _job(state)

    _emit(job_id, "revision", "started",
          f"🔄 Revision loop {revision_num}/{MAX_REVISIONS} — fixing critical QA issues...")
    logger.info(f"🔄 REVISION LOOP {revision_num}/{MAX_REVISIONS} ---")

    final_text = state.get("final", "")
    qa_issues = state.get("qa_issues", [])
    evidence = state.get("evidence", [])

    # Only fix critical issues — minor/suggestion issues are not worth a rewrite
    critical_issues = [i for i in qa_issues if i.get("severity") == "critical"]

    if not critical_issues:
        logger.info("   ✅ No critical issues to fix. Skipping revision.")
        _emit(job_id, "revision", "completed", "No critical issues found — skipping.")
        return {"revision_count": revision_num}

    # Build evidence context — full snippets so the revision agent can find real facts
    evidence_text = "\n".join(
        f"- [{e.title}]({e.url}): {e.snippet[:500]}"
        for e in evidence
    ) if evidence else "No external evidence available — remove any unsupported claims."

    from .utils import llm_quality as revision_llm
    topic = state.get("topic", "Unknown")

    # Try targeted section-level revision
    sections = _parse_sections_by_h2(final_text)
    flagged_sections = {}

    for issue in critical_issues:
        claim = (issue.get("claim") or "").strip()
        target_title = (issue.get("section_title") or "").strip()

        matched_section_idx = None
        for idx, sec in enumerate(sections):
            if target_title and target_title.lower() in sec["title"].lower():
                matched_section_idx = idx
                break
            if claim and claim.lower() in sec["body"].lower():
                matched_section_idx = idx
                break

        if matched_section_idx is not None:
            flagged_sections.setdefault(matched_section_idx, []).append(issue)

    if flagged_sections and len(sections) > 1:
        logger.info(f"   🎯 Targeted revision: fixing {len(flagged_sections)} specific section(s)...")
        _emit(job_id, "revision", "working", f"Targeted surgical revision on {len(flagged_sections)} section(s)...")

        for sec_idx, issues in flagged_sections.items():
            sec = sections[sec_idx]
            issues_text = "\n".join(
                f"- Claim: \"{i.get('claim', '')}\"\n  Fix: {i.get('recommendation', '')}"
                for i in issues
            )
            prompt = (
                f"BLOG TOPIC: {topic}\n"
                f"SECTION TITLE: {sec['title']}\n\n"
                f"SECTION TEXT TO REVISE:\n{sec['body']}\n\n"
                f"QA ISSUES TO FIX IN THIS SECTION:\n{issues_text}\n\n"
                f"AVAILABLE EVIDENCE FOR CORRECTIONS:\n{evidence_text}\n\n"
                f"INSTRUCTIONS:\n"
                f"Rewrite ONLY this section to fix the flagged claims while maintaining narrative flow. "
                f"Do NOT include the H2 header in your output. Return only the revised section body."
            )
            try:
                res = revision_llm.invoke([
                    SystemMessage(content=REVISION_SYSTEM),
                    HumanMessage(content=prompt)
                ])
                revised_body = res.content.strip()
                if revised_body and len(revised_body) > 100:
                    sections[sec_idx]["body"] = revised_body
            except Exception as exc:
                logger.warning(f"   ⚠️ Section revision for '{sec['title']}' failed: {exc}")

        # Reassemble full text
        reassembled = []
        for sec in sections:
            if sec["header"]:
                reassembled.append(sec["header"])
            if sec["body"]:
                reassembled.append(sec["body"])
            reassembled.append("")
        revised_text = "\n\n".join(reassembled).strip()
    else:
        # Fallback: Full article editing when issue spans entire post
        logger.info(f"   🔧 Full article revision: fixing {len(critical_issues)} critical issue(s)...")
        _emit(job_id, "revision", "working", f"Fixing {len(critical_issues)} critical issue(s)...")

        issues_text = "\n".join(
            f"{idx}. [{issue.get('issue_type', 'unknown').upper()}] "
            f"Claim: \"{issue.get('claim', '')}\"\n"
            f"   Fix: {issue.get('recommendation', '')}"
            for idx, issue in enumerate(critical_issues, 1)
        )

        try:
            response = revision_llm.invoke([
                SystemMessage(content=REVISION_SYSTEM),
                HumanMessage(content=(
                    f"BLOG TOPIC: {topic}\n\n"
                    f"CRITICAL ISSUES TO FIX ({len(critical_issues)} total):\n"
                    f"{issues_text}\n\n"
                    f"ORIGINAL EVIDENCE:\n"
                    f"{evidence_text}\n\n"
                    f"FULL BLOG POST TO EDIT:\n"
                    f"{final_text}"
                ))
            ])
            revised_text = response.content.strip()
        except Exception as e:
            logger.error(f"   ❌ Full revision failed: {e}. Keeping original content.")
            _emit(job_id, "revision", "error", f"Revision failed: {e}")
            return {"revision_count": revision_num}

    # Safety check: revised text should be at least 60% of original length
    if len(revised_text) < len(final_text) * 0.6:
        logger.warning(
            f"   ⚠️ Revised text is suspiciously short "
            f"({len(revised_text)} vs {len(final_text)} chars). Keeping original to be safe."
        )
        _emit(job_id, "revision", "error", "Revision output too short — keeping original.")
        return {"revision_count": revision_num}

    word_diff = len(revised_text.split()) - len(final_text.split())
    logger.info(f"   ✅ Revision complete. Word delta: {word_diff:+d} words. Re-running QA audit...")
    _emit(job_id, "revision", "completed",
          f"Revision {revision_num} complete ({word_diff:+d} words). Re-auditing...",
          {"revision": revision_num, "word_delta": word_diff})

    previously_fixed = state.get("qa_fixed_claims", [])
    newly_fixed = [i.get("claim", "") for i in critical_issues if i.get("claim")]
    all_fixed = previously_fixed + newly_fixed

    return {
        "final": revised_text,
        "revision_count": revision_num,
        "qa_fixed_claims": all_fixed,
    }
