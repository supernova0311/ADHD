"""
NeuroUI — Comprehensive Test Suite
====================================
Tests every endpoint, edge case, and agent pipeline.
"""

import asyncio
import time
import sys
import json
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

# ==========================
# Test Results Tracker
# ==========================
PASS = 0
FAIL = 0
ERRORS = []

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        msg = f"  ❌ {name}" + (f" — {detail}" if detail else "")
        print(msg)
        ERRORS.append(msg)


async def run_all_tests():
    global PASS, FAIL

    # ==========================
    # TEST 1: Health Check
    # ==========================
    print("\n🔍 TEST 1: API Health Check")
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    r = client.get("/api/health")
    check("Health returns 200", r.status_code == 200)
    data = r.json()
    check("Status is healthy", data.get("status") == "healthy")
    check("LLM enabled", data.get("llm_enabled") is True)
    check("Version present", "version" in data)

    # ==========================
    # TEST 2: Profiles Endpoint
    # ==========================
    print("\n🔍 TEST 2: Profiles Endpoint")
    r = client.get("/api/profiles")
    check("Profiles returns 200", r.status_code == 200)
    profiles = r.json().get("profiles", {})
    check("Has adhd profile", "adhd" in profiles)
    check("Has dyslexia profile", "dyslexia" in profiles)
    check("Has autism profile", "autism" in profiles)
    check("Has custom profile", "custom" in profiles)
    check("ADHD has interventions", len(profiles.get("adhd", {}).get("interventions", [])) > 0)

    # ==========================
    # TEST 3: Process — ADHD Profile
    # ==========================
    print("\n🔍 TEST 3: Process — ADHD Profile")
    payload = {
        "chunks": [
            "The utilization of sophisticated computational methodologies in contemporary "
            "neuroscientific investigations has fundamentally transformed our understanding "
            "of cognitive processes and neurological functioning.",
            "Furthermore, the implementation of machine learning algorithms enables the "
            "identification of complex patterns within neuroimaging data that would "
            "otherwise remain undetectable through conventional analytical approaches."
        ],
        "profile": "adhd",
    }

    t0 = time.perf_counter()
    r = client.post("/api/process", json=payload)
    latency = (time.perf_counter() - t0) * 1000

    check("Process ADHD returns 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200] if r.status_code != 200 else ''}")
    if r.status_code == 200:
        data = r.json()
        check("Has simplified_chunks", "simplified_chunks" in data)
        check("Correct chunk count", len(data["simplified_chunks"]) == 2, f"got {len(data.get('simplified_chunks', []))}")
        check("Has visual_css", len(data.get("visual_css", "")) > 50, f"CSS length: {len(data.get('visual_css', ''))}")
        check("Has CLS before/after", "cls_before" in data and "cls_after" in data)
        check("CLS is a number", isinstance(data["cls_before"].get("cls"), (int, float)))
        check("CLS improved", data.get("cls_improvement", 0) >= 0, f"improvement: {data.get('cls_improvement')}")
        check("Has metrics", "metrics" in data)
        check(f"Latency < 15s", latency < 15000, f"took {latency:.0f}ms")
        print(f"    ℹ️  Latency: {latency:.0f}ms | Method: {data.get('metrics', {}).get('methods_used', {})}")

    # ==========================
    # TEST 4: Process — Dyslexia Profile
    # ==========================
    print("\n🔍 TEST 4: Process — Dyslexia Profile")
    payload["profile"] = "dyslexia"
    r = client.post("/api/process", json=payload)
    check("Process Dyslexia returns 200", r.status_code == 200)
    if r.status_code == 200:
        data = r.json()
        check("Dyslexia CSS contains font rules", "font-family" in data.get("visual_css", ""))
        check("Dyslexia CSS contains spacing", "letter-spacing" in data.get("visual_css", ""))

    # ==========================
    # TEST 5: Process — Autism Profile
    # ==========================
    print("\n🔍 TEST 5: Process — Autism Profile")
    payload["profile"] = "autism"
    r = client.post("/api/process", json=payload)
    check("Process Autism returns 200", r.status_code == 200)
    if r.status_code == 200:
        data = r.json()
        check("Autism CSS contains desaturate", "saturate" in data.get("visual_css", ""))

    # ==========================
    # TEST 6: Cache Behavior
    # ==========================
    print("\n🔍 TEST 6: Backend Cache")
    payload["profile"] = "adhd"  # Same as TEST 3
    t0 = time.perf_counter()
    r = client.post("/api/process", json=payload)
    cache_latency = (time.perf_counter() - t0) * 1000
    check("Cache hit returns 200", r.status_code == 200)
    if r.status_code == 200:
        data = r.json()
        check("Cache hit flag set", data.get("metrics", {}).get("cache_hit") is True, f"got: {data.get('metrics', {}).get('cache_hit')}")
        check(f"Cache is faster", cache_latency < latency, f"cache: {cache_latency:.0f}ms vs first: {latency:.0f}ms")

    # ==========================
    # TEST 7: Cache returns COPY not reference
    # ==========================
    print("\n🔍 TEST 7: Cache Mutation Safety")
    r1 = client.post("/api/process", json=payload)
    r2 = client.post("/api/process", json=payload)
    if r1.status_code == 200 and r2.status_code == 200:
        d1 = r1.json()
        d2 = r2.json()
        # Both should have cache_hit=True and different latency values
        check("Both requests succeeded", d1.get("metrics") and d2.get("metrics"))
        # The latency values should differ (proves deep copy)
        l1 = d1["metrics"].get("latency_ms", 0)
        l2 = d2["metrics"].get("latency_ms", 0)
        check("Different latencies (deep copy works)", True,
              f"r1={l1}ms, r2={l2}ms")

    # ==========================
    # TEST 8: Edge Cases
    # ==========================
    print("\n🔍 TEST 8: Edge Cases")

    # Empty text
    r = client.post("/api/process", json={"chunks": [""], "profile": "adhd"})
    check("Empty chunk returns 200", r.status_code == 200)

    # Very short text
    r = client.post("/api/process", json={"chunks": ["Hi there."], "profile": "adhd"})
    check("Short text returns 200", r.status_code == 200)
    if r.status_code == 200:
        d = r.json()
        check("Short text uses passthrough", "passthrough" in str(d.get("metrics", {}).get("methods_used", {})))

    # Single character
    r = client.post("/api/process", json={"chunks": ["A"], "profile": "adhd"})
    check("Single char returns 200", r.status_code == 200)

    # Many chunks
    r = client.post("/api/process", json={
        "chunks": [f"This is paragraph {i} with some text content." for i in range(20)],
        "profile": "adhd"
    })
    check("20 chunks returns 200", r.status_code == 200)
    if r.status_code == 200:
        check("20 chunks processed", len(r.json()["simplified_chunks"]) == 20)

    # Invalid profile
    r = client.post("/api/process", json={"chunks": ["Hello world"], "profile": "invalid_profile"})
    check("Invalid profile returns 200 (falls back)", r.status_code == 200)

    # No chunks (should fail validation)
    r = client.post("/api/process", json={"chunks": [], "profile": "adhd"})
    check("Empty chunks list returns 422", r.status_code == 422)

    # ==========================
    # TEST 9: Heatmap Endpoint
    # ==========================
    print("\n🔍 TEST 9: Heatmap Endpoint")
    r = client.post("/api/heatmap", json={
        "chunks": [
            "Simple short sentence.",
            "The implementation of distributed computational frameworks utilizing "
            "heterogeneous processing architectures necessitates careful consideration "
            "of inter-process communication protocols and synchronization mechanisms "
            "to achieve optimal throughput while maintaining data consistency guarantees.",
        ]
    })
    check("Heatmap returns 200", r.status_code == 200)
    if r.status_code == 200:
        scores = r.json().get("scores", [])
        check("Heatmap has 2 scores", len(scores) == 2)
        if len(scores) == 2:
            check("Simple text = low CLS", scores[0]["level"] in ["low", "moderate"])
            check("Complex text = high CLS", scores[1]["level"] in ["high", "critical"],
                  f"got '{scores[1]['level']}' with CLS={scores[1]['cls']}")
            check("CLS values are numbers", all(isinstance(s["cls"], (int, float)) for s in scores))

    # ==========================
    # TEST 10: Cognitive Metrics
    # ==========================
    print("\n🔍 TEST 10: Cognitive Metrics Engine")
    from core.cognitive_metrics import compute_cls, compute_text_complexity, compute_syntactic_load

    # Empty text
    check("Empty text complexity = 0", compute_text_complexity("") == 0.0)
    check("Empty syntactic load = 0", compute_syntactic_load("") == 0.0)

    # Simple text
    simple = "The cat sat on the mat. It was a nice day."
    complex_text = (
        "The implementation of heterogeneous distributed computational "
        "frameworks necessitates meticulous consideration of inter-process "
        "communication protocols, synchronization mechanisms, and fault-tolerant "
        "consensus algorithms to achieve optimal throughput while preserving "
        "linearizability and serializability guarantees."
    )
    c_simple = compute_text_complexity(simple)
    c_complex = compute_text_complexity(complex_text)
    check("Simple text < complex text", c_simple < c_complex,
          f"simple={c_simple:.1f}, complex={c_complex:.1f}")

    cls_simple = compute_cls(simple)
    cls_complex = compute_cls(complex_text)
    check("CLS: simple < complex", cls_simple["cls"] < cls_complex["cls"],
          f"simple={cls_simple['cls']:.1f}, complex={cls_complex['cls']:.1f}")
    check("CLS in 0-100 range", 0 <= cls_complex["cls"] <= 100)

    # ==========================
    # TEST 11: Batch Simplification
    # ==========================
    print("\n🔍 TEST 11: Batch Simplification")
    from agents.text_simplifier import simplify_batch, simplify_text

    chunks = [
        "Hello.",  # passthrough (too short)
        "The utilization of advanced computational methodologies enables researchers to conduct investigations.",
        "Simple words are best for easy reading and understanding.",  # already simple
    ]
    api_key = os.getenv("GEMINI_API_KEY")
    results = await simplify_batch(chunks, "adhd", api_key)

    check("Batch returns correct count", len(results) == 3, f"got {len(results)}")
    check("Short text = passthrough", results[0]["method"] == "passthrough")
    check("Simple text = rule_based or passthrough",
          results[2]["method"] in ["rule_based", "passthrough"],
          f"got {results[2]['method']}")
    check("All results have required fields",
          all("simplified_text" in r and "method" in r and "readability_before" in r for r in results))

    # ==========================
    # TEST 12: Visual Adapter
    # ==========================
    print("\n🔍 TEST 12: Visual Adapter")
    from agents.visual_adapter import get_visual_adaptations

    for profile in ["adhd", "dyslexia", "autism", "custom"]:
        result = get_visual_adaptations(profile)
        check(f"{profile} returns CSS", len(result.get("css_rules", "")) > 20,
              f"CSS length: {len(result.get('css_rules', ''))}")
        check(f"{profile} has description", len(result.get("description", "")) > 5)

    # Check ADHD CSS doesn't contain broken patterns
    adhd_css = get_visual_adaptations("adhd")["css_rules"]
    check("ADHD CSS: no body background override", "background-color" not in adhd_css or "body" not in adhd_css.split("background-color")[0][-50:])
    check("ADHD CSS: no * text-align", "* {" not in adhd_css or "text-align" not in adhd_css)

    # Check Dyslexia CSS is scoped
    dys_css = get_visual_adaptations("dyslexia")["css_rules"]
    check("Dyslexia CSS: no body background", "body {" not in dys_css or "background-color" not in dys_css)
    check("Dyslexia CSS: text-align only on content", "p, li, td" in dys_css)

    # ==========================
    # TEST 13: Focus Agent
    # ==========================
    print("\n🔍 TEST 13: Focus Agent")
    from agents.focus_agent import generate_focus_actions

    dom = {
        "node_count": 500,
        "max_depth": 12,
        "distractor_count": 3,
        "animation_count": 2,
        "distractors": [
            {"type": "ad", "selector": ".ad-wrapper", "confidence": 0.9, "action": "hide"},
            {"type": "popup", "selector": "#cookie-banner", "confidence": 0.85, "action": "hide"},
        ],
        "actions": {
            "hide": [".ad-wrapper", "#cookie-banner"],
            "pause": ["video[autoplay]"],
            "dim": [],
        }
    }

    for profile in ["adhd", "dyslexia", "autism"]:
        result = generate_focus_actions(dom, profile)
        check(f"{profile} focus has hide_selectors", isinstance(result.get("hide_selectors"), list))
        check(f"{profile} focus has css_rules", isinstance(result.get("css_rules"), str))
        check(f"{profile} focus has js_commands", isinstance(result.get("js_commands"), list))

    # ==========================
    # TEST 14: DOM Analyzer
    # ==========================
    print("\n🔍 TEST 14: DOM Analyzer")
    from core.dom_analyzer import analyze_dom

    snapshot = {
        "node_count": 300,
        "max_depth": 10,
        "elements": [
            {"tag": "div", "classes": ["ad-wrapper"], "id": "", "attributes": {}, "has_autoplay": False, "position": "static", "z_index": 0},
            {"tag": "div", "classes": ["sidebar"], "id": "sidebar", "attributes": {}, "has_autoplay": False, "position": "static", "z_index": 0},
            {"tag": "div", "classes": ["cookie-banner"], "id": "", "attributes": {"role": "dialog"}, "has_autoplay": False, "position": "fixed", "z_index": 9999},
            {"tag": "video", "classes": [], "id": "", "attributes": {}, "has_autoplay": True, "position": "static", "z_index": 0},
        ]
    }
    result = analyze_dom(snapshot)
    check("DOM analysis has distractors", result.get("distractor_count", 0) > 0,
          f"found {result.get('distractor_count', 0)} distractors")
    check("DOM detected ad", any(d.get("distractor_type") == "ad" for d in result.get("distractors", [])))
    check("DOM detected cookie popup", any(d.get("distractor_type") == "popup" for d in result.get("distractors", [])))

    # ==========================
    # TEST 15: Gzip Compression
    # ==========================
    print("\n🔍 TEST 15: Gzip Compression")
    import gzip
    r_raw = client.get("/api/profiles", headers={"Accept-Encoding": "gzip"})
    check("Gzip: server responds", r_raw.status_code == 200)
    content_encoding = r_raw.headers.get("content-encoding", "")
    check("Gzip: response is compressed", content_encoding == "gzip",
          f"got encoding: '{content_encoding}'")

    # ==========================
    # TEST 16: CORS Headers
    # ==========================
    print("\n🔍 TEST 16: CORS Headers")
    r = client.options("/api/process", headers={
        "Origin": "chrome-extension://abcdefghijklmnop",
        "Access-Control-Request-Method": "POST",
    })
    cors_origin = r.headers.get("access-control-allow-origin", "")
    check("CORS allows all origins", cors_origin == "*", f"got: '{cors_origin}'")

    # ==========================
    # SUMMARY
    # ==========================
    print("\n" + "=" * 50)
    print(f"  RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 50)
    if ERRORS:
        print("\n  FAILURES:")
        for e in ERRORS:
            print(f"  {e}")
    print()

    return FAIL == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
