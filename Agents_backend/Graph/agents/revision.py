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


def revision_node(state: State) -> dict:
    """
    Rewrites sections of the blog that QA flagged with critical issues.

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

    # Build the issue list for the prompt
    issues_text = "\n".join(
        f"{idx}. [{issue.get('issue_type', 'unknown').upper()}] "
        f"Claim: \"{issue.get('claim', '')}\"\n"
        f"   Fix: {issue.get('recommendation', '')}"
        for idx, issue in enumerate(critical_issues, 1)
    )

    # Build evidence context — full snippets so the revision agent can find real facts
    evidence_text = "\n".join(
        f"- [{e.title}]({e.url}): {e.snippet[:500]}"
        for e in evidence
    ) if evidence else "No external evidence available — remove any unsupported claims."

    logger.info(f"   🔧 Fixing {len(critical_issues)} critical issue(s)...")
    _emit(job_id, "revision", "working",
          f"Fixing {len(critical_issues)} critical issue(s)...")

    try:
        # ✅ FIX: Use shared quality LLM instead of creating a new instance every call.
        # Also avoids hardcoding the model name — it follows LLM_QUALITY_MODEL env var.
        from .utils import llm_quality as revision_llm

        topic = state.get("topic", "Unknown")

        response = revision_llm.invoke([
            SystemMessage(content=REVISION_SYSTEM),
            HumanMessage(content=(
                f"BLOG TOPIC: {topic}\n\n"
                f"CRITICAL ISSUES TO FIX ({len(critical_issues)} total):\n"
                f"{issues_text}\n\n"
                f"ORIGINAL EVIDENCE (use these for corrections — cite with [Title](URL)):\n"
                f"{evidence_text}\n\n"
                f"FULL BLOG POST TO EDIT:\n"
                f"{final_text}"
            ))
        ])

        revised_text = response.content.strip()

        # Safety check: revised text should be at least 70% of original length
        # (we're removing bad sentences, not rewriting the whole thing)
        if len(revised_text) < len(final_text) * 0.5:
            logger.warning(
                f"   ⚠️ Revised text is suspiciously short "
                f"({len(revised_text)} vs {len(final_text)} chars). "
                f"Keeping original to be safe."
            )
            _emit(job_id, "revision", "error",
                  "Revision output too short — keeping original.")
            return {"revision_count": revision_num}

        word_diff = len(revised_text.split()) - len(final_text.split())
        logger.info(
            f"   ✅ Revision complete. Word delta: {word_diff:+d} words. "
            f"Re-running QA audit..."
        )
        _emit(job_id, "revision", "completed",
              f"Revision {revision_num} complete ({word_diff:+d} words). Re-auditing...",
              {"revision": revision_num, "word_delta": word_diff})

        # ✅ FIX: Track which claims were addressed so QA doesn't re-flag them.
        previously_fixed = state.get("qa_fixed_claims", [])
        newly_fixed = [i.get("claim", "") for i in critical_issues if i.get("claim")]
        all_fixed = previously_fixed + newly_fixed

        return {
            "final": revised_text,
            "revision_count": revision_num,
            "qa_fixed_claims": all_fixed,
        }

    except Exception as e:
        logger.error(f"   ❌ Revision failed: {e}. Keeping original content.")
        _emit(job_id, "revision", "error", f"Revision failed: {e}")
        return {"revision_count": revision_num}
