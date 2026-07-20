import re
from langgraph.types import Send
from langchain_core.messages import SystemMessage, HumanMessage

from Graph.state import State, Plan, Task, EvidenceItem
from Graph.templates import WORKER_SYSTEM
from .utils import logger, llm_quality, _job, _emit


def _make_section(task_id: int, content: str) -> tuple:
    """
    The ONLY way a worker should produce a section entry.
    Enforces the (int, str) contract used by merge_content.
    """
    assert isinstance(task_id, int), f"task_id must be int, got {type(task_id)}"
    assert isinstance(content, str), f"content must be str, got {type(content)}"
    return (task_id, content)


def _unpack_section(entry) -> tuple:
    """
    Safely unpack a section entry in merge_content.
    Raises a clear ValueError instead of silently defaulting to 0.
    """
    if not isinstance(entry, (tuple, list)) or len(entry) != 2:
        raise ValueError(
            f"Malformed section entry: expected (int, str) tuple, got {type(entry)}: {entry!r}"
        )
    task_id, content = entry
    if not isinstance(task_id, int):
        raise ValueError(f"Section task_id must be int, got {type(task_id)}: {task_id!r}")
    if not isinstance(content, str):
        raise ValueError(f"Section content must be str, got {type(content)}: {content!r}")
    return task_id, content


def _get_assigned_evidence(task: Task, all_evidence: list) -> list:
    """
    Returns the evidence slice assigned to this task by _assign_evidence_to_tasks()
    in orchestrator.py.

    ✅ FIX: Previously fanout() sent the FULL evidence list to every worker.
    With 9 sections and only 5 evidence items, every worker independently
    chose the same 2-3 most prominent facts (e.g. "70% AI adoption" and
    "GI Genius reduces polyps by 50%"), causing those stats to repeat
    7+ times across a single blog post.

    Now each worker only sees the evidence slice assigned to its task,
    so sections are forced to draw from different sources.

    Fallback: if no indices were assigned (e.g. closed_book mode with no
    evidence, or a plan created before this fix was deployed), the full
    list is returned so the worker can still function.
    """
    indices = task.assigned_evidence_indices if hasattr(task, 'assigned_evidence_indices') else []

    if not indices or not all_evidence:
        return all_evidence  # safe fallback

    return [all_evidence[i] for i in indices if i < len(all_evidence)]


def _get_assigned_evidence_dicts(task: Task, all_evidence_dicts: list) -> list:
    """
    Slices the pre-serialized evidence list using the task's assigned indices.
    Works on dicts (already serialized) so no model_dump() runs per worker.

    Mirrors _get_assigned_evidence() but accepts and returns plain dicts,
    avoiding repeated Pydantic serialization inside the fanout loop.
    """
    indices = task.assigned_evidence_indices if hasattr(task, "assigned_evidence_indices") else []

    if not indices or not all_evidence_dicts:
        return all_evidence_dicts  # safe fallback: full list

    return [all_evidence_dicts[i] for i in indices if i < len(all_evidence_dicts)]


def fanout(state: State):
    """Generates parallel workers for each section."""
    if not state.get("plan"):
        logger.warning("No plan found, skipping fanout.")
        return []

    _emit(_job(state), "writer", "started", f"Dispatching {len(state['plan'].tasks)} parallel writers...")

    all_evidence = state.get("evidence", [])

    # Serialize ALL evidence items ONCE here, before the loop.
    # Previously every Send() called model_dump() on its assigned slice,
    # so shared items were serialized multiple times. Now it happens once.
    all_evidence_dicts = [e.model_dump() for e in all_evidence]

    return [
        Send("worker", {
            "task":     task.model_dump(),
            "topic":    state["topic"],
            "mode":     state["mode"],
            "plan":     state["plan"].model_dump(),
            "_job_id":  state.get("_job_id", ""),

            # Slice the pre-serialized list instead of re-serializing per task
            "evidence": _get_assigned_evidence_dicts(task, all_evidence_dicts),

            # Cost-saving toggle flags
            "generate_images":   state.get("generate_images", True),
            "generate_campaign": state.get("generate_campaign", True),
            "generate_video":    state.get("generate_video", True),
            "generate_podcast":  state.get("generate_podcast", True),
        })
        for task in state["plan"].tasks
    ]


