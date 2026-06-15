#!/usr/bin/env python3
"""Emit data/raw/qa_bundles.json — one compact review bundle per in-budget 40+ town
(numbers + curated gov form + researched prose) for the adversarial QA review workflow."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
def load(n, d=None):
    try: return json.load(open(os.path.join(DATA, n)))
    except Exception: return d
TP = {f["properties"]["geoid"]: f["properties"] for f in load("towns.geojson")["features"]}
tres = load("town_research.json", {})
hoods = {}
for f in load("neighborhoods.geojson")["features"]:
    p = f["properties"]; hoods.setdefault(p["town_geoid"], []).append(p["name"])
COUNTY = {"001":"Barnstable","003":"Berkshire","005":"Bristol","007":"Dukes","009":"Essex","011":"Franklin",
          "013":"Hampden","015":"Hampshire","017":"Middlesex","019":"Nantucket","021":"Norfolk","023":"Plymouth",
          "025":"Suffolk","027":"Worcester"}
out = []
for g, p in TP.items():
    if not (p.get("composite", 0) >= 40 and p.get("budget_fit") in ("in", "below")):
        continue
    r = tres.get(g, {})
    out.append({
        "geoid": g, "name": p.get("name"), "county": COUNTY.get(p.get("county"), ""),
        "composite": p.get("composite"), "rank": p.get("rank"), "price": p.get("price"),
        "appr5_pct": p.get("appr5"), "rentability": p.get("rentability"), "safety_est": p.get("safety"),
        "gross_yield_pct": p.get("gross_yield"), "monthly_rent": p.get("rent"),
        "gov_form": (p.get("gov") or {}).get("form"), "scores": p.get("scores"),
        "our_neighborhoods": sorted(hoods.get(g, []))[:12],
        "research": {k: r.get(k) for k in ("why", "vibe", "best_side", "schools_note",
                     "safety_note", "market_note", "confidence")} if r else None,
    })
out.sort(key=lambda b: -(b.get("composite") or 0))
p = os.path.join(DATA, "raw", "qa_bundles.json")
json.dump(out, open(p, "w"))
print(f"wrote {len(out)} town bundles -> {p}")
