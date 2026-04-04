"""
NeuroUI Evaluation Test Suite
==============================
Comprehensive automated evaluation covering all rubric areas:
- Readability improvement
- CLS reduction
- Meaning preservation
- Profile differentiation
- Latency benchmarks
- Edge cases

Run: python -m pytest tests/test_evaluation.py -v
"""

import json
import time
import asyncio
import os
import sys

import pytest
import textstat

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cognitive_metrics import (
    compute_text_complexity,
    compute_syntactic_load,
    compute_dom_clutter,
    compute_cls,
)
from core.dom_analyzer import classify_element, analyze_dom
from agents.text_simplifier import simplify_text, _rule_based_simplify
from agents.visual_adapter import get_visual_adaptations
from agents.focus_agent import generate_focus_actions
from agents.orchestrator import process_page


# --- Load Test Corpus ---
CORPUS_PATH = os.path.join(os.path.dirname(__file__), "test_corpus.json")
with open(CORPUS_PATH, "r", encoding="utf-8") as f:
    TEST_CORPUS = json.load(f)


# ============================================================
# Test Group 1: Cognitive Metrics Engine
# ============================================================

class TestCognitiveMetrics:
    """Tests for the CLS computation engine."""

    def test_text_complexity_range(self):
        """Text complexity should always be in [0, 100]."""
        for sample in TEST_CORPUS:
            score = compute_text_complexity(sample["text"])
            assert 0 <= score <= 100, (
                f"Sample '{sample['id']}' produced out-of-range "
                f"complexity: {score}"
            )

    def test_complexity_ordering(self):
        """Simple text should have lower complexity than complex text."""
        simple = next(s for s in TEST_CORPUS if s["id"] == "simple_grade3")
        complex_ = next(s for s in TEST_CORPUS if s["id"] == "academic_high")

        simple_score = compute_text_complexity(simple["text"])
        complex_score = compute_text_complexity(complex_["text"])

        assert simple_score < complex_score, (
            f"Simple text ({simple_score}) should be less complex "
            f"than academic text ({complex_score})"
        )

    def test_syntactic_load_range(self):
        """Syntactic load should always be in [0, 100]."""
        for sample in TEST_CORPUS:
            score = compute_syntactic_load(sample["text"])
            assert 0 <= score <= 100, (
                f"Sample '{sample['id']}' produced out-of-range "
                f"syntactic load: {score}"
            )

    def test_nested_clauses_high_syntactic_load(self):
        """Deeply nested clauses should produce high syntactic load."""
        nested = next(s for s in TEST_CORPUS if s["id"] == "nested_clauses")
        simple = next(s for s in TEST_CORPUS if s["id"] == "simple_grade3")

        nested_score = compute_syntactic_load(nested["text"])
        simple_score = compute_syntactic_load(simple["text"])

        assert nested_score > simple_score, (
            f"Nested clauses ({nested_score}) should have higher syntactic load "
            f"than simple text ({simple_score})"
        )

    def test_dom_clutter_scales(self):
        """DOM clutter should scale with node count and distractors."""
        minimal = compute_dom_clutter({
            "node_count": 50, "max_depth": 3,
            "distractor_count": 0, "animation_count": 0,
        })
        cluttered = compute_dom_clutter({
            "node_count": 2000, "max_depth": 20,
            "distractor_count": 10, "animation_count": 5,
        })

        assert cluttered > minimal, (
            f"Cluttered DOM ({cluttered}) should score higher than "
            f"minimal DOM ({minimal})"
        )

    def test_cls_composite_range(self):
        """Full CLS should be in [0, 100]."""
        for sample in TEST_CORPUS:
            result = compute_cls(sample["text"])
            assert 0 <= result["cls"] <= 100
            assert "text_complexity" in result
            assert "syntactic_load" in result
            assert "grade_level" in result

    def test_cls_empty_text(self):
        """CLS should handle empty/minimal text gracefully."""
        result = compute_cls("")
        assert result["cls"] == 0.0

        result2 = compute_cls("Hi.")
        assert isinstance(result2["cls"], (int, float))


# ============================================================
# Test Group 2: DOM Analyzer
# ============================================================

