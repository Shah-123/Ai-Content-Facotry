"""Check the G-Eval overall score is a correct weighted average (computed in code)."""
from Graph.agents.evaluation import (
    CriteriaEvaluation,
    GEvalScorecard,
    GEVAL_WEIGHTS,
    weighted_overall,
)


def _card(coh, rel, acc, tone):
    ev = lambda s: CriteriaEvaluation(score=s, reasoning="x")
    return GEvalScorecard(
        coherence=ev(coh), relevance=ev(rel), accuracy=ev(acc), tone_alignment=ev(tone)
    )


def test_weights_sum_to_one():
    assert round(sum(GEVAL_WEIGHTS.values()), 6) == 1.0


def test_all_fives_is_five():
    assert weighted_overall(_card(5, 5, 5, 5)) == 5.0


def test_weighting_is_not_a_flat_mean():
    # coherence(0.3) + accuracy(0.3) high, relevance(0.2) + tone(0.2) low
    # weighted = 0.3*5 + 0.2*1 + 0.3*5 + 0.2*1 = 3.4, flat mean would be 3.0
    assert weighted_overall(_card(5, 1, 5, 1)) == 3.4


# ---------------------------------------------------------------------------
# Judge independence — guards the confound that invalidated the experiment
# ---------------------------------------------------------------------------


class TestJudgeIsConfiguredIndependently:
    """The evaluation judge must be repointable WITHOUT moving anything else.

    `llm_quality` drives the QA auditor, the revision agent, the podcast
    scripter and the get_llm() fallback. When the G-Eval judge also read that
    client, repointing LLM_QUALITY_MODEL to obtain an independent judge silently
    swapped the QA auditor and reviser too — so a change in scores could not be
    attributed to the judge. LLM_JUDGE_MODEL exists to break that coupling.
    """

    def test_judge_client_exists_and_is_separate_from_llm_quality(self):
        from Graph.agents import utils

        assert hasattr(utils, "llm_judge"), "llm_judge client is missing"
        assert utils.llm_judge is not utils.llm_quality, (
            "the judge must be its own client, otherwise repointing it also "
            "moves the QA auditor and the revision agent"
        )

    def test_judge_defaults_to_the_quality_model(self):
        """Unset LLM_JUDGE_MODEL must change nothing — this is opt-in."""
        from Graph.agents import utils

        assert utils._JUDGE_MODEL == utils._QUALITY_MODEL

    def test_judge_requests_deterministic_sampling(self):
        """temperature=0 where the model honours it, None where it does not.

        Reasoning-family models accept only their default temperature and
        langchain-openai drops the argument silently, so `None` here is the
        expected reading on gpt-5-mini rather than a misconfiguration. Any
        OTHER value would mean a grader was left sampling randomly.
        """
        from Graph.agents import utils

        assert utils.llm_judge.temperature in (0, 0.0, None), (
            f"judge temperature is {utils.llm_judge.temperature!r}; a grader "
            f"must not sample randomly"
        )

    def test_evaluation_node_uses_the_judge_client_not_llm_quality(self):
        """Source-level guard: importing llm_quality here reintroduces the confound."""
        import inspect
        from Graph.agents import evaluation

        src = inspect.getsource(evaluation)
        assert "llm_judge.with_structured_output" in src, (
            "the G-Eval judge must be built from llm_judge"
        )
        # Check for USE, not mere mention: the explanatory comment in
        # evaluation.py legitimately names llm_quality.
        code = "\n".join(
            line for line in src.splitlines() if not line.lstrip().startswith("#")
        )
        assert "llm_quality" not in code, (
            "evaluation.py must not call llm_quality - that is the coupling "
            "LLM_JUDGE_MODEL was introduced to remove"
        )

    def test_geval_scores_record_the_judge_model(self):
        """Every reported score must be attributable to the model that produced it."""
        import inspect
        from Graph.agents import evaluation

        src = inspect.getsource(evaluation)
        assert 'scores_dict["judge_model"]' in src
        assert 'results["judge_model"]' in src

    def test_deepeval_metrics_pin_their_model(self):
        """Unpinned GEval falls back to deepeval's own default, which is undocumented."""
        import inspect
        from Graph.agents import evaluation

        src = inspect.getsource(evaluation.deepeval_evaluation_node)
        assert src.count("model=_JUDGE_MODEL") == 4, (
            "all four deepeval rubrics must pin the judge model"
        )


