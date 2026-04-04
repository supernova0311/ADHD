"""
Cognitive Metrics Engine
========================
Implements the Cognitive Load Score (CLS) — a novel composite metric
that quantifies how cognitively demanding web content is for neurodivergent users.

CLS = W1 × TextComplexity + W2 × SyntacticLoad + W3 × DOMClutter

Research basis:
- TextComplexity: Flesch (1948), validated across millions of texts
- SyntacticLoad: Gibson (2000) Dependency Locality Theory — processing cost
  scales with distance between dependent words
- DOMClutter: Web visual complexity research (Harper et al., 2009)
"""

import re
import textstat
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to load spaCy (optional — graceful fallback if not installed)
nlp = None
try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
        logger.info("spaCy model loaded successfully.")
    except OSError:
        logger.warning(
            "spaCy model 'en_core_web_sm' not found. "
            "Run: python -m spacy download en_core_web_sm"
        )
except ImportError:
    logger.warning(
        "spaCy not installed. Using heuristic syntactic load estimation. "
        "Install with: pip install spacy"
    )

# --- CLS Weights ---
W_TEXT_COMPLEXITY = 0.40
W_SYNTACTIC_LOAD = 0.30
W_DOM_CLUTTER = 0.30


def compute_text_complexity(text: str) -> float:
    """
    Compute text complexity from an ensemble of readability metrics.
    Returns a value in [0, 100] where higher = more complex.

    Uses Flesch Reading Ease (inverted) as primary, with Coleman-Liau
    and SMOG as cross-validation.
    """
    if not text or len(text.strip()) < 10:
        return 0.0

    try:
        # Primary metric: Flesch Reading Ease (0-100, higher = easier)
        fre = textstat.flesch_reading_ease(text)
        # Invert: higher complexity = higher score
        fre_complexity = max(0, min(100, 100 - fre))

        # Secondary metrics for ensemble robustness
        fk_grade = textstat.flesch_kincaid_grade(text)
        # Normalize grade (0-16) to 0-100 scale
        fk_normalized = max(0, min(100, (fk_grade / 16.0) * 100))

        coleman = textstat.coleman_liau_index(text)
        coleman_normalized = max(0, min(100, (coleman / 16.0) * 100))

        # Ensemble: weighted average (Flesch primary, others secondary)
        complexity = (
            0.50 * fre_complexity
            + 0.25 * fk_normalized
            + 0.25 * coleman_normalized
        )

        return round(max(0, min(100, complexity)), 2)

    except Exception as e:
        logger.error(f"Error computing text complexity: {e}")
        return 50.0  # Default to moderate complexity on error


def compute_syntactic_load(text: str) -> float:
    """
    Compute syntactic load using mean dependency distance (MDD).

    Based on Gibson's Dependency Locality Theory (2000):
    Processing difficulty scales with the linear distance between
    a word and its syntactic head in a dependency parse.

    Falls back to a heuristic estimator when spaCy is not available.
    Returns a value in [0, 100] where higher = more syntactically complex.
    """
    if not text or len(text.strip()) < 10:
        return 0.0

    # Use spaCy if available
    if nlp is not None:
        try:
            doc = nlp(text)

            total_distance = 0
            token_count = 0

            for token in doc:
                if token.dep_ != "ROOT" and not token.is_punct and not token.is_space:
                    # Dependency distance = absolute difference in token positions
                    distance = abs(token.i - token.head.i)
                    total_distance += distance
                    token_count += 1

            if token_count == 0:
                return 0.0

            # Mean Dependency Distance
            mdd = total_distance / token_count

            # Normalize MDD to [0, 100]
            # Research shows MDD typically ranges from 1.5 (simple) to 6+ (complex)
            # We map: MDD=1 → 0, MDD=6 → 100
            normalized = max(0, min(100, ((mdd - 1.0) / 5.0) * 100))

            return round(normalized, 2)

        except Exception as e:
            logger.error(f"Error computing syntactic load with spaCy: {e}")

    # Heuristic fallback: estimate syntactic complexity from surface features
    # These correlate with dependency distance in linguistic research
    return _heuristic_syntactic_load(text)


