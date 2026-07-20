"""
Tests for Graph/agents/utils.py — shared utility helpers.
"""
import pytest
from Graph.agents.utils import _safe_slug


class TestSafeSlug:
    """Tests for _safe_slug()."""

    def test_basic_conversion(self):
        assert _safe_slug("Hello World") == "hello_world"

    def test_strips_special_characters(self):
        assert _safe_slug("AI & Healthcare: The Future!") == "ai_healthcare_the_future"

    def test_handles_multiple_spaces(self):
        slug = _safe_slug("too   many    spaces")
        assert "  " not in slug  # no double underscores from collapsed spaces
        assert slug == "too_many_spaces"

    def test_returns_fallback_for_empty_string(self):
        assert _safe_slug("") == "blog"

    def test_returns_fallback_for_only_special_chars(self):
        assert _safe_slug("!@#$%^&*()") == "blog"

    def test_preserves_hyphens_and_underscores(self):
        slug = _safe_slug("my-topic_name")
        assert "my-topic_name" == slug
