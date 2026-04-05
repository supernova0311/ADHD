# NeuroUI — Neuro-Inclusive Web Interface

> AI-powered browser extension that dynamically adapts web content to reduce cognitive load for neurodivergent users (ADHD, Dyslexia, Autism).

Built for **The Big Code 2026 Hackathon** | Problem Statement #2: Neuro-Inclusive Web Interface

---

## 🧠 What is NeuroUI?

Most digital platforms are designed for neurotypical users, causing sensory overload through cluttered layouts, intrusive pop-ups, and complex language. For individuals with ADHD, Autism, or Dyslexia, these create significant barriers to learning.

**NeuroUI** introduces **'Cognitive Accessibility'** as a core metric. It's a Chrome extension backed by a Python Multi-Agent System that:

1. **Analyzes** web page content and structure in real-time
2. **Quantifies** cognitive load using our novel **Cognitive Load Score (CLS)** metric
3. **Transforms** text, visuals, and layout through profile-specific AI agents
4. **Measures** the improvement with before/after CLS scores

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│         Chrome Extension (Client)        │
│  ┌──────────┐  ┌────────┐  ┌─────────┐  │
│  │  Popup   │  │Content │  │Background│  │
│  │  (UI)    │──│ Script │──│ Worker   │  │
│  └──────────┘  └────────┘  └─────────┘  │
└────────────────────┬────────────────────┘
                     │ POST /api/process
┌────────────────────▼────────────────────┐
│         FastAPI Backend (Server)         │
│  ┌──────────────────────────────────┐   │
│  │      MAS Orchestrator            │   │
│  │  ┌────────┐ ┌────────┐ ┌──────┐ │   │
│  │  │  Text  │ │Visual  │ │Focus │ │   │
│  │  │Simplify│ │Adapter │ │Agent │ │   │
│  │  │(Gemini)│ │ (CSS)  │ │(Hide)│ │   │
│  │  └────────┘ └────────┘ └──────┘ │   │
│  └──────────────────────────────────┘   │
│  ┌──────────────────────────────────┐   │
│  │   Cognitive Metrics Engine       │   │
│  │   (textstat + spaCy + CLS)       │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Components

| Component | Technology | Purpose |
|:---|:---|:---|
| **Chrome Extension** | JavaScript, Manifest V3 | DOM extraction, user interface, transformation rendering |
| **FastAPI Backend** | Python 3.11+, FastAPI | Multi-Agent System orchestration, AI processing |
| **Text Simplifier** | Gemini 1.5 Flash + Rule-based | Profile-specific text simplification with validation |
| **Visual Adapter** | Deterministic CSS | Research-backed typography and color adjustments |
| **Focus Agent** | Regex heuristics | Ad/popup/distraction detection and removal |
| **Cognitive Metrics** | textstat + spaCy | Novel CLS algorithm (Flesch + Syntactic Load + DOM Clutter) |

---

## 🔬 Core Algorithm: Cognitive Load Score (CLS)

Our novel **Cognitive Load Score** is a composite metric in [0, 100] that quantifies how cognitively demanding web content is:

```
CLS = 0.40 × TextComplexity + 0.30 × SyntacticLoad + 0.30 × DOMClutter
```

| Component | Data Source | Research Basis |
|:---|:---|:---|
| **TextComplexity** | Flesch Reading Ease (inverted) + Coleman-Liau ensemble | Flesch (1948), validated psycholinguistic metric |
| **SyntacticLoad** | Mean Dependency Distance via spaCy parse trees | Gibson (2000) Dependency Locality Theory |
| **DOMClutter** | Node count + depth + distractor count + animation count | Harper et al. (2009) web visual complexity |

---

## 🎯 Cognitive Profiles

Each profile produces genuinely different transformations based on condition-specific research:

| Profile | Key Interventions | Research Basis |
|:---|:---|:---|
| **ADHD** | Distraction removal, animation stop, content chunking, key-point highlighting | W3C COGA Objective 5 (Help Users Focus) |
| **Dyslexia** | Increased letter/word/line spacing, sans-serif fonts, left-aligned text, max 65ch line width | NIH 2023 (spacing > specialized fonts) |
| **Autism** | Color desaturation, literal language, animation removal, consistent layout enforcement | Sensory processing research, W3C COGA Obj. 8 |

