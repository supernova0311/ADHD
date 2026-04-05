"""
Multi-Agent System Orchestrator
================================
Coordinates the three specialized agents (Text Simplification,
Visual Adaptation, Focus/Distraction) using the Orchestrator-Worker pattern.

Pipeline:
1. Receive raw text chunks + DOM metadata + user profile
2. Run Cognitive Metrics on raw input (CLS_before)
3. Dispatch to agents in parallel
4. Aggregate transformation instructions
5. Run Cognitive Metrics on simplified output (CLS_after)
6. Return unified response
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, List

from core.cognitive_metrics import compute_cls
from core.dom_analyzer import analyze_dom
from agents.text_simplifier import simplify_text
from agents.visual_adapter import get_visual_adaptations
from agents.focus_agent import generate_focus_actions

logger = logging.getLogger(__name__)


async def process_page(
    chunks: list[str],
    profile: str,
    dom_snapshot: Optional[dict] = None,
    custom_settings: Optional[dict] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Main orchestration endpoint. Processes a full page through the MAS pipeline.
    Has a 15-second hard timeout to ensure interactive responsiveness.
    """
    try:
        return await asyncio.wait_for(
            _process_page_inner(chunks, profile, dom_snapshot, custom_settings, api_key),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Pipeline timed out after 15s — returning rule-based fallback")
        from core.cognitive_metrics import compute_cls as _compute_cls
        from agents.text_simplifier import _rule_based_simplify
        from agents.visual_adapter import get_visual_adaptations as _get_vis
        from agents.focus_agent import generate_focus_actions as _gen_focus

        # Quick fallback: rule-based only
        simplified = [_rule_based_simplify(c) if len(c.strip()) >= 20 else c for c in chunks]
        vis = _get_vis(profile, custom_settings)
        cls_before = _compute_cls(" ".join(chunks))
        cls_after = _compute_cls(" ".join(simplified))
        return {
            "simplified_chunks": simplified,
            "simplification_details": [],
            "visual_css": vis["css_rules"],
            "visual_description": vis["description"],
            "focus_actions": {"css_rules": "", "js_commands": [], "hide_selectors": []},
            "cls_before": cls_before,
            "cls_after": cls_after,
            "cls_improvement": round(cls_before["cls"] - cls_after["cls"], 2),
            "metrics": {
                "chunks_processed": len(chunks),
                "methods_used": {"rule_based": len(chunks)},
                "avg_readability_improvement": 0,
                "distractors_detected": 0,
                "elements_removed": 0,
                "profile": profile,
                "timeout": True,
            },
        }


async def _process_page_inner(
    chunks: list[str],
    profile: str,
    dom_snapshot: Optional[dict] = None,
    custom_settings: Optional[dict] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Main orchestration endpoint. Processes a full page through the MAS pipeline.

    Args:
        chunks: List of text chunks extracted from the page
        profile: "adhd" | "dyslexia" | "autism" | "custom"
        dom_snapshot: DOM metadata from content script
        custom_settings: User's custom overrides (spacing, colors, etc.)
        api_key: Gemini API key for LLM simplification

    Returns:
        {
            "simplified_chunks": [...],
            "visual_css": str,
            "focus_actions": {...},
            "cls_before": {...},
            "cls_after": {...},
            "cls_improvement": float,
            "metrics": {...},
        }
    """
    # --- Step 1: Analyze DOM Structure ---
    dom_analysis = {"node_count": 0, "max_depth": 0, "distractor_count": 0,
                    "animation_count": 0, "distractors": [], "actions": {}}

    if dom_snapshot:
        dom_analysis = analyze_dom(dom_snapshot)

    dom_metadata = {
        "node_count": dom_analysis.get("node_count", 0),
        "max_depth": dom_analysis.get("max_depth", 0),
        "distractor_count": dom_analysis.get("distractor_count", 0),
        "animation_count": dom_analysis.get("animation_count", 0),
    }

    # --- Step 2: Compute CLS BEFORE transformation ---
    full_text = " ".join(chunks)
    cls_before = compute_cls(full_text, dom_metadata)

    # --- Step 3: Dispatch to agents in parallel ---
    # Text simplification tasks (one per chunk)
    simplification_tasks = [
        simplify_text(chunk, profile, api_key)
        for chunk in chunks
    ]

    # Visual adaptation (synchronous, no IO)
    visual_result = get_visual_adaptations(profile, custom_settings)

    # Focus agent (synchronous, deterministic)
    focus_result = generate_focus_actions(dom_analysis, profile, custom_settings)

    # Await all text simplifications concurrently
    simplification_results = await asyncio.gather(*simplification_tasks)

    # --- Step 4: Aggregate results ---
    simplified_chunks = [r["simplified_text"] for r in simplification_results]
    methods_used = [r["method"] for r in simplification_results]

    # --- Step 5: Compute CLS AFTER transformation ---
    simplified_full_text = " ".join(simplified_chunks)

    # After transformation, distractors are removed → lower clutter
    post_dom_metadata = {
        "node_count": max(0, dom_metadata["node_count"] - focus_result["elements_removed"] * 5),
        "max_depth": dom_metadata["max_depth"],
        "distractor_count": max(0, dom_metadata["distractor_count"] - focus_result["elements_removed"]),
        "animation_count": 0,  # All animations paused
    }

    cls_after = compute_cls(simplified_full_text, post_dom_metadata)

    # --- Step 6: Compile metrics ---
    total_readability_improvement = sum(
        r["improvement"] for r in simplification_results
    ) / max(len(simplification_results), 1)

    metrics = {
        "chunks_processed": len(chunks),
        "methods_used": dict(zip(
            ["llm", "rule_based", "mock", "passthrough"],
            [methods_used.count(m) for m in ["llm", "rule_based", "mock", "passthrough"]]
        )),
        "avg_readability_improvement": round(total_readability_improvement, 2),
        "distractors_detected": dom_analysis.get("distractor_count", 0),
        "elements_removed": focus_result["elements_removed"],
        "profile": profile,
    }

    cls_improvement = cls_before["cls"] - cls_after["cls"]

    return {
        "simplified_chunks": simplified_chunks,
        "simplification_details": simplification_results,
        "visual_css": visual_result["css_rules"],
        "visual_description": visual_result["description"],
        "focus_actions": {
            "css_rules": focus_result["css_rules"],
            "js_commands": focus_result["js_commands"],
            "hide_selectors": focus_result["hide_selectors"],
        },
        "cls_before": cls_before,
        "cls_after": cls_after,
        "cls_improvement": round(cls_improvement, 2),
        "metrics": metrics,
    }