def _heuristic_syntactic_load(text: str) -> float:
    """
    Estimate syntactic load without a parser.
    Uses surface-level features that correlate with dependency distance:
    - Mean sentence length (longer sentences = higher MDD)
    - Comma density (more clauses = more embedded structures)
    - Subordinating conjunction count (relative clauses, embedded clauses)
    """
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 3]

    if not sentences:
        return 0.0

    words = text.split()
    word_count = len(words)

    # Mean sentence length in words
    mean_sent_len = word_count / max(len(sentences), 1)
    # Normalize: 10 words = simple (0), 40+ words = complex (100)
    sent_len_score = max(0, min(100, ((mean_sent_len - 10) / 30) * 100))

    # Comma density — proxy for clausal embedding
    comma_count = text.count(',')
    comma_density = comma_count / max(word_count, 1) * 100
    # Normalize: 0 commas/100 words = 0, 8+ commas/100 words = 100
    comma_score = max(0, min(100, (comma_density / 8) * 100))

    # Subordinating conjunction count — proxy for dependent clauses
    subordinators = re.findall(
        r'\b(which|that|who|whom|whose|where|when|while|although|because|'
        r'since|unless|whereas|whereby|if|though|after|before|until)\b',
        text, re.IGNORECASE
    )
    sub_density = len(subordinators) / max(len(sentences), 1)
    # Normalize: 0 per sentence = 0, 3+ per sentence = 100
    sub_score = max(0, min(100, (sub_density / 3) * 100))

    # Weighted combination
    score = 0.45 * sent_len_score + 0.30 * comma_score + 0.25 * sub_score

    return round(max(0, min(100, score)), 2)


def compute_dom_clutter(dom_metadata: dict) -> float:
    """
    Compute DOM clutter score from structural page metadata.

    Factors:
    - Total DOM node count (>1500 is flagged by Google Lighthouse)
    - Maximum nesting depth
    - Number of detected distractor elements (ads, popups, modals, etc.)

    Returns a value in [0, 100] where higher = more cluttered.
    """
    node_count = dom_metadata.get("node_count", 0)
    max_depth = dom_metadata.get("max_depth", 0)
    distractor_count = dom_metadata.get("distractor_count", 0)
    animation_count = dom_metadata.get("animation_count", 0)

    # Weighted components
    # Node count: 1500 nodes → 100 clutter
    node_score = min(100, (node_count / 1500) * 100)

    # Depth: 15 levels → 100 clutter
    depth_score = min(100, (max_depth / 15) * 100)

    # Distractors: each one add significant clutter
    distractor_score = min(100, distractor_count * 12)

    # Animations: each adds visual noise
    animation_score = min(100, animation_count * 15)

    clutter = (
        0.30 * node_score
        + 0.20 * depth_score
        + 0.35 * distractor_score
        + 0.15 * animation_score
    )

    return round(max(0, min(100, clutter)), 2)


def compute_cls(
    text: str,
    dom_metadata: Optional[dict] = None
) -> dict:
    """
    Compute the full Cognitive Load Score.

    Returns a detailed breakdown:
    {
        "cls": float,              # Composite score [0, 100]
        "text_complexity": float,  # Text readability component
        "syntactic_load": float,   # Syntactic difficulty component
        "dom_clutter": float,      # Visual clutter component
        "grade_level": str,        # Human-readable grade level
        "reading_ease": float,     # Raw Flesch Reading Ease
    }
    """
    text_complexity = compute_text_complexity(text)
    syntactic_load = compute_syntactic_load(text)

    if dom_metadata is None:
        dom_metadata = {"node_count": 0, "max_depth": 0, "distractor_count": 0}

    dom_clutter = compute_dom_clutter(dom_metadata)

    cls = (
        W_TEXT_COMPLEXITY * text_complexity
        + W_SYNTACTIC_LOAD * syntactic_load
        + W_DOM_CLUTTER * dom_clutter
    )

    # Get human-readable grade level
    try:
        grade_level = textstat.text_standard(text, float_output=False)
        reading_ease = textstat.flesch_reading_ease(text)
    except Exception:
        grade_level = "N/A"
        reading_ease = 0.0

    return {
        "cls": round(max(0, min(100, cls)), 2),
        "text_complexity": text_complexity,
        "syntactic_load": syntactic_load,
        "dom_clutter": dom_clutter,
        "grade_level": grade_level,
        "reading_ease": round(reading_ease, 2),
    }
