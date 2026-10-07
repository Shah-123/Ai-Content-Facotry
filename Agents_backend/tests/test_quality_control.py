"""
QA issues must say which section they are in, and manual QA must see the evidence.

Both were latency bugs as much as correctness bugs:

  * `qa_agent_node` built its issue dicts without `section_title`, so the title
    match in `revision_node` could never fire. Matching fell back to the claim
    appearing verbatim in a section, which a paraphrased claim never does, and a
    citation issue ("Link '[text](url)'") never does either. No match means the
    whole article goes through the model and comes back whole.
  * The manual "Run QA" task never loaded research/evidence.json, so every link
    in the article was reported as fabricated: the verdict was forced to
    NEEDS_REVISION, then the article was rewritten and audited a second time.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

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


def _evidence(url: str) -> EvidenceItem:
    return EvidenceItem(title="T", url=url, snippet="S", published_at=None, source="x.com")


# ---------------------------------------------------------------------------
# verify_citations names the section
# ---------------------------------------------------------------------------


def test_a_bad_link_names_the_section_it_sits_in():
    issues = qc.verify_citations(ARTICLE, [_evidence("https://good.example/x")])

    assert {i["claim"]: i["section_title"] for i in issues} == {
        "Link '[stray](https://stray.example/a)'": None,  # before the first H2
        "Link '[an invention](https://bad.example/y)'": "Beta",
    }


# ---------------------------------------------------------------------------
# qa_agent_node keeps section_title
# ---------------------------------------------------------------------------


def _audit(issues: list[QAIssue], evidence: list) -> dict:
    report = QAReport(
        depth_score=7, structure_score=7, readability_score=7, overall_score=8,
        verdict="READY", issues=issues, strengths=["clear"],
    )

    class _Checker:
        def invoke(self, _messages):
            return report

    fake = SimpleNamespace(with_structured_output=lambda _schema: _Checker())
    with patch.object(qc, "llm_quality", fake):
        return qc.qa_agent_node({"final": ARTICLE, "evidence": evidence, "_job_id": ""})


def test_qa_issues_keep_the_section_title_the_model_gave():
    out = _audit(
        [QAIssue(claim="an invented statistic", section_title="Alpha", issue_type="fact_error",
                 severity="critical", recommendation="remove it")],
        evidence=[_evidence("https://good.example/x"), _evidence("https://stray.example/a"),
                  _evidence("https://bad.example/y")],
    )
    assert [i["section_title"] for i in out["qa_issues"]] == ["Alpha"]


def test_citation_issues_get_their_section_whether_injected_or_echoed_by_the_model():
    echoed = QAIssue(  # the model repeated the scanner's finding but left the section out
        claim="Link '[an invention](https://bad.example/y)'", issue_type="hallucination",
        severity="critical", recommendation="replace it",
    )
    out = _audit([echoed], evidence=[_evidence("https://good.example/x")])

    by_claim = {i["claim"]: i["section_title"] for i in out["qa_issues"]}
    assert by_claim == {
        "Link '[an invention](https://bad.example/y)'": "Beta",   # echoed: filled in
        "Link '[stray](https://stray.example/a)'": None,          # injected: before the first H2
    }
    assert out["qa_verdict"] == "NEEDS_REVISION"  # the scanner's override is unchanged


def test_a_paraphrased_claim_is_revised_in_its_own_section_not_by_rewriting_the_article():
    """The end-to-end symptom, through the real QA node: the claim appears nowhere
    in the text, so only the section title can route it to the right section."""
    from Graph.agents import revision, utils

    qa = _audit(
        [QAIssue(claim="a paraphrase that appears nowhere in the text", section_title="Beta",
                 issue_type="fact_error", severity="critical", recommendation="fix it")],
        evidence=[_evidence("https://good.example/x"), _evidence("https://stray.example/a"),
                  _evidence("https://bad.example/y")],
    )

    prompts = []

    class _Reviser:
        def invoke(self, messages):
            prompts.append(messages[1].content)
            return SimpleNamespace(content="A rewritten section body. " * 10)

    with patch.object(utils, "llm_quality", _Reviser()):
        out = revision.revision_node({"final": ARTICLE, "qa_issues": qa["qa_issues"]})

    assert len(prompts) == 1 and "SECTION TITLE: Beta" in prompts[0]
    assert "FULL BLOG POST TO EDIT" not in prompts[0]
    assert "Alpha cites [a source](https://good.example/x) properly." in out["final"]  # untouched
    assert "A rewritten section body." in out["final"]


# ---------------------------------------------------------------------------
# manual QA loads the evidence
# ---------------------------------------------------------------------------


@pytest.fixture
def job_folder(tmp_path):
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "post.md").write_text(ARTICLE, encoding="utf-8")
    (tmp_path / "metadata").mkdir()
    (tmp_path / "metadata" / "metadata.json").write_text("{}", encoding="utf-8")
    (tmp_path / "research").mkdir()
    return tmp_path


def _context(job_folder, task_name):
    from api import manual_tasks

    job = {"topic": "T", "config": {}, "blog_folder": str(job_folder)}
    with patch.object(manual_tasks, "get_job_healed", return_value=job):
        return manual_tasks._load_context("job-1", task_name, pipeline_loader=lambda: None)


def test_manual_qa_gets_the_research_evidence_as_objects(job_folder):
    good = _evidence("https://good.example/x").model_dump()
    (job_folder / "research" / "evidence.json").write_text(
        json.dumps([good, {"not": "an evidence item"}]), encoding="utf-8"
    )

    evidence = _context(job_folder, "qa").state["evidence"]

    assert [e.url for e in evidence] == ["https://good.example/x"]  # the unreadable entry is skipped
    assert evidence[0].title == "T"  # attribute access, which the QA nodes rely on


def test_manual_qa_without_a_research_file_gets_no_evidence(job_folder):
    assert _context(job_folder, "qa").state["evidence"] == []


def test_other_manual_tasks_are_left_alone(job_folder):
    (job_folder / "research" / "evidence.json").write_text(
        json.dumps([_evidence("https://good.example/x").model_dump()]), encoding="utf-8"
    )
    assert "evidence" not in _context(job_folder, "campaign").state
