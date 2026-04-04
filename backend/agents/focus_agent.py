"""
Focus / Distraction Agent
===========================
Determines which DOM elements should be hidden, dimmed, or paused
based on the user's profile and element classification.

This agent works with the DOM Analyzer's output to generate
actionable CSS selectors and JavaScript commands.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# Profile-specific distraction sensitivity
# Higher values = more aggressive in removing distractions
PROFILE_AGGRESSIVENESS = {
    "adhd": {
        "hide_ads": True,
        "hide_popups": True,
        "hide_sidebars": True,
        "hide_cookie_banners": True,
        "pause_animations": True,
        "pause_autoplay": True,
        "dim_non_essential": True,
        "confidence_threshold": 0.50,  # Aggressive — remove anything suspect
    },
    "dyslexia": {
        "hide_ads": True,
        "hide_popups": True,
        "hide_sidebars": False,    # Sidebars might have useful navigation
        "hide_cookie_banners": True,
        "pause_animations": True,
        "pause_autoplay": True,
        "dim_non_essential": False,
        "confidence_threshold": 0.70,
    },
    "autism": {
        "hide_ads": True,
        "hide_popups": True,
        "hide_sidebars": False,
        "hide_cookie_banners": True,
        "pause_animations": True,   # Critical — unpredictable motion causes distress
        "pause_autoplay": True,     # Must be 100% stopped
        "dim_non_essential": False,
        "confidence_threshold": 0.60,
    },
    "custom": {
        "hide_ads": True,
        "hide_popups": True,
        "hide_sidebars": False,
        "hide_cookie_banners": True,
        "pause_animations": True,
        "pause_autoplay": True,
        "dim_non_essential": False,
        "confidence_threshold": 0.70,
    },
}


def generate_focus_actions(
    dom_analysis: dict,
    profile: str,
    custom_settings: dict = None,
) -> dict:
    """
    Generate focus actions (hide/pause/dim) based on DOM analysis and profile.

    Input dom_analysis (from dom_analyzer.analyze_dom):
    {
        "distractors": [...],
        "actions": {"hide": [...], "pause": [...], "dim": [...]},
        ...
    }

    Returns:
    {
        "hide_selectors": [str],        # CSS selectors to display:none
        "pause_selectors": [str],       # Media selectors to pause
        "dim_selectors": [str],         # CSS selectors to reduce opacity
        "css_rules": str,               # Combined CSS for all focus actions
        "js_commands": [str],           # JS commands to execute (pause media, etc.)
        "elements_removed": int,        # Count of elements affected
        "profile_description": str,
    }
    """
    config = PROFILE_AGGRESSIVENESS.get(profile, PROFILE_AGGRESSIVENESS["custom"])

    # Apply custom settings overrides
    if custom_settings:
        aggressiveness = custom_settings.get("distraction_level", "medium")
        if aggressiveness == "high":
            config["confidence_threshold"] = 0.40
            config["hide_sidebars"] = True
            config["dim_non_essential"] = True
        elif aggressiveness == "low":
            config["confidence_threshold"] = 0.85
            config["hide_sidebars"] = False
            config["dim_non_essential"] = False

    hide_selectors = []
    pause_selectors = []
    dim_selectors = []
    js_commands = []

    distractors = dom_analysis.get("distractors", [])

    for distractor in distractors:
        if distractor.get("confidence", 0) < config["confidence_threshold"]:
            continue

        selector = distractor.get("selector", "")
        if not selector:
            continue

        d_type = distractor.get("distractor_type", "")

        if d_type == "ad" and config["hide_ads"]:
            hide_selectors.append(selector)
        elif d_type == "popup" and config["hide_popups"]:
            hide_selectors.append(selector)
        elif d_type == "sidebar" and config["hide_sidebars"]:
            dim_selectors.append(selector)  # Dim rather than hide
        elif d_type in ("animation", "autoplay_media") and config["pause_animations"]:
            pause_selectors.append(selector)
            js_commands.append(f'document.querySelectorAll("{selector}").forEach(el => {{ if(el.pause) el.pause(); }})')
        elif d_type == "overlay" and config["hide_popups"]:
            hide_selectors.append(selector)

    # Build CSS
    css_parts = ["/* NeuroUI Focus Agent - Distraction Removal */"]

    if hide_selectors:
        selectors = ",\n".join(hide_selectors)
        css_parts.append(f"{selectors} {{\n  display: none !important;\n}}")

    if dim_selectors and config["dim_non_essential"]:
        selectors = ",\n".join(dim_selectors)
        css_parts.append(f"""{selectors} {{
  opacity: 0.2 !important;
  transition: opacity 0.3s !important;
}}
{selectors}:hover {{
  opacity: 1 !important;
}}""")

    if pause_selectors:
        selectors = ",\n".join(pause_selectors)
        css_parts.append(f"""{selectors} {{
  animation-play-state: paused !important;
}}""")

    # Always add these focus-enhancing rules
    if config.get("pause_animations", False):
        css_parts.append("""
/* Global animation pause */
@media (prefers-reduced-motion: reduce) {
  * {
    animation: none !important;
    transition: none !important;
  }
}""")

    # Body scroll lock removal (for cookie consent overlays)
    if config["hide_cookie_banners"]:
        js_commands.append(
            'document.body.style.overflow = "auto";'
            'document.documentElement.style.overflow = "auto";'
        )

    return {
        "hide_selectors": hide_selectors,
        "pause_selectors": pause_selectors,
        "dim_selectors": dim_selectors,
        "css_rules": "\n".join(css_parts),
        "js_commands": js_commands,
        "elements_removed": len(hide_selectors) + len(dim_selectors) + len(pause_selectors),
        "profile_description": f"{profile} focus profile (threshold={config['confidence_threshold']})",
    }
