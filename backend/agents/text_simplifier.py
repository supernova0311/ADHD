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

from __future__ import annotations

import os
import re
import logging
import asyncio
import textstat
from typing import Optional, List

logger = logging.getLogger(__name__)

# Try to load Gemini
_gemini_available = False
try:
    import google.generativeai as genai
    _gemini_available = True
except ImportError:
    logger.warning("google-generativeai not installed. Using mock simplifier.")

# One-time Gemini configuration (avoid re-configuring on every call)
_gemini_configured = False
_gemini_model = None


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
    # Formal → Simple verbs
    r'\butilize\b': 'use',
    r'\bfacilitate\b': 'help',
    r'\bcommence\b': 'start',
    r'\bterminate\b': 'end',
    r'\bascertain\b': 'find out',
    r'\bdelineate\b': 'describe',
    r'\bpromulgate\b': 'announce',
    r'\bprocure\b': 'get',
    r'\bengender\b': 'cause',
    r'\bconvene\b': 'meet',
    r'\bdisseminate\b': 'share',
    r'\belucidate\b': 'explain',
    r'\bexacerbate\b': 'worsen',
    r'\bmitigate\b': 'reduce',
    r'\baugment\b': 'increase',
    r'\boptimize\b': 'improve',
    r'\bleverage\b': 'use',
    r'\bsuccumb\b': 'give in',
    r'\bcoalesce\b': 'merge',
    r'\bascribe\b': 'attribute',
    r'\brelinquish\b': 'give up',
    r'\bcircumvent\b': 'avoid',
    r'\bpermeate\b': 'spread through',
    r'\bpreclude\b': 'prevent',
    r'\bstipulate\b': 'require',
    r'\bsubstantiate\b': 'prove',
    r'\bsupersede\b': 'replace',
    r'\btranscend\b': 'go beyond',
    # Formal → Simple adjectives/adverbs
    r'\bsubsequently\b': 'then',
    r'\bnevertheless\b': 'but',
    r'\bnotwithstanding\b': 'despite',
    r'\bconcomitant\b': 'related',
    r'\bubiquitous\b': 'widespread',
    r'\binnumerable\b': 'many',
    r'\bsuperfluous\b': 'extra',
    r'\bpernicious\b': 'harmful',
    r'\bpurportedly\b': 'supposedly',
    r'\bostensibly\b': 'seemingly',
    r'\bheretofore\b': 'until now',
    # Regex-capable word families
    r'\bameliorati\w+\b': 'improve',
    r'\bexpedit\w+\b': 'speed up',
    r'\bperpetuat\w+\b': 'continue',
    r'\bproliferati\w+\b': 'spread',
    # Wordy phrases → Simple
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
    r'\bon the basis of\b': 'based on',
    r'\bin the near future\b': 'soon',
    r'\bat the present time\b': 'now',
    r'\bin close proximity to\b': 'near',
    r'\bin the absence of\b': 'without',
    r'\bwith the exception of\b': 'except for',
    r'\bfor the duration of\b': 'during',
    r'\bin the majority of cases\b': 'usually',
    r'\bin accordance with\b': 'following',
    r'\bas a consequence of\b': 'because of',
    r'\bwith respect to\b': 'about',
    r'\bon a regular basis\b': 'regularly',
    r'\bin a timely manner\b': 'quickly',
    r'\btake into consideration\b': 'consider',
    r'\bmake a determination\b': 'decide',
    r'\bgive consideration to\b': 'consider',
    r'\bis indicative of\b': 'shows',
    r'\bis in a position to\b': 'can',
    r'\bhas the capacity to\b': 'can',
    # Buzzwords → Plain
    r'\bparadigm\b': 'model',
    r'\bsynergy\b': 'teamwork',
    r'\bstakeholder\b': 'person involved',
    r'\bholistic\b': 'complete',
    r'\bmethodology\b': 'method',
    r'\bimplementation\b': 'setup',
    r'\bscalable\b': 'flexible',
    r'\beckosystem\b': 'system',
    r'\bactionable\b': 'useful',
    r'\bincentivize\b': 'encourage',
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

    # Step 2: Decide whether LLM is needed
    simplified = None
    method = "rule_based"

    # Skip LLM for text that's already simple (saves time + API quota)
    text_is_simple = readability_before >= 70  # Flesch >= 70 = easy
    text_is_short = len(text.split()) < 25

    # Fast-path: if rule-based already achieves big improvement, skip LLM
    preprocessed_readability = textstat.flesch_reading_ease(preprocessed)
    rule_improvement = preprocessed_readability - readability_before
    if rule_improvement > 15:
        logger.info(f"Rule-based achieved +{rule_improvement:.0f} FRE improvement, skipping LLM")
        text_is_simple = True  # Force skip

    if api_key and _gemini_available and not text_is_simple and not text_is_short:
        # Check circuit breaker
        if not _is_circuit_open():
            try:
                simplified = await asyncio.wait_for(
                    _llm_simplify(preprocessed, profile, api_key),
                    timeout=10.0,  # Hard 10s ceiling for LLM call
                )
                if simplified and _validate_simplification(text, simplified):
                    method = "llm"
                    _record_llm_success()
                else:
                    simplified = None  # Fall back to rule-based
            except asyncio.TimeoutError:
                logger.warning("LLM simplification timed out after 10s, using rule-based")
                _record_llm_failure()
                simplified = None
            except Exception as e:
                logger.error(f"LLM simplification failed: {e}")
                _record_llm_failure()
                simplified = None
        else:
            logger.info("Circuit breaker OPEN — skipping LLM, using rule-based")
    elif text_is_simple:
        logger.info(f"Text already simple (FRE={readability_before:.0f}), skipping LLM")

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


