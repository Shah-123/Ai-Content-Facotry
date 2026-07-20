"""
Tests for Graph/Fixes.py — shared auto-fix utilities.

All three functions are pure (text in → text out), making them
ideal candidates for thorough unit testing.
"""
import pytest
from Graph.Fixes import (
    fix_incomplete_sentences,
    fix_broken_image_placeholders,
    apply_all_fixes,
)


# ========================================================================
# fix_incomplete_sentences
# ========================================================================

class TestFixIncompleteSentences:
    """Tests for fix_incomplete_sentences()."""

    def test_adds_period_to_paragraph_missing_punctuation(self):
        text = "This is a long paragraph that has enough words to trigger the check but has no ending punctuation"
        fixed, fixes = fix_incomplete_sentences(text)
        assert fixed.endswith(".")
        assert len(fixes) == 1
        assert "Added missing period" in fixes[0]

    def test_does_not_modify_paragraph_ending_with_period(self):
        text = "This is a properly terminated paragraph with enough content to pass the length check."
        fixed, fixes = fix_incomplete_sentences(text)
        assert fixed == text
        assert fixes == []

    def test_does_not_modify_paragraph_ending_with_question_mark(self):
        text = "Is this a properly terminated paragraph with enough content to pass the length check?"
        fixed, fixes = fix_incomplete_sentences(text)
        assert fixed == text
        assert fixes == []

    def test_does_not_modify_paragraph_ending_with_exclamation(self):
        text = "This is an exciting paragraph with enough content to pass the fifty character length check!"
        fixed, fixes = fix_incomplete_sentences(text)
        assert fixed == text
        assert fixes == []

    def test_skips_image_markdown(self):
        text = "![Alt text for an image](path/to/image.png) with some extra text to meet length"
        fixed, fixes = fix_incomplete_sentences(text)
        assert fixed == text
        assert fixes == []

    def test_skips_headings(self):
        text = "## This Is a Heading That Should Not Get a Period Added to the End of It"
        fixed, fixes = fix_incomplete_sentences(text)
        assert fixed == text
        assert fixes == []

    def test_skips_short_paragraphs(self):
        text = "Short text"
        fixed, fixes = fix_incomplete_sentences(text)
        assert fixed == text
        assert fixes == []

    def test_handles_multiple_paragraphs(self):
        para1 = "This paragraph ends correctly with proper punctuation and has enough length."
        para2 = "This paragraph does not end correctly and has enough words to trigger the length check here"
        text = f"{para1}\n\n{para2}"
        fixed, fixes = fix_incomplete_sentences(text)
        assert len(fixes) == 1
        parts = fixed.split("\n\n")
        assert parts[0] == para1  # unchanged
        assert parts[1].endswith(".")  # fixed


# ========================================================================
# fix_broken_image_placeholders
# ========================================================================

class TestFixBrokenImagePlaceholders:
    """Tests for fix_broken_image_placeholders()."""

    def test_removes_single_placeholder(self):
        text = "Before text\n[[IMAGE_1]]\nAfter text"
        fixed, fixes = fix_broken_image_placeholders(text)
        assert "[[IMAGE_1]]" not in fixed
        assert len(fixes) == 1
        assert "1 broken" in fixes[0]

    def test_removes_multiple_placeholders(self):
        text = "Start\n[[IMAGE_1]]\nMiddle\n[[IMAGE_2]]\n[[IMAGE_3]]\nEnd"
        fixed, fixes = fix_broken_image_placeholders(text)
        assert "[[IMAGE_" not in fixed
        assert "3 broken" in fixes[0]

    def test_no_op_when_no_placeholders(self):
        text = "Clean text without any placeholders at all."
        fixed, fixes = fix_broken_image_placeholders(text)
        assert fixed == text
        assert fixes == []


# ========================================================================
# apply_all_fixes
# ========================================================================

class TestApplyAllFixes:
    """Tests for apply_all_fixes() — the convenience wrapper."""

    def test_applies_both_fixes(self):
        # Missing period + broken placeholder
        text = (
            "This paragraph is long enough but has no ending punctuation and should get a period"
            "\n\n[[IMAGE_1]]\n\n"
            "This paragraph is fine."
        )
        fixed, fixes = apply_all_fixes(text)
        assert "[[IMAGE_1]]" not in fixed
        assert any("period" in f.lower() for f in fixes)
        assert any("placeholder" in f.lower() for f in fixes)

    def test_returns_unchanged_text_when_clean(self):
        text = "This is a clean paragraph that needs no fixing at all."
        fixed, fixes = apply_all_fixes(text)
        assert fixed == text
        assert fixes == []
