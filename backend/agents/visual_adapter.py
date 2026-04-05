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
            /* Kill animations and transitions - critical for focus */
            *, *::before, *::after {
                animation-duration: 0s !important;
                animation-delay: 0s !important;
                transition-duration: 0s !important;
                transition-delay: 0s !important;
                scroll-behavior: auto !important;
            }

            /* Gently mute non-essential visual elements */
            aside:not(main aside), [role="complementary"] {
                opacity: 0.5 !important;
            }
            aside:not(main aside):hover, [role="complementary"]:hover {
                opacity: 1 !important;
            }

            /* Stop autoplay videos */
            video[autoplay] {
                display: none !important;
            }

            /* Subtle highlight on main content — only direct main/article */
            body > main, body > article, [role="main"] {
                border-left: 3px solid rgba(74, 144, 217, 0.5) !important;
                padding-left: 12px !important;
            }
        """,
        "font_css": """
            /* Clean typography for focus — text elements only */
            p, li, td, th, blockquote, figcaption, dd, dt {
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif !important;
                line-height: 1.65 !important;
            }
        """,
    },

    "dyslexia": {
        "description": "Dyslexia mode: Maximise spacing, readable fonts, left-aligned text",
        "global_css": """
            /* Typography — scoped to text content, protects icon fonts */
            p, li, td, th, blockquote, figcaption, dd, dt,
            h1, h2, h3, h4, h5, h6 {
                font-family: 'Verdana', 'Arial', 'Helvetica Neue', sans-serif !important;
                letter-spacing: 0.12em !important;
                word-spacing: 0.16em !important;
                line-height: 1.8 !important;
            }

            /* Left-align text content only — don't break navs/buttons */
            p, li, td, th, blockquote, dd, dt {
                text-align: left !important;
                hyphens: none !important;
            }

            /* Constrain line length to reduce tracking difficulty */
            p, li, td, blockquote {
                max-width: 65ch !important;
            }

            /* Increase paragraph spacing */
            p {
                margin-bottom: 1.2em !important;
            }

            /* No italics on text content — they tilt character shapes */
            p em, p i, li em, li i,
            td em, td i, blockquote em, blockquote i {
                font-style: normal !important;
                text-decoration: underline !important;
                text-decoration-color: rgba(0, 0, 0, 0.3) !important;
            }

            /* Make links clearly distinguishable */
            a {
                text-decoration: underline !important;
                text-underline-offset: 3px !important;
            }

            /* Reading ruler effect via focus glow on paragraphs */
            p:hover, li:hover {
                background-color: rgba(255, 255, 200, 0.25) !important;
                border-radius: 4px;
            }
        """,
        "font_css": """
            /* Font size minimum — text content only */
            p, li, td, th, blockquote, dd, dt {
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
            /* Gently desaturate — reduce sensory load without killing the page */
            html {
                filter: saturate(65%) !important;
            }

            /* Remove animations and transitions */
            *, *::before, *::after {
                animation: none !important;
                transition: none !important;
                scroll-behavior: auto !important;
            }

            /* Remove decorative background images on containers only */
            div, section, header, footer, aside, nav, main, article {
                background-image: none !important;
            }

            /* Remove text shadows on content */
            p, li, td, th, h1, h2, h3, h4, h5, h6, span, a {
                text-shadow: none !important;
            }

            /* Stop ALL media autoplay */
            video[autoplay], audio[autoplay] {
                display: none !important;
            }

            /* Enforce consistent heading hierarchy */
            h1, h2, h3, h4, h5, h6 {
                font-family: 'Segoe UI', system-ui, sans-serif !important;
                font-weight: 600 !important;
                margin-top: 1.5em !important;
                margin-bottom: 0.5em !important;
            }

            /* Subtle separator on h2+ only */
            h2, h3 {
                border-bottom: 1px solid rgba(0, 0, 0, 0.1) !important;
                padding-bottom: 0.3em !important;
            }

            /* Consistent, underlined links */
            a {
                text-decoration: underline !important;
            }

            /* Remove transform hover effects on interactive elements only */
            a:hover, button:hover, [role="button"]:hover {
                transform: none !important;
            }

            /* Predictable form elements */
            input, select, textarea {
                border: 2px solid #999 !important;
                border-radius: 4px !important;
                padding: 8px !important;
                font-size: 16px !important;
            }
        """,
        "font_css": """
            p, li, td, th, blockquote, figcaption, dd, dt {
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
