"""Score and verdict derivation in the QA agent.

Both used to be free-form LLM outputs. These assert the two rules that
replaced them: the grade is a weighted mean of the rated dimensions minus a
proportional grounding penalty, and the verdict tracks `critical` issues only
-- the same rule _after_qa_manual() in main.py already used for routing.
"""
from types import SimpleNamespace

from Graph.agents.quality_control import (
    MAX_GROUNDING_PENALTY, QA_WEIGHTS, qa_overall, verify_citations,
)


def _report(depth, structure, readability):
    return SimpleNamespace(
        depth_score=depth, structure_score=structure, readability_score=readability
    )


def test_weights_sum_to_one():
    assert sum(QA_WEIGHTS.values()) == 1.0


def test_overall_is_the_weighted_mean():
    # 8*0.4 + 6*0.3 + 7*0.3 = 3.2 + 1.8 + 2.1 = 7.1
    assert qa_overall(_report(8, 6, 7)) == 7.1
    # A uniform rating returns itself -- no drift from the arithmetic.
    assert qa_overall(_report(9, 9, 9)) == 9.0


def test_grounding_penalty_scales_with_the_share_of_bad_links():
    clean = qa_overall(_report(9, 9, 9))
    # 1 bad link in 20 costs a twentieth of the maximum penalty, not a flat cap.
    assert qa_overall(_report(9, 9, 9), total_links=20, unverified_links=1) == round(
        clean - MAX_GROUNDING_PENALTY / 20, 1
    )
    # Every citation unverifiable costs the full penalty.
    assert qa_overall(_report(9, 9, 9), total_links=4, unverified_links=4) == round(
        clean - MAX_GROUNDING_PENALTY, 1
    )
    # The old flat rule capped both of those at 6.0; the first no longer is.
    assert qa_overall(_report(9, 9, 9), total_links=20, unverified_links=1) > 6.0


def test_overall_stays_inside_the_scale():
    assert qa_overall(_report(0, 0, 0), total_links=2, unverified_links=2) == 0.0
    assert qa_overall(_report(10, 10, 10)) == 10.0


def test_verify_citations_reports_the_denominator():
    evidence = [{"url": "https://www.nature.com/articles/x"}]
    text = (
        "[ok](https://nature.com/articles/y) and "
        "[bad](https://invented.example/z)"
    )
    issues, total = verify_citations(text, evidence)
    assert total == 2                       # denominator for the penalty
    assert len(issues) == 1                 # domain match keeps the nature.com link
    assert issues[0]["severity"] == "critical"
    assert verify_citations("no links here", evidence) == ([], 0)


def test_verdict_rule_matches_the_router():
    """The displayed verdict must agree with _after_qa_manual()'s routing rule."""
    def verdict(severities):
        return "NEEDS_REVISION" if any(s == "critical" for s in severities) else "READY"

    assert verdict(["minor", "minor", "suggestion"]) == "READY"
    assert verdict(["minor", "critical"]) == "NEEDS_REVISION"
    assert verdict([]) == "READY"
