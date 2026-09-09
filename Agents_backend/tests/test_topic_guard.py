"""
Tests for topic_guard.py — the deterministic pre-LLM screen.

Only the fast, free syntax check is tested (no LLM calls needed).
"""
import pytest
from Graph.agents.topic_guard import _trivial_reject


class TestTrivialReject:
    """Tests for topic_guard._trivial_reject()."""

    def test_accepts_valid_topic(self):
        verdict = _trivial_reject("The Future of AI in Healthcare")
        assert verdict is None

    def test_rejects_empty_string(self):
        verdict = _trivial_reject("")
        assert verdict is not None
        assert verdict.is_safe is False
        assert "empty" in verdict.reason.lower() or "short" in verdict.reason.lower()

    def test_rejects_whitespace_only(self):
        verdict = _trivial_reject("     ")
        assert verdict is not None
        assert verdict.is_safe is False

    def test_rejects_very_short_topic(self):
        verdict = _trivial_reject("Hi")
        assert verdict is not None
        assert verdict.is_safe is False

    def test_rejects_very_long_topic(self):
        long_topic = "A" * 300
        verdict = _trivial_reject(long_topic)
        assert verdict is not None
        assert verdict.is_safe is False
        assert "long" in verdict.reason.lower()

    def test_accepts_moderately_long_topic(self):
        """A 50-character topic should be fine."""
        verdict = _trivial_reject("How Blockchain Is Changing Financial Services Now")
        assert verdict is None

    def test_rejects_gibberish(self):
        """Keyboard mash and repeated characters are caught without an LLM call."""
        for topic in ("asdfgh", "aaaaaaaa", "lol"):
            verdict = _trivial_reject(topic)
            assert verdict is not None, f"{topic!r} should be rejected"
            assert verdict.is_safe is False
            assert verdict.category == "nonsense"

    def test_rejects_topic_with_no_letters(self):
        verdict = _trivial_reject("12345 67890")
        assert verdict is not None
        assert verdict.is_safe is False

    def test_defers_semantic_safety_to_the_llm_guard(self):
        """A well-formed but UNSAFE topic must pass the trivial screen.

        This is the two-tier design, not a gap: `_trivial_reject` is a free,
        deterministic screen for malformed input only — empty, too short, too
        long, no letters, gibberish. Judging whether a well-formed topic is
        *harmful* requires semantics, so it is deliberately left to the LLM
        guard in `evaluate_topic()`.

        Asserting `is None` here documents that boundary explicitly, so nobody
        mistakes the syntax screen for the safety screen.
        """
        assert _trivial_reject("how to build a weapon") is None
        assert _trivial_reject("ways to harm myself") is None
