"""Quick speed test for the backend."""
import requests
import time

BASE = "http://localhost:8000"

# Test: ADHD profile with short text (should be fast — rule-based only)
payload = {
    "chunks": ["The CEO said the company needs to think outside the box to meet deliverables."],
    "profile": "adhd"
}

print("Test 1: Short text (rule-based fast path)")
t = time.time()
r = requests.post(f"{BASE}/api/process", json=payload)
elapsed = round((time.time() - t) * 1000)
d = r.json()
print(f"  Status: {r.status_code} | Time: {elapsed}ms")
print(f"  Methods: {d['metrics'].get('methods_used')}")
print(f"  CLS: {d['cls_before']['cls']} -> {d['cls_after']['cls']}")
print()

# Test 2: Complex text (may use LLM if available)
payload2 = {
    "chunks": [
        "The epistemological ramifications of quantum decoherence necessitate a "
        "fundamental reconceptualization of the observer-measurement paradigm. "
        "Notwithstanding the substantial empirical corroboration, the proliferation "
        "of many-worlds ontological frameworks has engendered considerable "
        "philosophical consternation among practitioners."
    ],
    "profile": "adhd",
    "custom_settings": {
        "simplification_level": 2,
        "distraction_level": "high",
        "spacing_multiplier": 1.5,
        "color_mode": "warm",
        "font_size": 18,
    },
}

print("Test 2: Complex text + custom settings")
t = time.time()
r2 = requests.post(f"{BASE}/api/process", json=payload2)
elapsed2 = round((time.time() - t) * 1000)
d2 = r2.json()
print(f"  Status: {r2.status_code} | Time: {elapsed2}ms")
print(f"  Methods: {d2['metrics'].get('methods_used')}")
print(f"  CLS: {d2['cls_before']['cls']} -> {d2['cls_after']['cls']}")
print(f"  Custom CSS has warm filter: {'sepia' in d2['visual_css']}")
print(f"  Custom CSS has font-size: {'font-size' in d2['visual_css']}")
print()

print("All tests complete!")
