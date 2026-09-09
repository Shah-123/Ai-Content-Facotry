"""
Golden Test Harness — End-to-End Pipeline Regression
=====================================================
Runs the full LangGraph pipeline against a curated list of topics and
asserts the output meets documented quality bounds (QA score, evidence
count, word count, etc.).

These tests:
  - Cost real API tokens (OpenAI + Tavily + optionally Gemini)
  - Take several minutes per topic to complete
  - Therefore skip by default — only run when explicitly enabled

Usage
-----
Run only the cheap unit tests (default):
    pytest

Run the golden harness explicitly:
    $env:RUN_GOLDEN_TESTS=1; pytest tests/golden -v -s

Or filter to a single topic:
    $env:RUN_GOLDEN_TESTS=1; pytest tests/golden -k closed_book_evergreen -v -s

What the harness checks
-----------------------
For each topic in `topics.json`, the harness runs the pipeline end-to-end
and asserts the final state satisfies the documented `expected` ranges:
  - min_word_count               — final blog must be at least N words
  - min_qa_score                 — QA agent score must clear floor
  - min_blog_evaluator_score     — independent reader-grade evaluator floor
  - qa_verdict_in                — verdict must be in this allow-list
  - min_evidence_count           — research must surface at least N citations
  - max_critical_issues          — at most N critical QA issues
  - expected_mode_in             — router must pick a mode in this list

These bounds are deliberately permissive so prompt tweaks don't cause
flaky failures — they exist to catch genuine regressions (e.g. word
count collapsing to 200, or QA score dropping below 5).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any

import pytest

# --- Skip the entire module unless explicitly opted in ---------------------
RUN_GOLDEN = os.getenv("RUN_GOLDEN_TESTS", "0") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_GOLDEN,
    reason=(
        "Golden tests cost real API tokens and take minutes per topic. "
        "Set RUN_GOLDEN_TESTS=1 to enable."
    ),
)

# --- Load the golden topic fixture once at module level --------------------
_GOLDEN_DIR = Path(__file__).parent
_TOPICS_FILE = _GOLDEN_DIR / "topics.json"

with _TOPICS_FILE.open("r", encoding="utf-8") as f:
    _GOLDEN = json.load(f)

_TOPIC_CASES = _GOLDEN["topics"]


# ===========================================================================
# Helpers
# ===========================================================================

# Writer model for the run. Override to compare arms while holding the JUDGE
# fixed — the in-house G-Eval judge reads LLM_QUALITY_MODEL, not this, so
# varying only this keeps scores comparable across models:
#     GOLDEN_MODEL=gpt-4o-mini RUN_GOLDEN_TESTS=1 pytest tests/golden -v -s
GOLDEN_MODEL = os.getenv("GOLDEN_MODEL", "gpt-5-mini")

# Ablation switch for the evidence-distribution experiment.
#   GOLDEN_ASSIGN_EVIDENCE=1 (default) -> workers receive disjoint evidence slices
#   GOLDEN_ASSIGN_EVIDENCE=0           -> workers receive the full pool (pre-fix)
# Artefacts are written to an arm-suffixed directory so both arms can be
# collected without overwriting each other.
ASSIGN_EVIDENCE = os.getenv("GOLDEN_ASSIGN_EVIDENCE", "1") != "0"
ARM = "assigned" if ASSIGN_EVIDENCE else "fullpool"


def _run_dir(case_id: str) -> Path:
    """Artefact directory for one case under the current ablation arm."""
    return _GOLDEN_DIR / "_runs" / f"{case_id}__{ARM}"


def _build_initial_state(case: dict) -> dict:
    """Construct the initial graph state for a single golden topic.

    Delegates to the API's build_initial_state() so this harness cannot drift
    from what the web app actually sends the graph. That drift is not
    hypothetical — `generate_qa` was missing from the State schema for every
    web run while this file set it correctly, and the mismatch went unnoticed
    because these tests were never executed.
    """
    from api.background import build_initial_state
    from api.schemas import GenerationConfig

    config = GenerationConfig(
        tone=case.get("tone", "professional"),
        sections=case.get("sections", 3),
        selected_model=case.get("model", GOLDEN_MODEL),
        generate_qa=True,
        # Media generation is slow and expensive; the graph edges it guards are
        # exercised by unit tests instead.
        generate_images=False,
        generate_campaign=False,
        generate_video=False,
        generate_podcast=False,
        export_formats=[],
        # Ablation arm. A per-case override wins over the environment default,
        # so a fixture can pin itself to one arm if it ever needs to.
        assign_evidence=case.get("assign_evidence", ASSIGN_EVIDENCE),
    )
    return build_initial_state(
        job_id=f"golden_{case['id']}_{ARM}",
        topic=case["topic"],
        blog_folder=str(_run_dir(case["id"])),
        generation_config=config,
    )


def _run_pipeline(case: dict) -> dict[str, Any]:
    """Run the full graph for one topic and return the terminal state values."""
    # Late imports so unit-test runs (which skip this module) never touch
    # langgraph / langchain heavy machinery.
    from main import build_graph
    import uuid as _uuid

    import usage

    _run_dir(case["id"]).mkdir(parents=True, exist_ok=True)

    # Token accounting baseline. Taken here rather than via a contextvar because
    # LangGraph dispatches the section writers to worker threads, which
    # contextvar-based accounting does not follow — and those writers are the
    # bulk of a run's spend.
    usage_before = usage.snapshot()

    app = build_graph()
    thread = {"configurable": {"thread_id": f"golden_{_uuid.uuid4().hex[:12]}"}}

    initial_state = _build_initial_state(case)

    # Phase 1: research + plan (graph interrupts after orchestrator for HITL)
    for _ in app.stream(initial_state, thread, stream_mode="values"):
        pass

    # Phase 2: auto-approve and run the rest
    for _ in app.stream(None, thread, stream_mode="values", recursion_limit=150):
        pass

    values = dict(app.get_state(thread).values)
    # Attached under a private key so it reaches _save_run_artifacts without
    # being declared in the graph State (LangGraph would drop it anyway).
    values["_usage"] = usage.delta(usage_before)
    return values


def _save_run_artifacts(case: dict, final_state: dict[str, Any]) -> Path:
    """Persist per-run metrics and the QA report next to the run folder.

    The harness previously asserted against in-memory state and saved nothing,
    so a passing run left no evidence behind. These files are the raw data for
    the report's results table, and `qa_report.txt` is the artifact that shows
    the QA agent genuinely executed.

    Writes to tests/golden/_runs/<case_id>/ (gitignored).
    """
    run_dir = _run_dir(case["id"])
    run_dir.mkdir(parents=True, exist_ok=True)

    # Deterministic repetition / source-spread measurement. These are the
    # dependent variables for the evidence-distribution ablation; no model is
    # involved in computing them, so the numbers are not subject to judge bias.
    from tests.golden.metrics import article_metrics
    final_md = final_state.get("final", "")

    geval = final_state.get("geval_scores") or {}
    summary = {
        "case_id": case["id"],
        "topic": case["topic"],
        "run_at": _dt.datetime.now().isoformat(timespec="seconds"),
        # Which ablation arm produced this run.
        "arm": ARM,
        "assign_evidence": case.get("assign_evidence", ASSIGN_EVIDENCE),
        # Recorded so the report can state exactly which model produced these
        # numbers, and so writer-model arms stay distinguishable.
        "writer_model": case.get("model", GOLDEN_MODEL),
        # The judge is LLM_JUDGE_MODEL, which falls back to LLM_QUALITY_MODEL.
        # Recording the resolved value (not the raw env var) is what makes a run
        # attributable — and makes a same-model writer/judge pair visible.
        "judge_model": os.getenv(
            "LLM_JUDGE_MODEL", os.getenv("LLM_QUALITY_MODEL", "gpt-5-mini")
        ),
        "independent_judge": os.getenv(
            "LLM_JUDGE_MODEL", os.getenv("LLM_QUALITY_MODEL", "gpt-5-mini")
        ) != case.get("model", GOLDEN_MODEL),
        "tone": case.get("tone", "professional"),
        "router_mode": final_state.get("mode"),
        "word_count": len(final_state.get("final", "").split()),
        "evidence_count": len(final_state.get("evidence", [])),
        "qa_score": final_state.get("qa_score"),
        "qa_verdict": final_state.get("qa_verdict"),
        "qa_critical_issues": sum(
            1 for i in final_state.get("qa_issues", []) if i.get("severity") == "critical"
        ),
        "revision_count": final_state.get("revision_count", 0),
        "blog_evaluator_score": final_state.get("blog_evaluator_score"),
        "geval": {
            dim: (geval.get(dim) or {}).get("score")
            for dim in ("coherence", "relevance", "accuracy", "tone_alignment")
        },
        "geval_overall": geval.get("overall_score"),
        # Ablation dependent variables (deterministic, no LLM involved).
        **article_metrics(final_md),
        # Token counts and estimated cost for this run (see usage.py).
        "usage": final_state.get("_usage", {}),
    }

    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    if final_state.get("qa_report"):
        (run_dir / "qa_report.txt").write_text(final_state["qa_report"], encoding="utf-8")
    if final_state.get("final"):
        (run_dir / "blog.md").write_text(final_state["final"], encoding="utf-8")

    return run_dir


def _assert_within_bounds(case: dict, final_state: dict[str, Any]) -> list[str]:
    """
    Check the terminal state against the case's `expected` ranges.

    Returns a list of failure messages (empty list = all checks passed).
    Collecting failures instead of raising on the first one means a single
    pytest run surfaces every issue at once.
    """
    expected = case["expected"]
    failures: list[str] = []

    final = final_state.get("final", "")
    word_count = len(final.split())
    if word_count < expected["min_word_count"]:
        failures.append(
            f"word_count={word_count} < min_word_count={expected['min_word_count']}"
        )

    qa_score = final_state.get("qa_score") or 0
    if qa_score < expected["min_qa_score"]:
        failures.append(
            f"qa_score={qa_score} < min_qa_score={expected['min_qa_score']}"
        )

    eval_score = final_state.get("blog_evaluator_score") or 0
    if eval_score < expected["min_blog_evaluator_score"]:
        failures.append(
            f"blog_evaluator_score={eval_score} < "
            f"min_blog_evaluator_score={expected['min_blog_evaluator_score']}"
        )

    verdict = final_state.get("qa_verdict")
    if verdict not in expected["qa_verdict_in"]:
        failures.append(
            f"qa_verdict={verdict!r} not in {expected['qa_verdict_in']}"
        )

    evidence = final_state.get("evidence", [])
    if len(evidence) < expected["min_evidence_count"]:
        failures.append(
            f"evidence_count={len(evidence)} < "
            f"min_evidence_count={expected['min_evidence_count']}"
        )

    issues = final_state.get("qa_issues", [])
    critical = sum(1 for i in issues if i.get("severity") == "critical")
    if critical > expected["max_critical_issues"]:
        failures.append(
            f"critical_issues={critical} > "
            f"max_critical_issues={expected['max_critical_issues']}"
        )

    mode = final_state.get("mode")
    if mode not in expected["expected_mode_in"]:
        failures.append(
            f"router mode={mode!r} not in {expected['expected_mode_in']}"
        )

    return failures


# ===========================================================================
# Parametrized golden test
# ===========================================================================

@pytest.mark.parametrize(
    "case",
    _TOPIC_CASES,
    ids=[c["id"] for c in _TOPIC_CASES],
)
def test_golden_topic(case: dict) -> None:
    """
    Run the full pipeline for one golden topic and verify it stays within
    the documented quality bounds. Designed to catch genuine regressions
    (output collapse, prompt drift), not micro-fluctuations in scores.
    """
    final_state = _run_pipeline(case)

    # Save BEFORE asserting: a run that violates a bound is exactly the one
    # whose artifacts you want to inspect.
    run_dir = _save_run_artifacts(case, final_state)

    # Diagnostic dump — printed when -s is used, stays silent otherwise
    rep = (final_state.get("final") and
           __import__("tests.golden.metrics", fromlist=["x"]).repeated_statistics(
               final_state["final"])) or {}
    print(
        f"\n[{case['id']}] arm={ARM} "
        f"repeat_rate={rep.get('repetition_rate')} "
        f"max_spread={rep.get('max_section_spread')} "
        f"model={case.get('model', GOLDEN_MODEL)} "
        f"qa={final_state.get('qa_score')} "
        f"eval={final_state.get('blog_evaluator_score')} "
        f"geval={(final_state.get('geval_scores') or {}).get('overall_score')} "
        f"words={len(final_state.get('final', '').split())} "
        f"evidence={len(final_state.get('evidence', []))} "
        f"verdict={final_state.get('qa_verdict')} "
        f"mode={final_state.get('mode')} "
        f"→ {run_dir}"
    )

    # A null qa_score means the QA agent never ran (the regression that hid
    # behind the State schema), not that it ran and scored badly. Call it out
    # distinctly so a real structural break isn't read as a quality dip.
    if final_state.get("qa_score") is None:
        pytest.fail(
            f"'{case['id']}': qa_score is None — the QA agent did not execute. "
            f"Check that 'generate_qa' is still declared in Graph.state.State "
            f"(see tests/test_state_schema.py)."
        )

    failures = _assert_within_bounds(case, final_state)
    if failures:
        joined = "\n  - ".join(failures)
        pytest.fail(f"Golden bounds violated for '{case['id']}':\n  - {joined}")
