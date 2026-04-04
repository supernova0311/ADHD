"""
Text Simplification Agent
==========================
Hybrid text simplification combining:
1. Rule-based pre-processing (deterministic, fast)
2. LLM-powered rewriting (Gemini 1.5 Flash, quality)
3. Post-processing validation (ensuring improvement)

Profile-specific system prompts ensure genuinely different
transformations for ADHD, Dyslexia, and Autism modes.
"""

import os
import re
import logging
import textstat
from typing import Optional

logger = logging.getLogger(__name__)

# Try to load Gemini
_gemini_available = False
try:
    import google.generativeai as genai
    _gemini_available = True
except ImportError:
    logger.warning("google-generativeai not installed. Using mock simplifier.")


# --- Profile-Specific System Prompts ---
SYSTEM_PROMPTS = {
    "adhd": (
        "You are an expert plain-language editor specializing in making text accessible "
        "for readers with ADHD. Follow these rules strictly:\n"
        "1. Use SHORT, punchy sentences (max 15 words each).\n"
        "2. Bold the ONE key takeaway in each paragraph using **bold** markdown.\n"
        "3. Use bullet points to break dense information into scannable lists.\n"
        "4. Remove all filler phrases, redundant words, and tangential details.\n"
        "5. Front-load the most important information (inverted pyramid).\n"
        "6. Use active voice exclusively.\n"
        "7. Preserve ALL factual content — simplify phrasing, never meaning."
    ),
    "dyslexia": (
        "You are an expert plain-language editor specializing in making text accessible "
        "for readers with dyslexia. Follow these rules strictly:\n"
        "1. Use simple, common words (prefer Anglo-Saxon over Latin-derived).\n"
        "2. Keep sentences under 20 words.\n"
        "3. Use active voice and present tense when possible.\n"
        "4. Avoid words with similar visual shapes (e.g., 'through/thorough/though').\n"
        "5. Separate each instruction or idea onto its own line.\n"
        "6. Avoid abbreviations — spell out all words fully.\n"
        "7. Preserve ALL factual content — simplify phrasing, never meaning."
    ),
    "autism": (
        "You are an expert plain-language editor specializing in making text accessible "
        "for autistic readers. Follow these rules strictly:\n"
        "1. Replace ALL idioms, metaphors, and figurative language with literal equivalents.\n"
        "2. Be direct and unambiguous. Say exactly what you mean.\n"
        "3. Avoid sarcasm, irony, and implied meanings.\n"
        "4. Use consistent terminology — do not use synonyms for the same concept.\n"
        "5. Structure information in logical, sequential order.\n"
        "6. Explain any cultural references or assumptions explicitly.\n"
        "7. Preserve ALL factual content — simplify phrasing, never meaning."
    ),
    "custom": (
        "You are an expert plain-language editor. Simplify the following text:\n"
        "1. Use short, clear sentences.\n"
        "2. Use simple words and active voice.\n"
        "3. Break complex ideas into bullet points.\n"
        "4. Preserve ALL factual content — simplify phrasing, never meaning."
    ),
}


# --- Rule-Based Pre-Processing ---

# Common jargon → plain language substitutions
JARGON_MAP = {
    r'\butilize\b': 'use',
    r'\bfacilitate\b': 'help',
    r'\bsubsequently\b': 'then',
    r'\bnevertheless\b': 'but',
    r'\bnotwithstanding\b': 'despite',
    r'\bcommence\b': 'start',
    r'\bterminate\b': 'end',
    r'\bascertain\b': 'find out',
    r'\bameliorati\w+\b': 'improve',
    r'\bexpedit\w+\b': 'speed up',
    r'\bdelineate\b': 'describe',
    r'\bpromulgate\b': 'announce',
    r'\bperpetuat\w+\b': 'continue',
    r'\bin order to\b': 'to',
    r'\bdue to the fact that\b': 'because',
    r'\bat this point in time\b': 'now',
    r'\bin the event that\b': 'if',
    r'\bprior to\b': 'before',
    r'\bsubsequent to\b': 'after',
    r'\bwith regard to\b': 'about',
    r'\bin lieu of\b': 'instead of',
    r'\bin conjunction with\b': 'with',
    r'\bfor the purpose of\b': 'to',
    r'\bin spite of the fact that\b': 'although',
}