---

## 🚀 Setup & Run

### Prerequisites
- Python 3.11+
- Google Chrome
- (Optional) Gemini API key for LLM text simplification

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Download spaCy English model
python -m spacy download en_core_web_sm

# Configure API key (optional — rule-based mode works without it)
# Edit .env and add: GEMINI_API_KEY=your_key_here

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The backend will be available at `http://localhost:8000`.
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/health`

### Extension Installation

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer Mode** (toggle in top-right)
3. Click **Load Unpacked**
4. Select the `extension/` directory
5. Pin the **NeuroUI** extension to your toolbar

### Usage

1. Navigate to any text-heavy webpage (Wikipedia, news sites, documentation)
2. Click the NeuroUI extension icon
3. Select a cognitive profile (ADHD, Dyslexia, or Autism)
4. Click **Activate NeuroUI**
5. Observe the CLS score badge showing before/after improvement

---

## 🧪 Running Tests

```bash
cd backend

# Run the full evaluation suite
python -m pytest tests/test_evaluation.py -v

# Run with coverage
python -m pytest tests/test_evaluation.py -v --tb=short
```

### Test Coverage

| Test Group | Tests | What It Validates |
|:---|:---|:---|
| Cognitive Metrics | 7 tests | CLS range, ordering, component scaling |
| DOM Analyzer | 5 tests | Ad/popup/autoplay detection accuracy |
| Text Simplification | 5 tests | Readability improvement, meaning preservation |
| Visual Adaptation | 5 tests | Profile CSS generation, distinctness |
| Focus Agent | 1 test | Aggressiveness differentiation |
| Orchestrator (E2E) | 4 tests | Full pipeline validity, CLS improvement, latency |
| Edge Cases | 4 tests | Empty input, long text, missing DOM |

---

## 📚 Research References

1. **W3C COGA** — "Making Content Usable for People with Cognitive and Learning Disabilities" (W3C Working Group Note, 2021)
2. **Sweller, J.** — "Cognitive Load During Problem Solving: Effects on Learning" (Cognitive Science, 1988)
3. **Gibson, E.** — "The Dependency Locality Theory" (Cognition, 2000)
4. **Flesch, R.** — "A New Readability Yardstick" (Journal of Applied Psychology, 1948)
5. **WCAG 2.2** — Web Content Accessibility Guidelines, Success Criteria 3.2.6, 3.3.7, 3.3.8
6. **NIH (2023)** — Research on typography interventions for dyslexia (spacing > specialized fonts)
7. **Harper, S. et al.** — "Web Visual Complexity and Cognitive Load" (Web4All, 2009)

---

## 📁 Project Structure

```
ADHD/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── requirements.txt           # Python dependencies
│   ├── .env                       # API key configuration
│   ├── core/
│   │   ├── cognitive_metrics.py   # CLS algorithm (textstat + spaCy)
│   │   └── dom_analyzer.py        # DOM distractor detection
│   ├── agents/
│   │   ├── orchestrator.py        # Multi-Agent System coordinator
│   │   ├── text_simplifier.py     # Hybrid text simplification (LLM + rules)
│   │   ├── visual_adapter.py      # Profile-specific CSS generation
│   │   └── focus_agent.py         # Distraction removal agent
│   └── tests/
│       ├── test_evaluation.py     # Comprehensive test suite (31 tests)
│       └── test_corpus.json       # 20 curated test samples
├── extension/
│   ├── manifest.json              # Chrome Manifest V3
│   ├── popup.html                 # Extension UI
│   ├── popup.css                  # Premium dark-mode styles
│   ├── popup.js                   # UI controller
│   ├── content_script.js          # DOM transformation engine
│   ├── background.js              # Service worker (API bridge)
│   └── icons/                     # Extension icons
└── README.md                      # This file
```

---
.\venv\Scripts\activate; uvicorn main:app --reload --host 0.0.0.0 --port 8000
## 📄 License

MIT License — Built for The Big Code 2026 Hackathon
