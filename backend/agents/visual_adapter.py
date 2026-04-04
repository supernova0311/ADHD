"""
Visual Adaptation Agent
========================
Pure deterministic CSS transformation rules based on neurodivergent
user profiles. No LLM needed — all rules trace to research evidence.

Research basis:
- ADHD: Reduce visual noise (W3C COGA Objective 5: Help Users Focus)
- Dyslexia: Increase spacing (strongest evidence per NIH, 2023)
- Autism: Muted colors + consistent layouts (sensory processing research)
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


# --- Profile CSS Rules ---
# Each profile returns a set of CSS rules to inject into the page

PROFILE_CSS = {
    "adhd": {
        "description": "ADHD mode: Remove distractions, reduce animations, mute non-essential visuals",
        "global_css": """
            /* Kill ALL animations and transitions - critical for focus */
            *, *::before, *::after {
                animation-duration: 0s !important;
                animation-delay: 0s !important;
                transition-duration: 0s !important;
                transition-delay: 0s !important;
                scroll-behavior: auto !important;
            }

            /* Mute non-essential visual elements */
            aside, [role="complementary"], [role="banner"] {
                opacity: 0.3 !important;
                transition: opacity 0.2s !important;
            }
            aside:hover, [role="complementary"]:hover, [role="banner"]:hover {
                opacity: 1 !important;
            }

            /* Reduce visual weight of images (they pull attention) */
            img:not([role="img"]):not(.essential) {
                opacity: 0.7 !important;
                filter: grayscale(30%) !important;
            }

            /* Stop autoplay videos */
            video[autoplay] {
                display: none !important;
            }

            /* Highlight main content area */
            main, [role="main"], article, .content, #content {
                border-left: 3px solid #4A90D9 !important;
                padding-left: 12px !important;
                background-color: rgba(74, 144, 217, 0.03) !important;
            }

            /* Remove floating/sticky elements that break focus */
            [style*="position: fixed"]:not(nav):not(header),
            [style*="position: sticky"]:not(nav):not(header) {
                position: relative !important;
            }
        """,
        "font_css": """
            /* Clean typography for focus */
            body {
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif !important;
                line-height: 1.6 !important;
            }
        """,
    },

    "dyslexia": {
        "description": "Dyslexia mode: Maximise spacing, readable fonts, left-aligned text",
        "global_css": """
            /* Typography - Research-backed spacing interventions */
            body, p, li, td, th, span, div {
                font-family: 'Verdana', 'Arial', 'Helvetica Neue', sans-serif !important;
                letter-spacing: 0.12em !important;
                word-spacing: 0.16em !important;
                line-height: 1.8 !important;
                text-align: left !important;
            }

            /* Constrain line length to reduce tracking difficulty */
            p, li, td, blockquote {
                max-width: 65ch !important;
            }

            /* Remove justified text - causes uneven word spacing */
            * {
                text-align: left !important;
                hyphens: none !important;
            }

            /* Increase paragraph spacing */
            p {
                margin-bottom: 1.2em !important;
            }

            /* No italics - they tilt character shapes */
            em, i, [style*="font-style: italic"] {
                font-style: normal !important;
                text-decoration: underline !important;
            }

            /* Ensure sufficient contrast without harshness */
            body {
                background-color: #FAFAF5 !important;
                color: #2D2D2D !important;
            }

            /* Make links clearly distinguishable */
            a {
                color: #1A56DB !important;
                text-decoration: underline !important;
                text-underline-offset: 3px !important;
            }

            /* Reading ruler effect via focus glow on paragraphs */
            p:hover, li:hover {
                background-color: rgba(255, 255, 200, 0.3) !important;
            }
        """,
        "font_css": """
            /* Font size minimum */
            body {
                font-size: max(16px, 1rem) !important;
            }
            h1 { font-size: 2em !important; }
            h2 { font-size: 1.6em !important; }
            h3 { font-size: 1.3em !important; }
        """,
    },

    "autism": {
        "description": "Autism mode: Reduce sensory stimulation, enforce predictability, mute colors",
        "global_css": """
            /* Desaturate the entire page - reduce sensory load */
            html {
                filter: saturate(60%) !important;
            }

            /* Remove ALL animations, transitions, and motion */
            *, *::before, *::after {
                animation: none !important;
                transition: none !important;
                scroll-behavior: auto !important;
            }

            /* Remove background images (visual noise) */
            *:not(img):not(video):not(canvas):not(svg) {
                background-image: none !important;
            }

            /* Consistent, calm color scheme */
            body {
                background-color: #F5F5F0 !important;
                color: #333333 !important;
            }

            /* Remove text shadows and decorative borders */
            * {
                text-shadow: none !important;
            }

            /* Stop ALL media autoplay */
            video, audio {
                autoplay: false;
            }
            video[autoplay], audio[autoplay] {
                display: none !important;
            }

            /* Enforce consistent heading hierarchy */
            h1, h2, h3, h4, h5, h6 {
                font-family: 'Segoe UI', system-ui, sans-serif !important;
                font-weight: 600 !important;
                margin-top: 1.5em !important;
                margin-bottom: 0.5em !important;
                border-bottom: 1px solid #E0E0E0 !important;
                padding-bottom: 0.3em !important;
            }

            /* Reduce visual complexity of links */
            a {
                color: #2C5F9E !important;
                text-decoration: underline !important;
            }
            a:visited {
                color: #5B4B8A !important;
            }

            /* Remove hover effects that cause unexpected changes */
            *:hover {
                transform: none !important;
                box-shadow: none !important;
            }

            /* Make form elements predictable */
            input, select, textarea, button {
                border: 2px solid #999 !important;
                border-radius: 4px !important;
                padding: 8px !important;
                font-size: 16px !important;
            }
        """,
        "font_css": """
            body {
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif !important;
                line-height: 1.7 !important;
                font-size: max(16px, 1rem) !important;
            }
        """,
    },
}


def get_visual_adaptations(profile: str, custom_settings: dict = None) -> dict:
    """
    Get CSS transformation rules for a given profile.

    Returns:
    {
        "description": str,
        "css_rules": str,       # Combined CSS to inject
        "profile": str,
    }
    """
    if profile in PROFILE_CSS:
        config = PROFILE_CSS[profile]
        combined_css = config["global_css"] + "\n" + config["font_css"]

        # Apply custom overrides if present
        if custom_settings:
            combined_css = _apply_custom_overrides(combined_css, custom_settings)

        return {
            "description": config["description"],
            "css_rules": combined_css.strip(),
            "profile": profile,
        }

    # Custom profile with user-specified settings
    return _build_custom_css(custom_settings or {})


def _apply_custom_overrides(base_css: str, settings: dict) -> str:
    """Apply user's custom settings as CSS overrides on top of a profile."""
    overrides = []

    # Spacing multiplier
    spacing = settings.get("spacing_multiplier", 1.0)
    if spacing != 1.0:
        overrides.append(f"""
            body, p, li, td {{
                letter-spacing: {0.05 * spacing:.2f}em !important;
                word-spacing: {0.08 * spacing:.2f}em !important;
                line-height: {1.5 * spacing:.1f} !important;
            }}
        """)

    # Color mode
    color_mode = settings.get("color_mode", "original")
    if color_mode == "warm":
        overrides.append("""
            html { filter: sepia(15%) !important; }
            body { background-color: #FFF8F0 !important; }
        """)
    elif color_mode == "high_contrast":
        overrides.append("""
            body { background-color: #000 !important; color: #FFF !important; }
            a { color: #6DB3F2 !important; }
        """)
    elif color_mode == "muted":
        overrides.append("""
            html { filter: saturate(50%) !important; }
        """)

    # Font size override
    font_size = settings.get("font_size", None)
    if font_size:
        overrides.append(f"""
            body {{ font-size: {font_size}px !important; }}
        """)

    return base_css + "\n" + "\n".join(overrides)


def _build_custom_css(settings: dict) -> dict:
    """Build a fully custom CSS configuration from user settings."""
    css_parts = [
        "/* Custom NeuroUI Profile */",
    ]

    spacing = settings.get("spacing_multiplier", 1.2)
    css_parts.append(f"""
        body, p, li, td {{
            letter-spacing: {0.05 * spacing:.2f}em !important;
            word-spacing: {0.08 * spacing:.2f}em !important;
            line-height: {1.5 * spacing:.1f} !important;
            font-family: 'Verdana', 'Arial', sans-serif !important;
        }}
    """)

    if settings.get("remove_animations", True):
        css_parts.append("""
            *, *::before, *::after {
                animation: none !important;
                transition: none !important;
            }
        """)

    return {
        "description": "Custom NeuroUI profile",
        "css_rules": "\n".join(css_parts),
        "profile": "custom",
    }