def worker_node(payload: dict) -> dict:
    task     = Task(**payload["task"])
    plan     = Plan(**payload["plan"])
    evidence = [EvidenceItem(**e) for e in payload.get("evidence", [])]
    job_id   = payload.get("_job_id", "")

    _emit(job_id, "writer", "working",
          f"Writing section {task.id + 1}/{len(plan.tasks)}: {task.title}",
          {"section": task.id + 1, "total": len(plan.tasks)})
    logger.info(f"✍️ Writing Section {task.id + 1}/{len(plan.tasks)}: {task.title} "
                f"(Tone: {plan.tone}, Evidence: {len(evidence)} items)")

    try:
        bullets_text   = "\n- " + "\n- ".join(task.bullets)
        evidence_text  = "\n".join(
            f"- [{e.title}]({e.url}) ({e.published_at or 'Unknown Date'})\n  Content: {e.snippet[:300]}"
            for e in evidence[:15]
        )

        section_keywords = task.tags[:3]
        keywords_str     = ", ".join(section_keywords) if section_keywords else "general topic"

        # Build a list of other section titles so the worker knows what
        # topics its siblings are covering — reinforces the inter-section
        # fact-ban in the prompt.
        other_section_titles = [
            f"  - Section {t.id + 1}: {t.title}"
            for t in plan.tasks if t.id != task.id
        ]
        other_sections_str = "\n".join(other_section_titles)

        response = llm_quality.invoke(
            [
                SystemMessage(content=WORKER_SYSTEM.format(
                    tone=plan.tone,
                    keywords=keywords_str,
                    target_words=task.target_words
                )),
                HumanMessage(content=(
                    f"Blog Title: {plan.blog_title}\n"
                    f"Section Number: {task.id + 1} of {len(plan.tasks)}\n"
                    f"Section Title: {task.title}\n"
                    f"Goal: {task.goal}\n"
                    f"Target Words: {task.target_words}\n"
                    f"Tone: {plan.tone} (MAINTAIN THIS TONE CONSISTENTLY)\n"
                    f"Keywords to integrate naturally: {keywords_str}\n"
                    f"Bullets to Cover:{bullets_text}\n\n"
                    f"OTHER SECTIONS IN THIS BLOG (do NOT repeat their facts):\n"
                    f"{other_sections_str}\n\n"
                    f"Available Evidence (Cite these URLs — these are YOUR assigned sources):\n"
                    f"{evidence_text}\n\n"
                    f"CRITICAL INSTRUCTIONS:\n"
                    f"1. Write approximately {task.target_words} words. Prioritize substance — do not add filler to hit the count.\n"
                    f"2. Cover ALL bullet points completely\n"
                    f"3. End with a complete sentence (period/question mark/exclamation)\n"
                    f"4. DO NOT stop mid-sentence or mid-paragraph\n\n"
                    f"Remember: Write in {plan.tone} tone throughout."
                )),
            ],
            max_tokens=3000
        )

        section_md = response.content.strip()

        # Check for unclosed code blocks and close them
        if section_md.count("```") % 2 != 0:
            section_md += "\n```\n"

        lines = section_md.split('\n')
        if lines and re.match(r'^#{1,4}\s+', lines[0]):
            lines      = lines[1:]
            section_md = '\n'.join(lines).strip()
        section_md = f"## {task.title}\n\n{section_md}"

        word_count = len(section_md.split())
        if word_count < (task.target_words * 0.7):
            logger.warning(
                f"Section {task.id + 1} seems short "
                f"({word_count} words, target: {task.target_words})"
            )

        if not section_md.endswith(('.', '!', '?', '"', ')', '`', '```', '```\n')):
            logger.warning(f"Section {task.id + 1} incomplete (doesn't end with punctuation)")
            section_md += "."

        logger.info(f"✅ Completed: {word_count} words")
        _emit(job_id, "writer", "working",
              f"Completed section {task.id + 1}: {task.title} ({word_count} words)",
              {"section": task.id + 1, "words": word_count})

    except Exception as e:
        import traceback
        logger.error(f"Error in section {task.title}: {e}")
        traceback.print_exc()
        section_md = f"## {task.title}\n\n[Error generating content: {str(e)}]"
        _emit(job_id, "writer", "error", f"Failed section {task.id + 1}: {str(e)}")

    return {"sections": [_make_section(task.id, section_md)]}


def merge_content(state: State) -> dict:
    _emit(_job(state), "merger", "started", "Merging all sections into final blog...")
    logger.info("🔗 MERGING SECTIONS ---")
    plan = state["plan"]

    unique_sections = {}

    for entry in state["sections"]:
        try:
            task_id, content = _unpack_section(entry)

            if task_id in unique_sections:
                logger.warning(
                    f"⚠️ Duplicate section detected for task_id={task_id} "
                    f"('{plan.tasks[task_id].title if task_id < len(plan.tasks) else 'unknown'}'). "
                    f"A worker retry likely occurred — keeping the latest version."
                )

            unique_sections[task_id] = content

        except ValueError as e:
            logger.error(f"Skipping malformed section entry: {e}")
            continue

    expected_ids = set(range(len(plan.tasks)))
    received_ids = set(unique_sections.keys())
    missing_ids  = expected_ids - received_ids
    if missing_ids:
        missing_titles = [
            plan.tasks[i].title for i in sorted(missing_ids) if i < len(plan.tasks)
        ]
        logger.warning(
            f"⚠️ {len(missing_ids)} section(s) missing from merge: {missing_titles}. "
            f"These will be absent from the final blog."
        )

    ordered_content = [unique_sections[k] for k in sorted(unique_sections.keys())]

    body       = "\n\n".join(ordered_content).strip()
    merged_md  = f"# {plan.blog_title}\n\n{body}\n"
    word_count = len(merged_md.split())

    logger.info(f"✅ Merged {len(ordered_content)} sections")
    _emit(_job(state), "merger", "completed",
          f"Merged {len(ordered_content)} sections ({word_count} words)",
          {"sections": len(ordered_content), "words": word_count})
    _emit(_job(state), "writer", "completed",
          f"All {len(ordered_content)} sections written",
          {"sections": len(ordered_content), "words": word_count})

    return {"merged_md": merged_md, "final": merged_md}