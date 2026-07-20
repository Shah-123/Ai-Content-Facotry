"""
Tests for Graph/keyword_optimizer.py — SEO keyword analysis helpers.

Both analyze_keyword_density() and generate_optimization_suggestions()
are pure functions with no external dependencies.
"""
import pytest
from Graph.keyword_optimizer import (
    analyze_keyword_density,
    generate_optimization_suggestions,
)


# ========================================================================
# analyze_keyword_density
# ========================================================================

class TestAnalyzeKeywordDensity:
    """Tests for analyze_keyword_density()."""

    SAMPLE_BLOG = (
        "## AI in Healthcare: A Modern Overview\n\n"
        "Artificial intelligence is transforming healthcare delivery across the world. "
        "AI in healthcare enables faster diagnoses, better patient outcomes, and cost savings. "
        "Machine learning models are being deployed in radiology, pathology, and genomics. "
        "AI in healthcare is also reshaping drug discovery pipelines.\n\n"
        "## The Future of Medical Automation\n\n"
        "Medical automation powered by AI will continue to grow. "
        "Hospitals are investing in robotic surgery and predictive analytics. "
        "The integration of AI in healthcare systems is accelerating globally."
    )

    def test_correct_count(self):
        result = analyze_keyword_density(self.SAMPLE_BLOG, ["AI in healthcare"])
        # "AI in healthcare" appears multiple times
        assert result["AI in healthcare"]["count"] >= 3

    def test_density_is_percentage(self):
        result = analyze_keyword_density(self.SAMPLE_BLOG, ["AI in healthcare"])
        density = result["AI in healthcare"]["density"]
        assert 0 <= density <= 100

    def test_status_low_for_rare_keyword(self):
        # A keyword that appears 0 times → low
        result = analyze_keyword_density(self.SAMPLE_BLOG, ["blockchain"])
        assert result["blockchain"]["status"] == "low"
        assert result["blockchain"]["count"] == 0

    def test_in_title_detection(self):
        result = analyze_keyword_density(self.SAMPLE_BLOG, ["AI in Healthcare"])
        # Present in the first 200 chars (the H2 heading)
        assert result["AI in Healthcare"]["in_title"] is True

    def test_in_first_paragraph_detection(self):
        result = analyze_keyword_density(self.SAMPLE_BLOG, ["Artificial intelligence"])
        assert result["Artificial intelligence"]["in_first_paragraph"] is True

    def test_in_headings_detection(self):
        result = analyze_keyword_density(self.SAMPLE_BLOG, ["Medical Automation"])
        assert result["Medical Automation"]["in_headings"] is True

    def test_not_in_headings(self):
        result = analyze_keyword_density(self.SAMPLE_BLOG, ["drug discovery"])
        assert result["drug discovery"]["in_headings"] is False

    def test_case_insensitive(self):
        result = analyze_keyword_density(self.SAMPLE_BLOG, ["ai in healthcare"])
        assert result["ai in healthcare"]["count"] >= 3

    def test_empty_text(self):
        result = analyze_keyword_density("", ["keyword"])
        assert result["keyword"]["count"] == 0
        assert result["keyword"]["density"] == 0
        assert result["keyword"]["status"] == "low"

    def test_multiple_keywords(self):
        result = analyze_keyword_density(self.SAMPLE_BLOG, ["AI", "machine learning"])
        assert "AI" in result
        assert "machine learning" in result


# ========================================================================
# generate_optimization_suggestions
# ========================================================================

class TestGenerateOptimizationSuggestions:
    """Tests for generate_optimization_suggestions()."""

    def test_generates_suggestion_for_low_density(self):
        analysis = {
            "AI": {"count": 1, "density": 0.1, "status": "low",
                   "in_title": True, "in_first_paragraph": True, "in_headings": True}
        }
        suggestions = generate_optimization_suggestions(analysis)
        assert any("appears only 1 times" in s for s in suggestions)

    def test_generates_suggestion_for_high_density(self):
        analysis = {
            "AI": {"count": 50, "density": 5.0, "status": "high",
                   "in_title": True, "in_first_paragraph": True, "in_headings": True}
        }
        suggestions = generate_optimization_suggestions(analysis)
        assert any("keyword stuffing" in s for s in suggestions)

    def test_generates_suggestion_for_missing_title(self):
        analysis = {
            "AI": {"count": 5, "density": 1.5, "status": "optimal",
                   "in_title": False, "in_first_paragraph": True, "in_headings": True}
        }
        suggestions = generate_optimization_suggestions(analysis)
        assert any("missing from the title" in s for s in suggestions)

    def test_generates_suggestion_for_missing_headings(self):
        analysis = {
            "AI": {"count": 5, "density": 1.5, "status": "optimal",
                   "in_title": True, "in_first_paragraph": True, "in_headings": False}
        }
        suggestions = generate_optimization_suggestions(analysis)
        assert any("not used in any headings" in s for s in suggestions)

    def test_no_suggestions_for_optimal_keyword(self):
        analysis = {
            "AI": {"count": 5, "density": 1.5, "status": "optimal",
                   "in_title": True, "in_first_paragraph": True, "in_headings": True}
        }
        suggestions = generate_optimization_suggestions(analysis)
        assert suggestions == []
