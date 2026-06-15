#!/usr/bin/env python3
"""
build_research.py <workflow_results.json>

Turns a town-research Workflow result ({"results":[...]}) into the two sidecar files the
map loads: data/town_research.json (keyed by geoid) and data/neighborhoods_research.json
(keyed by "geoid|neighborhood"). Merges into any existing files so partial runs accumulate.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TOWN_KEYS = ("why", "vibe", "best_side", "schools_note", "safety_note",
             "market_note", "spots", "sources", "confidence", "name")


def real_hoods_by_town():
    out = {}
    try:
        geo = json.load(open(os.path.join(DATA, "neighborhoods.geojson")))
        for f in geo["features"]:
            p = f["properties"]; out.setdefault(p["town_geoid"], set()).add(p["name"])
    except Exception:
        pass
    return out

def best_match(name, real_names):
    """Map a research neighborhood name to our actual tract-derived name so the blurb displays."""
    if not name: return None
    if name in real_names: return name
    bylow = {r.lower(): r for r in real_names}
    if name.lower() in bylow: return bylow[name.lower()]
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    n = norm(name)
    for r in real_names:
        rn = norm(r)
        if n and rn and (n == rn or n in rn or rn in n): return r
    nt = set(re.findall(r"[a-z0-9]+", name.lower()))
    best, bs = None, 0.0
    for r in real_names:
        rt = set(re.findall(r"[a-z0-9]+", r.lower()))
        if not nt or not rt: continue
        ov = len(nt & rt) / len(nt | rt)
        if ov > bs and ov >= 0.5: bs, best = ov, r
    return best

def merge(path, new):
    cur = {}
    if os.path.exists(path):
        try: cur = json.load(open(path))
        except Exception: cur = {}
    cur.update(new)
    with open(path, "w") as f:
        json.dump(cur, f, separators=(",", ":"))
    return len(cur)


def main(path):
    raw = json.load(open(path))
    if isinstance(raw, dict) and isinstance(raw.get("result"), dict):
        raw = raw["result"]          # unwrap the workflow task envelope
    results = raw.get("results") if isinstance(raw, dict) else raw
    real = real_hoods_by_town()
    town, hood = {}, {}
    matched = unmatched = 0
    for r in results or []:
        g = r.get("geoid")
        if not g or not r.get("why"):
            continue
        town[g] = {k: r.get(k) for k in TOWN_KEYS if r.get(k) not in (None, "", [])}
        names = real.get(g, set())
        for nh in (r.get("neighborhoods") or []):
            nm = (nh.get("name") or "").strip()
            if not nm or not nh.get("blurb"): continue
            key_nm = best_match(nm, names) or nm        # remap to a real tract name where possible
            if key_nm in names: matched += 1
            else: unmatched += 1
            hood[g + "|" + key_nm] = {"blurb": nh["blurb"]}
    print(f"hood blurbs: {matched} matched to a real neighborhood, {unmatched} unmatched (won't display)")
    nt = merge(os.path.join(DATA, "town_research.json"), town)
    nh = merge(os.path.join(DATA, "neighborhoods_research.json"), hood)
    print(f"merged {len(town)} towns / {len(hood)} hoods -> "
          f"town_research.json ({nt} total), neighborhoods_research.json ({nh} total)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: build_research.py <results.json>"); sys.exit(1)
    main(sys.argv[1])
