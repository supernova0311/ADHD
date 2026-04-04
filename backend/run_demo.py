"""
NeuroUI — Live Demo Test
Sends real requests to the running backend and displays results.
"""
import requests
import json

BASE = "http://localhost:8000"

# Test 1: Health check
print("=" * 60)
print("TEST 1: Health Check")
print("=" * 60)
health = requests.get(f"{BASE}/api/health").json()
print(json.dumps(health, indent=2))

# Test 2: Profiles
print("\n" + "=" * 60)
print("TEST 2: Available Profiles")
print("=" * 60)
profiles = requests.get(f"{BASE}/api/profiles").json()
for key, val in profiles["profiles"].items():
    name = val["name"]
    desc = val["description"]
    print(f"  {key:10s} | {name:25s} | {desc}")

# Test 3: ADHD profile with complex academic text + distractors
print("\n" + "=" * 60)
print("TEST 3: ADHD Profile — Complex Academic Text")
print("=" * 60)
payload = {
    "chunks": [
        "The epistemological ramifications of quantum decoherence necessitate a "
        "fundamental reconceptualization of the observer-measurement paradigm. "
        "Notwithstanding the substantial empirical corroboration of Copenhagen "
        "interpretations, the proliferation of many-worlds ontological frameworks "
        "has engendered considerable philosophical consternation among practitioners "
        "of theoretical physics.",
    ],
    "profile": "adhd",
    "dom_snapshot": {
        "node_count": 800,
        "max_depth": 12,
        "elements": [
            {"tag": "div", "classes": ["ad-wrapper"], "id": "google-ad-1", "attributes": {}},
            {"tag": "div", "classes": ["cookie-consent-banner"], "id": "",
             "attributes": {"role": "dialog"}, "position": "fixed", "z_index": 9999},
            {"tag": "video", "classes": [], "id": "hero", "attributes": {},
             "has_autoplay": True},
        ],
    },
}
resp = requests.post(f"{BASE}/api/process", json=payload)
result = resp.json()

cls_b = result["cls_before"]["cls"]
cls_a = result["cls_after"]["cls"]
imp = result["cls_improvement"]

print(f"  CLS Before:       {cls_b}")
print(f"  CLS After:        {cls_a}")
print(f"  Improvement:      {imp} points ({round(imp/max(cls_b,1)*100)}%)")
print(f"  Grade Level:      {result['cls_before']['grade_level']}")
print(f"  Reading Ease:     {result['cls_before']['reading_ease']}")
print(f"  Text Complexity:  {result['cls_before']['text_complexity']}")
print(f"  Syntactic Load:   {result['cls_before']['syntactic_load']}")
print(f"  DOM Clutter:      {result['cls_before']['dom_clutter']}")
print(f"  Distractors:      {result['metrics']['distractors_detected']}")
print(f"  Elements Removed: {result['metrics']['elements_removed']}")
print(f"  Methods Used:     {result['metrics']['methods_used']}")
print(f"  Hide Selectors:   {result['hide_selectors']}")
print()
print("  ORIGINAL:")
print(f"  {payload['chunks'][0][:200]}...")
print()
print("  SIMPLIFIED:")
print(f"  {result['simplified_chunks'][0][:200]}...")

# Test 4: Dyslexia profile — check CSS output
print("\n" + "=" * 60)
print("TEST 4: Dyslexia Profile — CSS Verification")
print("=" * 60)
payload2 = {
    "chunks": ["Reading is difficult when text is too small and closely spaced."],
    "profile": "dyslexia",
}
resp2 = requests.post(f"{BASE}/api/process", json=payload2)
r2 = resp2.json()
css = r2["visual_css"]
checks = {
    "letter-spacing": "letter-spacing" in css,
    "word-spacing": "word-spacing" in css,
    "line-height: 1.8": "line-height: 1.8" in css,
    "text-align: left": "text-align: left" in css,
    "max-width: 65ch": "max-width: 65ch" in css,
}
for feature, present in checks.items():
    status = "✓" if present else "✗"
    print(f"  {status} {feature}")

# Test 5: Autism profile — check CSS has desaturation
print("\n" + "=" * 60)
print("TEST 5: Autism Profile — Sensory Reduction Check")
print("=" * 60)
payload3 = {
    "chunks": ["The brightly flashing neon signs illuminated the bustling street."],
    "profile": "autism",
}
resp3 = requests.post(f"{BASE}/api/process", json=payload3)
r3 = resp3.json()
css3 = r3["visual_css"]
checks3 = {
    "saturate(60%)": "saturate(60%)" in css3,
    "animation: none": "animation: none" in css3,
    "background-image: none": "background-image: none" in css3,
}
for feature, present in checks3.items():
    status = "✓" if present else "✗"
    print(f"  {status} {feature}")

# Test 6: Profile differentiation
print("\n" + "=" * 60)
print("TEST 6: Profile Differentiation")
print("=" * 60)
text = "The CEO said the company needs to think outside the box."
results = {}
for profile in ["adhd", "dyslexia", "autism"]:
    p = {"chunks": [text], "profile": profile}
    r = requests.post(f"{BASE}/api/process", json=p).json()
    results[profile] = r["visual_css"][:100]

all_different = (results["adhd"] != results["dyslexia"] and
                 results["dyslexia"] != results["autism"] and
                 results["adhd"] != results["autism"])
print(f"  All profiles produce distinct CSS: {'✓ YES' if all_different else '✗ NO'}")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE ✓")
print("=" * 60)
