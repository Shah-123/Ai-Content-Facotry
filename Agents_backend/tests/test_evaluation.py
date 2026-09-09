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