# --- Batch Simplification (single LLM call for all chunks) ---

async def simplify_batch(
    chunks: list[str],
    profile: str = "adhd",
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Batch-simplify multiple chunks using ONE LLM call instead of N.
    Dramatically reduces latency: 5 chunks → 1 API call instead of 5.
    Falls back to individual rule-based processing on failure.
    """
    results: list[Optional[dict]] = [None] * len(chunks)
    llm_indices = []
    preprocessed_map = {}

    # Phase 1: Triage — decide which chunks need LLM vs rule-based
    for i, text in enumerate(chunks):
        if not text or len(text.strip()) < 20:
            results[i] = {
                "simplified_text": text,
                "method": "passthrough",
                "readability_before": 0,
                "readability_after": 0,
                "improvement": 0,
            }
            continue

        readability_before = textstat.flesch_reading_ease(text)
        preprocessed = _rule_based_simplify(text)
        preprocessed_readability = textstat.flesch_reading_ease(preprocessed)
        rule_improvement = preprocessed_readability - readability_before

        text_is_simple = readability_before >= 70 or rule_improvement > 15
        text_is_short = len(text.split()) < 25

        if (api_key and _gemini_available and not text_is_simple
                and not text_is_short and not _is_circuit_open()):
            llm_indices.append(i)
            preprocessed_map[i] = preprocessed
        else:
            results[i] = {
                "simplified_text": preprocessed,
                "method": "rule_based",
                "readability_before": round(readability_before, 2),
                "readability_after": round(preprocessed_readability, 2),
                "improvement": round(preprocessed_readability - readability_before, 2),
            }

    # Phase 2: Single batched LLM call for all chunks that need it
    if llm_indices and api_key:
        llm_texts = [preprocessed_map[i] for i in llm_indices]
        logger.info(f"Batch LLM: {len(llm_texts)} chunks in 1 call (skipped {len(chunks) - len(llm_texts)} simple)")

        try:
            llm_results = await asyncio.wait_for(
                _llm_simplify_batch(llm_texts, profile, api_key),
                timeout=12.0,
            )
            _record_llm_success()

            for j, idx in enumerate(llm_indices):
                original = chunks[idx]
                rb = textstat.flesch_reading_ease(original)

                if j < len(llm_results) and llm_results[j] and _validate_simplification(original, llm_results[j]):
                    simplified = llm_results[j]
                    method = "llm"
                else:
                    simplified = preprocessed_map[idx]
                    method = "rule_based"

                ra = textstat.flesch_reading_ease(simplified)
                results[idx] = {
                    "simplified_text": simplified,
                    "method": method,
                    "readability_before": round(rb, 2),
                    "readability_after": round(ra, 2),
                    "improvement": round(ra - rb, 2),
                }

        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Batch LLM failed ({type(e).__name__}), falling back to rule-based")
            _record_llm_failure()

    # Phase 3: Fill any remaining gaps with rule-based
    for i in range(len(results)):
        if results[i] is None:
            original = chunks[i]
            pre = _rule_based_simplify(original)
            rb = textstat.flesch_reading_ease(original)
            ra = textstat.flesch_reading_ease(pre)
            results[i] = {
                "simplified_text": pre,
                "method": "rule_based",
                "readability_before": round(rb, 2),
                "readability_after": round(ra, 2),
                "improvement": round(ra - rb, 2),
            }

    return results


async def _llm_simplify_batch(
    chunks: list[str], profile: str, api_key: str
) -> list[str]:
    """Send multiple chunks in a single Gemini call with delimiters."""
    system_prompt = SYSTEM_PROMPTS.get(profile, SYSTEM_PROMPTS["custom"])

    numbered = "\n\n===CHUNK===\n\n".join(
        f"[{i+1}] {chunk}" for i, chunk in enumerate(chunks)
    )

    prompt = f"""{system_prompt}

---
You are given {len(chunks)} text chunks separated by ===CHUNK===.
Simplify EACH chunk independently according to the rules above.
Keep the [{'{N}'}] numbering and ===CHUNK=== delimiters in your response.
Output ONLY the simplified text for each chunk. No preamble.
---

{numbered}"""

    try:
        _ensure_gemini_configured(api_key)
        response = await _gemini_model.generate_content_async(prompt)
        if response and response.text:
            return _parse_batch_response(response.text, len(chunks))
    except Exception as e:
        logger.error(f"Batch Gemini SDK failed: {e}")

    # Fallback: REST API
    result = await _rest_fallback(prompt, api_key)
    if result:
        return _parse_batch_response(result, len(chunks))

    return []


def _parse_batch_response(response_text: str, expected_count: int) -> list[str]:
    """Parse a batched Gemini response back into individual chunks."""
    parts = response_text.split("===CHUNK===")
    results = []
    for part in parts:
        cleaned = re.sub(r'\[\d+\]\s*', '', part).strip()
        if cleaned:
            results.append(cleaned)

    # Pad if we got fewer results than expected
    while len(results) < expected_count:
        results.append("")

    return results[:expected_count]


# --- Circuit Breaker for Rate Limits ---
import time as _time

_llm_failures = 0
_llm_circuit_open_until = 0.0
_CIRCUIT_THRESHOLD = 2      # Open after 2 consecutive failures
_CIRCUIT_COOLDOWN = 60.0    # Stay open for 60 seconds


def _is_circuit_open() -> bool:
    if _llm_failures >= _CIRCUIT_THRESHOLD:
        if _time.time() < _llm_circuit_open_until:
            return True
        # Cooldown expired — reset
        _reset_circuit()
    return False


def _record_llm_failure():
    global _llm_failures, _llm_circuit_open_until
    _llm_failures += 1
    if _llm_failures >= _CIRCUIT_THRESHOLD:
        _llm_circuit_open_until = _time.time() + _CIRCUIT_COOLDOWN
        logger.warning(f"Circuit breaker OPENED — skipping LLM for {_CIRCUIT_COOLDOWN}s")


def _record_llm_success():
    global _llm_failures, _llm_circuit_open_until
    _llm_failures = 0
    _llm_circuit_open_until = 0.0


def _reset_circuit():
    global _llm_failures, _llm_circuit_open_until
    _llm_failures = 0
    _llm_circuit_open_until = 0.0


def _ensure_gemini_configured(api_key: str):
    """Configure Gemini SDK once and cache the model instance."""
    global _gemini_configured, _gemini_model
    if not _gemini_configured or _gemini_model is None:
        genai.configure(api_key=api_key)
        _gemini_model = genai.GenerativeModel(
            "gemini-2.0-flash",
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=1024,
            ),
        )
        _gemini_configured = True
        logger.info("Gemini SDK configured (one-time init)")


async def _llm_simplify(text: str, profile: str, api_key: str) -> Optional[str]:
    """Call Gemini for text simplification with retry + backoff."""

    system_prompt = SYSTEM_PROMPTS.get(profile, SYSTEM_PROMPTS["custom"])

    prompt = f"""{system_prompt}

---
TEXT TO SIMPLIFY:
{text}
---

Provide ONLY the simplified text. Do not include any preamble, explanation, or metadata."""

    # Try the modern SDK API first (v0.3+)
    try:
        _ensure_gemini_configured(api_key)
        response = await _gemini_model.generate_content_async(prompt)
        if response and response.text:
            return response.text.strip()
    except AttributeError:
        # SDK too old for GenerativeModel — try REST fallback
        pass
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            logger.warning("Rate limited by Gemini — retrying in 1s...")
            await asyncio.sleep(1)
            try:
                response = await _gemini_model.generate_content_async(prompt)
                if response and response.text:
                    return response.text.strip()
            except Exception as retry_err:
                logger.error(f"Gemini retry also failed: {retry_err}")
                raise
        else:
            logger.error(f"Gemini SDK error: {e}")

    # Fallback: Direct REST API call (run in thread to avoid blocking event loop)
    return await _rest_fallback(prompt, api_key)


def _rest_call_sync(prompt: str, api_key: str) -> Optional[str]:
    """Synchronous REST call — meant to run in a thread via asyncio.to_thread."""
    import urllib.request
    import json

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1024,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
    return None


async def _rest_fallback(prompt: str, api_key: str) -> Optional[str]:
    """Non-blocking REST fallback using asyncio.to_thread."""
    for attempt in range(2):
        try:
            result = await asyncio.to_thread(_rest_call_sync, prompt, api_key)
            if result:
                return result
        except Exception as e:
            error_str = str(e)
            if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt == 0:
                logger.warning("REST rate limited — retrying in 1s...")
                await asyncio.sleep(1)
                continue
            logger.error(f"Gemini REST fallback failed: {e}")
            break
    return None


