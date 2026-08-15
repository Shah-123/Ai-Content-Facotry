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