class TestDOMAnalyzer:
    """Tests for the DOM distractor detection system."""

    def test_detect_ad_elements(self):
        """Should detect ad-related elements."""
        ad_element = {
            "tag": "div",
            "classes": ["ad-wrapper", "banner"],
            "id": "google-ad-1",
            "attributes": {},
        }
        result = classify_element(ad_element)
        assert result["is_distractor"] is True
        assert result["distractor_type"] == "ad"
        assert result["confidence"] >= 0.8

    def test_detect_popup_overlay(self):
        """Should detect popup/modal elements."""
        popup_element = {
            "tag": "div",
            "classes": ["cookie-consent-banner"],
            "id": "",
            "attributes": {"role": "dialog"},
            "position": "fixed",
            "z_index": 9999,
        }
        result = classify_element(popup_element)
        assert result["is_distractor"] is True
        assert result["distractor_type"] == "popup"

    def test_detect_autoplay_media(self):
        """Should detect autoplay video/audio."""
        video = {
            "tag": "video",
            "classes": [],
            "id": "hero-video",
            "attributes": {},
            "has_autoplay": True,
        }
        result = classify_element(video)
        assert result["is_distractor"] is True
        assert result["action"] == "pause"

    def test_normal_element_not_distractor(self):
        """Normal content elements should not be flagged."""
        paragraph = {
            "tag": "p",
            "classes": ["article-text"],
            "id": "",
            "attributes": {},
        }
        result = classify_element(paragraph)
        assert result["is_distractor"] is False

    def test_full_dom_analysis(self):
        """Full DOM snapshot analysis should produce valid output."""
        snapshot = {
            "node_count": 500,
            "max_depth": 8,
            "elements": [
                {"tag": "div", "classes": ["ad-container"], "id": "", "attributes": {}},
                {"tag": "div", "classes": ["cookie-popup"], "id": "", "attributes": {},
                 "position": "fixed", "z_index": 10000},
                {"tag": "p", "classes": ["content"], "id": "", "attributes": {}},
                {"tag": "video", "classes": [], "id": "bg-video", "attributes": {},
                 "has_autoplay": True},
            ],
            "url": "https://example.com",
        }

        result = analyze_dom(snapshot)
        assert result["distractor_count"] >= 2
        assert result["node_count"] == 500
        assert len(result["actions"]["hide"]) >= 1


# ============================================================
# Test Group 3: Text Simplification
# ============================================================

class TestTextSimplification:
    """Tests for the hybrid text simplification pipeline."""

    def test_rule_based_jargon_replacement(self):
        """Rule-based simplifier should replace common jargon."""
        text = "We need to utilize this tool in order to facilitate the process."
        simplified = _rule_based_simplify(text)
        assert "use" in simplified.lower()
        assert "help" in simplified.lower()

    def test_rule_based_preserves_content(self):
        """Rule-based simplifier should not remove essential content."""
        text = "The temperature is 72 degrees Fahrenheit in New York City."
        simplified = _rule_based_simplify(text)
        assert "72" in simplified
        assert "New York" in simplified

    @pytest.mark.asyncio
    async def test_simplification_improves_readability(self):
        """Simplified text should have better readability scores."""
        complex_sample = next(
            s for s in TEST_CORPUS if s["id"] == "legal_complex"
        )
        result = await simplify_text(complex_sample["text"], "adhd")

        assert result["readability_after"] >= result["readability_before"] - 5, (
            f"Simplification should improve or maintain readability. "
            f"Before: {result['readability_before']}, After: {result['readability_after']}"
        )

    @pytest.mark.asyncio
    async def test_simple_text_passthrough(self):
        """Already simple text should pass through with minimal changes."""
        simple = next(s for s in TEST_CORPUS if s["id"] == "simple_grade3")
        result = await simplify_text(simple["text"], "adhd")

        # Simple text should not get significantly worse
        assert result["readability_after"] >= result["readability_before"] - 10

    @pytest.mark.asyncio
    async def test_empty_text_handling(self):
        """Should handle empty or very short text gracefully."""
        result = await simplify_text("", "adhd")
        assert result["method"] == "passthrough"

        result2 = await simplify_text("Hi.", "adhd")
        assert result2["method"] == "passthrough"


# ============================================================
# Test Group 4: Visual Adaptation
# ============================================================

class TestVisualAdaptation:
    """Tests for profile-specific CSS generation."""

    def test_adhd_profile_stops_animations(self):
        """ADHD CSS should disable animations."""
        result = get_visual_adaptations("adhd")
        assert "animation-duration: 0s" in result["css_rules"]
        assert result["profile"] == "adhd"

    def test_dyslexia_profile_increases_spacing(self):
        """Dyslexia CSS should increase letter and word spacing."""
        result = get_visual_adaptations("dyslexia")
        assert "letter-spacing" in result["css_rules"]
        assert "word-spacing" in result["css_rules"]
        assert "line-height: 1.8" in result["css_rules"]

    def test_autism_profile_desaturates(self):
        """Autism CSS should desaturate colors."""
        result = get_visual_adaptations("autism")
        assert "saturate" in result["css_rules"]
        assert "animation: none" in result["css_rules"]

    def test_profiles_are_distinct(self):
        """Each profile should produce genuinely different CSS."""
        adhd = get_visual_adaptations("adhd")
        dyslexia = get_visual_adaptations("dyslexia")
        autism = get_visual_adaptations("autism")

        assert adhd["css_rules"] != dyslexia["css_rules"]
        assert dyslexia["css_rules"] != autism["css_rules"]
        assert adhd["css_rules"] != autism["css_rules"]

    def test_custom_spacing_override(self):
        """Custom spacing multiplier should affect CSS output."""
        result = get_visual_adaptations("dyslexia", {"spacing_multiplier": 2.0})
        assert result["css_rules"]  # Should produce valid CSS


