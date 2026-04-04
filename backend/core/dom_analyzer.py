"""
DOM Analyzer
=============
Parses DOM metadata sent from the browser extension's content script
and classifies structural elements to compute the DOMClutter component
of the Cognitive Load Score.

Detects distractor elements via heuristic pattern matching on
class names, IDs, tag types, and ARIA attributes.
"""

import re
import logging
from typing import List

logger = logging.getLogger(__name__)

# --- Distractor Detection Patterns ---
# Compiled regex for performance (these run on every page analysis)

AD_PATTERNS = re.compile(
    r'(ad[\-_]?(?:wrapper|container|slot|unit|banner|block|frame|box|rail))|'
    r'(doubleclick|adsense|adsbygoogle|taboola|outbrain|prebid|'
    r'googlesyndication|amazon\-adsystem|criteo|mediavine|'
    r'ad\-placeholder|sponsored|promoted)',
    re.IGNORECASE
)

POPUP_PATTERNS = re.compile(
    r'(popup|pop\-up|modal|overlay|lightbox|dialog|interstitial|'
    r'notification[\-_]?bar|sticky[\-_]?bar|announcement[\-_]?bar|'
    r'cookie[\-_]?(?:banner|consent|notice|bar|popup)|'
    r'gdpr|consent[\-_]?(?:banner|modal|dialog)|'
    r'newsletter[\-_]?(?:popup|modal|signup)|'
    r'subscribe[\-_]?(?:popup|modal|overlay))',
    re.IGNORECASE
)

SIDEBAR_PATTERNS = re.compile(
    r'(sidebar|side[\-_]?bar|side[\-_]?column|widget[\-_]?area|'
    r'related[\-_]?(?:posts|articles|content)|'
    r'recommended[\-_]?(?:posts|articles)|'
    r'trending|popular[\-_]?(?:posts|articles))',
    re.IGNORECASE
)

ANIMATION_PATTERNS = re.compile(
    r'(carousel|slider|marquee|scroll[\-_]?(?:animation|ticker)|'
    r'auto[\-_]?(?:play|scroll|rotate)|'
    r'hero[\-_]?(?:slider|carousel|banner))',
    re.IGNORECASE
)


def classify_element(element: dict) -> dict:
    """
    Classify a single DOM element descriptor.

    Input element format:
    {
        "tag": "div",
        "classes": ["ad-wrapper", "sidebar"],
        "id": "google-ad-1",
        "attributes": {"role": "dialog", "aria-label": "Cookie consent"},
        "has_autoplay": false,
        "position": "fixed",
        "z_index": 9999
    }

    Returns classification:
    {
        "is_distractor": bool,
        "distractor_type": str | None,  # "ad", "popup", "sidebar", "animation"
        "confidence": float,            # 0.0 - 1.0
        "action": str                   # "hide", "pause", "dim", "none"
    }
    """
    classes_str = " ".join(element.get("classes", []))
    id_str = element.get("id", "")
    tag = element.get("tag", "").lower()
    attrs = element.get("attributes", {})
    combined = f"{classes_str} {id_str} {attrs.get('role', '')} {attrs.get('aria-label', '')}"

    # Check for ads
    if AD_PATTERNS.search(combined):
        return {
            "is_distractor": True,
            "distractor_type": "ad",
            "confidence": 0.90,
            "action": "hide"
        }

    # Check for popups / modals / cookie banners
    if POPUP_PATTERNS.search(combined):
        confidence = 0.85
        # Higher confidence if it has overlay positioning
        position = element.get("position", "")
        z_index = element.get("z_index", 0)
        if position in ("fixed", "sticky") and z_index > 100:
            confidence = 0.95
        return {
            "is_distractor": True,
            "distractor_type": "popup",
            "confidence": confidence,
            "action": "hide"
        }

    # Check for sidebars / related content
    if SIDEBAR_PATTERNS.search(combined):
        return {
            "is_distractor": True,
            "distractor_type": "sidebar",
            "confidence": 0.70,
            "action": "dim"  # Dim rather than hide — might contain useful nav
        }

    # Check for animations / carousels
    if ANIMATION_PATTERNS.search(combined):
        return {
            "is_distractor": True,
            "distractor_type": "animation",
            "confidence": 0.80,
            "action": "pause"
        }

    # Check for autoplay media
    if element.get("has_autoplay", False) and tag in ("video", "audio"):
        return {
            "is_distractor": True,
            "distractor_type": "autoplay_media",
            "confidence": 0.95,
            "action": "pause"
        }

    # Check for high z-index overlays with fixed positioning
    position = element.get("position", "")
    z_index = element.get("z_index", 0)
    if position == "fixed" and z_index > 999:
        return {
            "is_distractor": True,
            "distractor_type": "overlay",
            "confidence": 0.60,
            "action": "hide"
        }

    return {
        "is_distractor": False,
        "distractor_type": None,
        "confidence": 0.0,
        "action": "none"
    }


def analyze_dom(dom_snapshot: dict) -> dict:
    """
    Analyze a full DOM snapshot from the content script.

    Input format:
    {
        "node_count": int,
        "max_depth": int,
        "elements": [... element descriptors ...],
        "text_content": str,
        "url": str
    }

    Returns:
    {
        "node_count": int,
        "max_depth": int,
        "distractor_count": int,
        "animation_count": int,
        "distractors": [... classified distractors with selectors ...],
        "actions": {
            "hide": [... CSS selectors ...],
            "pause": [... CSS selectors ...],
            "dim": [... CSS selectors ...]
        }
    }
    """
    elements = dom_snapshot.get("elements", [])
    node_count = dom_snapshot.get("node_count", len(elements))
    max_depth = dom_snapshot.get("max_depth", 0)

    distractors = []
    actions = {"hide": [], "pause": [], "dim": []}

    distractor_count = 0
    animation_count = 0

    for elem in elements:
        classification = classify_element(elem)

        if classification["is_distractor"]:
            distractor_count += 1

            if classification["distractor_type"] in ("animation", "autoplay_media"):
                animation_count += 1

            # Build a CSS selector for this element
            selector = _build_selector(elem)
            if selector:
                classification["selector"] = selector
                distractors.append(classification)
                actions[classification["action"]].append(selector)

    return {
        "node_count": node_count,
        "max_depth": max_depth,
        "distractor_count": distractor_count,
        "animation_count": animation_count,
        "distractors": distractors,
        "actions": actions,
    }


def _build_selector(element: dict) -> str:
    """Build a CSS selector from an element descriptor."""
    tag = element.get("tag", "div")
    elem_id = element.get("id", "")
    classes = element.get("classes", [])

    if elem_id:
        return f"#{elem_id}"
    elif classes:
        class_selector = ".".join(classes[:3])  # Limit to 3 classes for specificity
        return f"{tag}.{class_selector}"
    else:
        return ""
