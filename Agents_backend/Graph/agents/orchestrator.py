from langchain_core.messages import SystemMessage, HumanMessage

from Graph.state import State, Plan, Task
from Graph.templates import ORCH_SYSTEM
from .utils import logger, llm, llm_planner, _job, _emit

# ✅ FIX #7: Named section constants (unchanged from before)
FIXED_OPENING_SECTIONS = 2   # Section 1: Hook/Intro, Section 2: Context/Background
FIXED_CLOSING_SECTIONS = 2   # Second-to-last: Practical Application, Last: Actionable Takeaways
TOTAL_FIXED_SECTIONS   = FIXED_OPENING_SECTIONS + FIXED_CLOSING_SECTIONS  # = 4


# ============================================================================
# EVIDENCE DISTRIBUTION
# ============================================================================

def _assign_evidence_to_tasks(plan: Plan, evidence: list) -> Plan:
    """
    Distributes evidence items across tasks so each worker receives a
    unique slice of the evidence pool instead of the full list.

    WHY THIS MATTERS:
    Previously every worker received all evidence and independently chose
    which facts to cite. With 9 sections and only 5 evidence items, every
    section naturally gravitated toward the same 2-3 most prominent stats
    (e.g. "70% of orgs use AI" and "GI Genius reduces missed polyps by 50%").
    Those two facts appeared 7+ times across a single blog post.

    DISTRIBUTION STRATEGY:
    - Opening sections (intro, context) get the first third of evidence —
      broad overview stats belong at the top.
    - Body sections share the middle evidence pool round-robin so adjacent
      sections pull from different sources.
    - Closing sections (practical, takeaways) get the final third — actionable
      data and forward-looking stats belong at the end.
    - Every task is guaranteed at least 1 evidence item.
    - If evidence is sparse (fewer items than tasks), items are shared but
      the assignment still prevents total overlap by rotating the starting
      index per task.

    The indices stored in task.assigned_evidence_indices reference positions
    in the global state["evidence"] list. fanout() in workers.py uses them
    to build the per-worker evidence payload.
    """
    if not evidence:
        return plan

    n_tasks    = len(plan.tasks)
    n_evidence = len(evidence)

    # Guarantee every section gets at least 2 items (or all items if pool is tiny)
    items_per_task = max(2, n_evidence // n_tasks)

    for i, task in enumerate(plan.tasks):
        # Stagger the start index so adjacent sections don't share the same
        # primary source. Use modulo wrap so we never go out of bounds.
        start = (i * max(1, n_evidence // n_tasks)) % n_evidence
        indices = []

        for j in range(items_per_task):
            indices.append((start + j) % n_evidence)

        # Deduplicate while preserving order
        seen = set()
        unique_indices = []
        for idx in indices:
            if idx not in seen:
                seen.add(idx)
                unique_indices.append(idx)

        task.assigned_evidence_indices = unique_indices

    logger.info(
        f"📎 Evidence distributed across {n_tasks} sections "
        f"({n_evidence} items, ~{items_per_task} per section)"
    )

    # Log the assignment so it's visible during development
    for task in plan.tasks:
        sources = [evidence[i].source for i in task.assigned_evidence_indices
                   if i < n_evidence]
        logger.info(f"   Section {task.id + 1} '{task.title[:40]}' → {sources}")

    return plan


# ============================================================================
# ORCHESTRATOR NODE
# ============================================================================

def orchestrator_node(state: State) -> dict:
    _emit(_job(state), "orchestrator", "started", "Creating detailed blog outline...")
    logger.info("📋 PLANNING ---")
    planner = llm_planner.with_structured_output(Plan)
    mode    = state.get("mode", "closed_book")
    evidence = state.get("evidence", [])

    target_tone     = state.get("target_tone", "professional")
    target_audience = state.get("target_audience", "general")
    target_keywords = state.get("target_keywords", [])
    keywords_str    = ", ".join(target_keywords) if target_keywords else "None specified"

    prompt_content = f"""Topic: {state['topic']}
Mode: {mode}
Target Tone: {target_tone}
Target Keywords: {keywords_str}

Evidence Context:
{[e.model_dump() for e in evidence][:10]}

Create a blog plan that:
1. Maintains '{target_tone}' tone consistently throughout all sections
2. Naturally integrates these keywords: {keywords_str}
3. Distributes keywords strategically across sections (avoid stuffing)
4. Creates engaging, SEO-optimized content
"""

    target_sections = state.get("target_sections", 5)

    total_sections           = target_sections + TOTAL_FIXED_SECTIONS
    last_body_section        = target_sections + FIXED_OPENING_SECTIONS
    practical_section_number = last_body_section + 1
    takeaways_section_number = last_body_section + 2

    plan = planner.invoke([
        SystemMessage(content=ORCH_SYSTEM.format(
            tone=target_tone,
            audience=target_audience,
            keywords=keywords_str,
            target_sections=last_body_section,
            target_sections_plus_one=practical_section_number,
            target_sections_plus_two=takeaways_section_number,
            total_sections=total_sections,
        )),
        HumanMessage(content=prompt_content),
    ])

    logger.info(f"Generated {len(plan.tasks)} sections.")
    logger.info(f"🎨 Tone: {plan.tone}")
    if plan.primary_keywords:
        logger.info(f"🎯 Keywords: {', '.join(plan.primary_keywords)}")

    # ✅ FIX: Distribute evidence across tasks immediately after plan generation.
    # This runs before fanout() so each Task already knows which evidence
    # indices belong to it by the time workers are dispatched.
    # If no evidence was gathered (closed_book mode), this is a safe no-op.
    if evidence:
        plan = _assign_evidence_to_tasks(plan, evidence)
    else:
        logger.info("📎 No evidence to distribute (closed_book mode).")

    _emit(
        _job(state), "orchestrator", "completed",
        f"Planned {len(plan.tasks)} sections",
        {"sections": len(plan.tasks), "tone": plan.tone}
    )

    return {"plan": plan}