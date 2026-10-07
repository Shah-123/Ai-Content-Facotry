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


# ---------------------------------------------------------------------------
# section_title survives QA, so revision can target one section
# ---------------------------------------------------------------------------
# qa_agent_node used to build its issue dicts without section_title, so the
# title match in revision_node never fired; a paraphrased claim or a citation
# issue then matched no section and the whole article was rewritten.

from unittest.mock import patch

from Graph.agents import quality_control as qc
from Graph.state import EvidenceItem
from Graph.structured_data import QAIssue, QAReport

ARTICLE = (
    "# Title\n\n"
    "Intro with a [stray](https://stray.example/a) link.\n\n"
    "## Alpha\n\n"
    "Alpha cites [a source](https://good.example/x) properly.\n\n"
    "## Beta\n\n"
    "Beta cites [an invention](https://bad.example/y) instead.\n"
)
ALL_GOOD = ["https://good.example/x", "https://stray.example/a", "https://bad.example/y"]


def _evidence(*urls):
    return [EvidenceItem(title="T", url=u, snippet="S", published_at=None, source="x.com") for u in urls]


def _audit(issues, evidence=ALL_GOOD):
    report = QAReport(depth_score=7, structure_score=7, readability_score=7, overall_score=8,
                      verdict="READY", issues=issues, strengths=["clear"])
    fake = SimpleNamespace(with_structured_output=lambda _s: SimpleNamespace(invoke=lambda _m: report))
    with patch.object(qc, "llm_quality", fake):
        return qc.qa_agent_node({"final": ARTICLE, "evidence": _evidence(*evidence), "_job_id": ""})


def test_a_bad_link_names_the_section_it_sits_in():
    issues, _ = verify_citations(ARTICLE, _evidence("https://good.example/x"))
    assert {i["claim"]: i["section_title"] for i in issues} == {
        "Link '[stray](https://stray.example/a)'": None,  # before the first H2
        "Link '[an invention](https://bad.example/y)'": "Beta",
    }


def test_qa_issues_keep_the_section_title_the_model_gave():
    out = _audit([QAIssue(claim="an invented statistic", section_title="Alpha",
                          issue_type="fact_error", severity="critical", recommendation="remove it")])
    assert [i["section_title"] for i in out["qa_issues"]] == ["Alpha"]


def test_citation_issues_get_their_section_whether_injected_or_echoed():
    echoed = QAIssue(claim="Link '[an invention](https://bad.example/y)'", issue_type="hallucination",
                     severity="critical", recommendation="replace it")
    out = _audit([echoed], evidence=["https://good.example/x"])
    assert {i["claim"]: i["section_title"] for i in out["qa_issues"]} == {
        "Link '[an invention](https://bad.example/y)'": "Beta",  # echoed: filled in
        "Link '[stray](https://stray.example/a)'": None,         # injected
    }


def test_a_paraphrased_claim_is_revised_in_its_own_section_only():
    from Graph.agents import revision, utils

    qa = _audit([QAIssue(claim="a paraphrase that appears nowhere in the text", section_title="Beta",
                         issue_type="fact_error", severity="critical", recommendation="fix it")])
    prompts = []

    def _invoke(messages):
        prompts.append(messages[1].content)
        return SimpleNamespace(content="A rewritten section body. " * 10)

    with patch.object(utils, "llm_quality", SimpleNamespace(invoke=_invoke)):
        out = revision.revision_node({"final": ARTICLE, "qa_issues": qa["qa_issues"]})

    assert len(prompts) == 1 and "Beta" in prompts[0]
    assert "Alpha cites [a source](https://good.example/x) properly." in out["final"]  # untouched
    assert "A rewritten section body." in out["final"]
