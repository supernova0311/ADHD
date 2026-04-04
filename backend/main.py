"""
NeuroUI Backend — FastAPI Entry Point
======================================
Exposes the Multi-Agent System (MAS) pipeline as a REST API
for the Chrome extension to consume.

Endpoint: POST /api/process
"""

from __future__ import annotations

import os
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

# CORS — Allow Chrome extension origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to chrome-extension:// origins
    allow_credentials=True,
    allow_methods=["*"],
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
        api_key = os.getenv("GEMINI_API_KEY")

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

        return ProcessResponse(
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

    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    api_key = os.getenv("GEMINI_API_KEY")
    return {
        "status": "healthy",
        "service": "NeuroUI Backend",
        "llm_enabled": bool(api_key),
        "version": "1.0.0",
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