class TestTemperatureIsInertOnReasoningModels:
    """Documents that temperature arguments do nothing on the default model.

    Reasoning-family models (the gpt-5 line) accept only their default sampling
    temperature. langchain-openai drops the parameter silently rather than
    raising, so every `temperature=` in this codebase is a no-op while
    gpt-5-mini is selected — including `llm_planner`'s 0.7, which exists to
    diversify outlines, and the worker's 0.3.

    This is captured as a test so nobody spends an afternoon tuning a number
    that cannot take effect, and so the day the default model changes to one
    that DOES honour temperature, that becomes a visible event.
    """

    def test_reasoning_model_discards_temperature(self):
        from langchain_openai import ChatOpenAI

        assert ChatOpenAI(model="gpt-5-mini", temperature=0.7).temperature is None

    def test_non_reasoning_model_honours_temperature(self):
        """The same argument works on gpt-4o-mini — the code is not wrong, just conditional."""
        from langchain_openai import ChatOpenAI

        assert ChatOpenAI(model="gpt-4o-mini", temperature=0.7).temperature == 0.7

    def test_planner_temperature_is_currently_inert(self):
        """`llm_planner` requests 0.7 for outline variety; on gpt-5-mini it is ignored."""
        from Graph.agents import utils

        if utils._QUALITY_MODEL.startswith(("gpt-5", "o1", "o3", "o4")):
            assert utils.llm_planner.temperature is None, (
                "expected the reasoning model to discard temperature"
            )
        else:
            assert utils.llm_planner.temperature == 0.7


class TestTruncationIsReported:
    """Evaluators cap their input; they must not do so silently.

    A 39,025-character article was audited on 77% of its text and graded by
    G-Eval on 64% of it, with nothing in the logs, the report or the scores to
    say so. A score over two thirds of an article is a different measurement
    from one over all of it, and a reader of the results had no way to tell
    which they were looking at.
    """

    def test_short_text_is_untouched_and_reports_full_coverage(self):
        from Graph.agents.utils import truncate_for_eval

        text = "a" * 100
        out, info = truncate_for_eval(text, 25_000, "test")
        assert out == text
        assert info["truncated"] is False
        assert info["coverage"] == 1.0
        assert info["chars_evaluated"] == info["chars_total"] == 100

    def test_long_text_is_clipped_and_flagged(self):
        from Graph.agents.utils import truncate_for_eval

        out, info = truncate_for_eval("a" * 39_025, 25_000, "test")
        assert len(out) == 25_000
        assert info["truncated"] is True
        assert info["chars_total"] == 39_025
        assert info["coverage"] == 0.6406  # the real open_book_current figure

    def test_empty_text_does_not_divide_by_zero(self):
        from Graph.agents.utils import truncate_for_eval

        out, info = truncate_for_eval("", 25_000, "test")
        assert out == ""
        assert info["coverage"] == 1.0
        assert info["truncated"] is False

    def test_truncation_is_logged_as_a_warning(self, caplog):
        import logging
        from Graph.agents.utils import truncate_for_eval

        with caplog.at_level(logging.WARNING, logger="blog_pipeline"):
            truncate_for_eval("a" * 40_000, 25_000, "G-Eval")
        assert any("truncated" in r.message.lower() for r in caplog.records)

    def test_qa_coverage_is_declared_in_state(self):
        """Undeclared keys are dropped silently — the generate_qa trap."""
        from Graph.state import State

        assert "qa_coverage" in State.__annotations__

    def test_both_judges_record_coverage_with_their_scores(self):
        import inspect
        from Graph.agents import evaluation

        src = inspect.getsource(evaluation)
        assert 'scores_dict["coverage"] = coverage' in src
        assert 'results["coverage"] = coverage' in src

    def test_no_evaluator_slices_the_article_inline(self):
        """A bare [:25000] bypasses the reporting helper."""
        import inspect
        import re
        from Graph.agents import evaluation, quality_control

        for module in (evaluation, quality_control):
            code = "\n".join(
                l for l in inspect.getsource(module).splitlines()
                if not l.lstrip().startswith("#")
            )
            bad = re.findall(r"blog_content\[:\d+\]|final_text\[:_?[A-Z_]*\d*\]", code)
            assert not bad, f"{module.__name__} truncates inline: {bad}"
