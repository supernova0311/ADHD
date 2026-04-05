"""
NeuroUI Backend — FastAPI Entry Point
======================================
Exposes the Multi-Agent System (MAS) pipeline as a REST API
for the Chrome extension to consume.

Endpoint: POST /api/process
"""

from __future__ import annotations

import os
import time
import copy
import hashlib
import logging
import asyncio
from collections import defaultdict
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from agents.orchestrator import process_page

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("neuroui")

# --- Server Analytics ---
_server_start_time = time.time()
_total_requests = 0
_total_cache_hits = 0
_total_latency_ms = 0.0
_profile_usage: dict[str, int] = defaultdict(int)
_method_counts: dict[str, int] = defaultdict(int)
_rate_limited_count = 0
_overloaded_count = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("=" * 60)
    logger.info("  NeuroUI Backend Starting...")
    logger.info("=" * 60)

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        logger.info("  ✓ Gemini API key detected — LLM simplification enabled")
    else:
        logger.info("  ✗ No Gemini API key — using rule-based simplification only")
        logger.info("    Set GEMINI_API_KEY in .env to enable LLM mode")

    logger.info("=" * 60)
    yield
    logger.info("NeuroUI Backend shutting down.")


# --- FastAPI App ---
app = FastAPI(
    title="NeuroUI — Cognitive Accessibility Engine",
    description=(
        "AI-powered Multi-Agent System for dynamically adapting web content "
        "to reduce cognitive load for neurodivergent users (ADHD, Dyslexia, Autism). "
        "Implements W3C COGA guidelines via a novel Cognitive Load Score (CLS) metric."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — Allow all origins (chrome-extension://* is not a valid pattern)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# Gzip compression — 60-80% payload reduction
app.add_middleware(GZipMiddleware, minimum_size=500)


# --- Rate Limiting & Concurrency Controls ---

# Max concurrent /api/process calls (prevents memory explosion)
_PROCESS_SEMAPHORE = asyncio.Semaphore(20)

# Per-IP sliding window rate limiter
_RATE_LIMIT_WINDOW = 60       # seconds
_RATE_LIMIT_MAX_REQUESTS = 30 # max requests per window per IP
_ip_request_log: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str) -> bool:
    """Returns True if request is allowed, False if rate-limited."""
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW

    # Prune old entries
    _ip_request_log[client_ip] = [
        t for t in _ip_request_log[client_ip] if t > window_start
    ]

    if len(_ip_request_log[client_ip]) >= _RATE_LIMIT_MAX_REQUESTS:
        return False

    _ip_request_log[client_ip].append(now)
    return True


# Periodic cleanup of stale IPs (prevent memory leak)
_CLEANUP_INTERVAL = 300  # every 5 min
_last_cleanup = time.time()


def _cleanup_stale_ips():
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    window_start = now - _RATE_LIMIT_WINDOW
    stale = [ip for ip, times in _ip_request_log.items() if not times or times[-1] < window_start]
    for ip in stale:
        del _ip_request_log[ip]
    if stale:
        logger.info(f"Rate limiter cleanup: removed {len(stale)} stale IPs")


# --- Request / Response Models ---

class DOMElement(BaseModel):
    tag: str = "div"
    classes: List[str] = Field(default_factory=list)
    id: str = ""
    attributes: dict = Field(default_factory=dict)
    has_autoplay: bool = False
    position: str = ""
    z_index: int = 0


class DOMSnapshot(BaseModel):
    node_count: int = 0
    max_depth: int = 0
    elements: List[DOMElement] = Field(default_factory=list)
    url: str = ""


class CustomSettings(BaseModel):
    simplification_level: int = Field(default=2, ge=1, le=3)
    distraction_level: str = Field(default="medium")  # low, medium, high
    spacing_multiplier: float = Field(default=1.0, ge=0.5, le=3.0)
    color_mode: str = Field(default="original")  # original, muted, high_contrast, warm
    font_size: Optional[int] = None


class ProcessRequest(BaseModel):
    chunks: List[str] = Field(
        ...,
        description="Text chunks extracted from the page",
        min_length=1,
    )
    profile: str = Field(
        default="adhd",
        description="Cognitive profile: adhd, dyslexia, autism, or custom",
    )
    dom_snapshot: Optional[DOMSnapshot] = None
    custom_settings: Optional[CustomSettings] = None


class ProcessResponse(BaseModel):
    simplified_chunks: List[str]
    visual_css: str
    focus_css: str
    focus_js_commands: List[str]
    hide_selectors: List[str]
    cls_before: dict
    cls_after: dict
    cls_improvement: float
    metrics: dict


# --- Response Cache ---
# In-memory cache to avoid re-processing same content & reduce Gemini API calls
_response_cache: dict = {}
MAX_CACHE_SIZE = 100


def _make_cache_key(chunks: list, profile: str) -> str:
    """Create a deterministic cache key from request content."""
    content = f"{profile}:{'|'.join(chunks[:5])}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# --- Endpoints ---

@app.post("/api/process", response_model=ProcessResponse)
async def process_content(request: ProcessRequest, req: Request):
    """
    Process web page content through the Multi-Agent System pipeline.

    Accepts text chunks and DOM metadata, returns transformation
    instructions (simplified text + CSS + JS commands) along with
    before/after Cognitive Load Scores.
    """
    # --- Rate limit check ---
    global _total_requests, _total_cache_hits, _total_latency_ms, _rate_limited_count, _overloaded_count
    client_ip = req.client.host if req.client else "unknown"
    _cleanup_stale_ips()

    if not _check_rate_limit(client_ip):
        logger.warning(f"Rate limited: {client_ip}")
        _rate_limited_count += 1
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before retrying.",
            headers={"Retry-After": "60"},
        )

    # --- Concurrency gate ---
    if _PROCESS_SEMAPHORE.locked() and _PROCESS_SEMAPHORE._value == 0:
        # All 20 slots occupied — reject immediately instead of queuing
        logger.warning(f"Server overloaded: rejecting request from {client_ip}")
        _overloaded_count += 1
        raise HTTPException(
            status_code=503,
            detail="Server is at capacity. Please retry shortly.",
            headers={"Retry-After": "5"},
        )

    async with _PROCESS_SEMAPHORE:
        try:
            t_start = time.perf_counter()
            api_key = os.getenv("GEMINI_API_KEY")

            # Check cache first
            cache_key = _make_cache_key(request.chunks, request.profile)
            if cache_key in _response_cache:
                logger.info(f"Cache HIT for key={cache_key[:8]}... profile={request.profile}")
                cached = copy.deepcopy(_response_cache[cache_key])
                cached.metrics["cache_hit"] = True
                cached.metrics["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
                # Track analytics
                _total_requests += 1
                _total_cache_hits += 1
                _profile_usage[request.profile] += 1
                return cached

            # Convert Pydantic models to dicts for internal processing
            dom_snapshot = None
            if request.dom_snapshot:
                dom_snapshot = request.dom_snapshot.model_dump()

            custom_settings = None
            if request.custom_settings:
                custom_settings = request.custom_settings.model_dump()

            result = await process_page(
                chunks=request.chunks,
                profile=request.profile,
                dom_snapshot=dom_snapshot,
                custom_settings=custom_settings,
                api_key=api_key,
            )

            # Add latency to metrics
            latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
            result["metrics"]["latency_ms"] = latency_ms
            result["metrics"]["cache_hit"] = False
            logger.info(f"Processed in {latency_ms}ms | profile={request.profile} | chunks={len(request.chunks)}")

            # Track analytics
            _total_requests += 1
            _total_latency_ms += latency_ms
            _profile_usage[request.profile] += 1
            for method, count in result["metrics"].get("methods_used", {}).items():
                _method_counts[method] += count

            response = ProcessResponse(
                simplified_chunks=result["simplified_chunks"],
                visual_css=result["visual_css"],
                focus_css=result["focus_actions"]["css_rules"],
                focus_js_commands=result["focus_actions"]["js_commands"],
                hide_selectors=result["focus_actions"]["hide_selectors"],
                cls_before=result["cls_before"],
                cls_after=result["cls_after"],
                cls_improvement=result["cls_improvement"],
                metrics=result["metrics"],
            )

            # Store in cache (evict oldest if full)
            if len(_response_cache) >= MAX_CACHE_SIZE:
                oldest_key = next(iter(_response_cache))
                del _response_cache[oldest_key]
            _response_cache[cache_key] = response

            return response

        except HTTPException:
            raise  # Re-raise rate limit / overload errors as-is
        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Processing failed: {str(e)}"
            )


class HeatmapRequest(BaseModel):
    chunks: List[str] = Field(..., description="Text chunks to score", min_length=1)


class HeatmapScore(BaseModel):
    cls: float
    level: str  # "low", "moderate", "high", "critical"
    text_complexity: float
    syntactic_load: float
    grade_level: str


@app.post("/api/heatmap")
async def compute_heatmap(request: HeatmapRequest):
    """
    Compute per-paragraph Cognitive Load Scores for heatmap visualization.
    Returns a CLS score + severity level for each text chunk.
    """
    from core.cognitive_metrics import compute_cls

    scores = []
    for chunk in request.chunks:
        if not chunk or len(chunk.strip()) < 10:
            scores.append(HeatmapScore(
                cls=0, level="low", text_complexity=0,
                syntactic_load=0, grade_level="N/A"
            ))
            continue

        result = compute_cls(chunk)
        cls_val = result["cls"]

        # Classify severity
        if cls_val < 25:
            level = "low"
        elif cls_val < 45:
            level = "moderate"
        elif cls_val < 65:
            level = "high"
        else:
            level = "critical"

        scores.append(HeatmapScore(
            cls=cls_val,
            level=level,
            text_complexity=result["text_complexity"],
            syntactic_load=result["syntactic_load"],
            grade_level=result["grade_level"],
        ))

    return {"scores": scores}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    api_key = os.getenv("GEMINI_API_KEY")
    return {
        "status": "healthy",
        "service": "NeuroUI Backend",
        "llm_enabled": bool(api_key),
        "version": "1.2.0",
    }


@app.get("/api/stats")
async def server_stats():
    """
    Live server analytics. Useful for demo dashboards and monitoring.
    Returns request counts, cache efficiency, latency stats, and profile usage.
    """
    from agents.text_simplifier import _llm_failures, _llm_circuit_open_until
    import time as _t

    uptime_seconds = round(time.time() - _server_start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    non_cached_requests = _total_requests - _total_cache_hits
    avg_latency = round(_total_latency_ms / max(non_cached_requests, 1), 1)
    cache_hit_rate = round((_total_cache_hits / max(_total_requests, 1)) * 100, 1)

    circuit_open = _t.time() < _llm_circuit_open_until

    return {
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "uptime_seconds": uptime_seconds,
        "requests": {
            "total": _total_requests,
            "cache_hits": _total_cache_hits,
            "cache_hit_rate": f"{cache_hit_rate}%",
            "rate_limited": _rate_limited_count,
            "overloaded": _overloaded_count,
        },
        "performance": {
            "avg_latency_ms": avg_latency,
            "total_latency_ms": round(_total_latency_ms, 1),
        },
        "profiles": dict(_profile_usage),
        "methods": dict(_method_counts),
        "system": {
            "cache_size": len(_response_cache),
            "max_cache_size": MAX_CACHE_SIZE,
            "tracked_ips": len(_ip_request_log),
            "circuit_breaker": "OPEN" if circuit_open else "CLOSED",
            "llm_consecutive_failures": _llm_failures,
            "llm_enabled": bool(os.getenv("GEMINI_API_KEY")),
        },
    }


@app.get("/api/profiles")
async def list_profiles():
    """List available cognitive profiles and their descriptions."""
    return {
        "profiles": {
            "adhd": {
                "name": "ADHD Focus Mode",
                "description": "Removes distractions, chunks content, highlights key points",
                "interventions": ["distraction_removal", "text_chunking", "key_highlighting", "animation_stop"],
            },
            "dyslexia": {
                "name": "Dyslexia Reading Mode",
                "description": "Maximises spacing, readable fonts, left-aligned text",
                "interventions": ["spacing_increase", "font_adaptation", "line_width_limit", "reading_ruler"],
            },
            "autism": {
                "name": "Autism Calm Mode",
                "description": "Reduces sensory stimulation, enforces predictability, literal language",
                "interventions": ["color_desaturation", "animation_stop", "literal_language", "consistent_layout"],
            },
            "custom": {
                "name": "Custom Profile",
                "description": "User-defined settings for all parameters",
                "interventions": ["customizable"],
            },
        }
    }
