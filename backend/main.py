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
import hashlib
import logging
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

# CORS — Restrict to Chrome extension and local development origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "chrome-extension://*",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


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
async def process_content(request: ProcessRequest):
    """
    Process web page content through the Multi-Agent System pipeline.

    Accepts text chunks and DOM metadata, returns transformation
    instructions (simplified text + CSS + JS commands) along with
    before/after Cognitive Load Scores.
    """
    try:
        t_start = time.perf_counter()
        api_key = os.getenv("GEMINI_API_KEY")

        # Check cache first
        cache_key = _make_cache_key(request.chunks, request.profile)
        if cache_key in _response_cache:
            logger.info(f"Cache HIT for key={cache_key[:8]}... profile={request.profile}")
            cached = _response_cache[cache_key]
            cached.metrics["cache_hit"] = True
            cached.metrics["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
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
