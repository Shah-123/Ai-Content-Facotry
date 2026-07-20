"""
Tests for topic_guard.py — _trivial_reject.

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