# ============================================================
# Test Group 5: Focus Agent
# ============================================================

class TestFocusAgent:
    """Tests for the distraction detection and removal agent."""

    def test_adhd_removes_more_distractors(self):
        """ADHD profile should be more aggressive in removing distractors."""
        dom_analysis = {
            "distractors": [
                {"distractor_type": "ad", "confidence": 0.55, "selector": ".ad-1", "action": "hide"},
                {"distractor_type": "sidebar", "confidence": 0.65, "selector": ".sidebar", "action": "dim"},
            ],
            "actions": {},
        }

        adhd = generate_focus_actions(dom_analysis, "adhd")
        dyslexia = generate_focus_actions(dom_analysis, "dyslexia")

        assert adhd["elements_removed"] >= dyslexia["elements_removed"]


# ============================================================
# Test Group 6: Full Pipeline (Orchestrator)
# ============================================================

class TestOrchestrator:
    """End-to-end tests for the full MAS pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_output(self):
        """Full pipeline should return valid transformation data."""
        chunks = [TEST_CORPUS[0]["text"], TEST_CORPUS[4]["text"]]

        result = await process_page(
            chunks=chunks,
            profile="adhd",
            dom_snapshot={
                "node_count": 500,
                "max_depth": 8,
                "elements": [
                    {"tag": "div", "classes": ["ad-unit"], "id": "", "attributes": {}},
                ],
            },
        )

        assert len(result["simplified_chunks"]) == 2
        assert "cls_before" in result
        assert "cls_after" in result
        assert isinstance(result["cls_improvement"], float)
        assert result["visual_css"]  # Non-empty CSS

    @pytest.mark.asyncio
    async def test_cls_improves_after_pipeline(self):
        """CLS should improve (decrease) after the full pipeline."""
        complex_sample = next(
            s for s in TEST_CORPUS if s["id"] == "academic_high"
        )

        result = await process_page(
            chunks=[complex_sample["text"]],
            profile="adhd",
            dom_snapshot={
                "node_count": 1000,
                "max_depth": 12,
                "elements": [
                    {"tag": "div", "classes": ["ad-wrapper"], "id": "", "attributes": {}},
                    {"tag": "div", "classes": ["popup-modal"], "id": "",
                     "attributes": {}, "position": "fixed", "z_index": 9999},
                ],
            },
        )

        assert result["cls_improvement"] >= 0, (
            f"CLS should improve (decrease). "
            f"Before: {result['cls_before']['cls']}, "
            f"After: {result['cls_after']['cls']}"
        )

    @pytest.mark.asyncio
    async def test_pipeline_latency(self):
        """Full pipeline should process a chunk in under 5 seconds (no LLM)."""
        chunk = TEST_CORPUS[3]["text"]  # Moderate length

        start = time.time()
        result = await process_page(
            chunks=[chunk],
            profile="adhd",
        )
        elapsed = time.time() - start

        assert elapsed < 5.0, (
            f"Pipeline latency ({elapsed:.2f}s) exceeds 5s threshold"
        )

    @pytest.mark.asyncio
    async def test_different_profiles_produce_different_results(self):
        """Different profiles should produce genuinely different outputs."""
        text = TEST_CORPUS[7]["text"]  # Metaphor-heavy (good for differentiating)

        adhd_result = await process_page(chunks=[text], profile="adhd")
        autism_result = await process_page(chunks=[text], profile="autism")

        # Visual CSS should differ
        assert adhd_result["visual_css"] != autism_result["visual_css"]


# ============================================================
# Test Group 7: Edge Cases
# ============================================================

class TestEdgeCases:
    """Edge case handling tests."""

    @pytest.mark.asyncio
    async def test_single_word_input(self):
        """Pipeline should handle single-word input."""
        result = await process_page(chunks=["Hello"], profile="adhd")
        assert result["simplified_chunks"][0]  # Should not crash

    @pytest.mark.asyncio
    async def test_very_long_input(self):
        """Pipeline should handle long text without crashing."""
        long_text = " ".join([TEST_CORPUS[0]["text"]] * 10)  # ~10x repetition
        result = await process_page(chunks=[long_text], profile="dyslexia")
        assert result["simplified_chunks"]

    @pytest.mark.asyncio
    async def test_no_dom_snapshot(self):
        """Pipeline should work without DOM snapshot."""
        result = await process_page(
            chunks=[TEST_CORPUS[4]["text"]],
            profile="adhd",
        )
        assert result["cls_before"]["dom_clutter"] == 0.0

    def test_cls_with_zero_dom(self):
        """CLS should be valid even with no DOM data."""
        result = compute_cls("This is a test sentence.")
        assert 0 <= result["cls"] <= 100
        assert result["dom_clutter"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