def _rule_based_simplify(text: str) -> str:
    """
    Apply deterministic rule-based simplifications.
    Fast, no API calls needed. Always produces some improvement.
    """
    result = text

    # 1. Substitute jargon with plain language
    for pattern, replacement in JARGON_MAP.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # 2. Remove excessive parenthetical asides (reduce cognitive load)
    # Only remove short parentheticals that are likely clarifications
    result = re.sub(r'\s*\([^)]{1,50}\)\s*', ' ', result)

    # 3. Split overly long sentences at semicolons
    result = result.replace('; ', '.\n')

    # 4. Remove redundant transition phrases
    redundant = [
        r'\bIt is worth noting that\b',
        r'\bIt should be noted that\b',
        r'\bIt is important to note that\b',
        r'\bAs a matter of fact,?\b',
        r'\bIn point of fact,?\b',
    ]
    for pattern in redundant:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    # 5. Clean up whitespace
    result = re.sub(r'\s+', ' ', result).strip()
    result = re.sub(r'\.\s*\.', '.', result)  # Remove double periods

    return result


def _validate_simplification(original: str, simplified: str) -> bool:
    """
    Validate that simplification actually improved readability.
    Returns True if the simplified text is genuinely easier.
    """
    if not simplified or len(simplified.strip()) < 10:
        return False

    orig_ease = textstat.flesch_reading_ease(original)
    simp_ease = textstat.flesch_reading_ease(simplified)

    # Simplified text should be easier (higher Flesch Reading Ease)
    if simp_ease < orig_ease - 5:  # Allow small tolerance
        logger.warning(
            f"Simplification made text harder! "
            f"Original FRE={orig_ease:.1f}, Simplified FRE={simp_ease:.1f}"
        )
        return False

    # Check meaning preservation via keyword overlap
    orig_words = set(re.findall(r'\b\w{4,}\b', original.lower()))
    simp_words = set(re.findall(r'\b\w{4,}\b', simplified.lower()))

    if orig_words:
        overlap = len(orig_words & simp_words) / len(orig_words)
        if overlap < 0.4:  # Less than 40% keyword retention
            logger.warning(
                f"Low keyword overlap ({overlap:.1%}). "
                f"Simplification may have lost meaning."
            )
            return False

    return True


async def simplify_text(
    text: str,
    profile: str = "adhd",
    api_key: Optional[str] = None,
) -> dict:
    """
    Simplify text using the hybrid pipeline.

    Returns:
    {
        "simplified_text": str,
        "method": "llm" | "rule_based" | "mock",
        "readability_before": float,
        "readability_after": float,
        "improvement": float,
    }
    """
    if not text or len(text.strip()) < 20:
        return {
            "simplified_text": text,
            "method": "passthrough",
            "readability_before": 0,
            "readability_after": 0,
            "improvement": 0,
        }

    readability_before = textstat.flesch_reading_ease(text)

    # Step 1: Always apply rule-based pre-processing
    preprocessed = _rule_based_simplify(text)

    # Step 2: Try LLM-powered simplification
    simplified = None
    method = "rule_based"

    if api_key and _gemini_available:
        try:
            simplified = await _llm_simplify(preprocessed, profile, api_key)
            if simplified and _validate_simplification(text, simplified):
                method = "llm"
            else:
                simplified = None  # Fall back to rule-based
        except Exception as e:
            logger.error(f"LLM simplification failed: {e}")
            simplified = None

    if simplified is None:
        simplified = preprocessed

    readability_after = textstat.flesch_reading_ease(simplified)

    return {
        "simplified_text": simplified,
        "method": method,
        "readability_before": round(readability_before, 2),
        "readability_after": round(readability_after, 2),
        "improvement": round(readability_after - readability_before, 2),
    }


async def _llm_simplify(text: str, profile: str, api_key: str) -> Optional[str]:
    """Call Gemini for text simplification. Handles multiple SDK versions."""
    
    system_prompt = SYSTEM_PROMPTS.get(profile, SYSTEM_PROMPTS["custom"])
    
    prompt = f"""{system_prompt}

---
TEXT TO SIMPLIFY:
{text}
---

Provide ONLY the simplified text. Do not include any preamble, explanation, or metadata."""

    # Try the modern SDK API first (v0.3+)
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2048,
            ),
        )
        response = await model.generate_content_async(prompt)
        if response and response.text:
            return response.text.strip()
    except AttributeError:
        # SDK too old for GenerativeModel — try REST fallback
        pass
    except Exception as e:
        logger.error(f"Gemini SDK error: {e}")

    # Fallback: Direct REST API call (works regardless of SDK version)
    try:
        import urllib.request
        import json

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 2048,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
    except Exception as e:
        logger.error(f"Gemini REST fallback failed: {e}")

    return None

