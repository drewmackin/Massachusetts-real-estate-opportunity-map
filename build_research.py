#!/usr/bin/env python3
"""
build_research.py <workflow_results.json>

Turns a town-research Workflow result ({"results":[...]}) into the two sidecar files the
map loads: data/town_research.json (keyed by geoid) and data/neighborhoods_research.json
(keyed by "geoid|neighborhood"). Merges into any existing files so partial runs accumulate.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TOWN_KEYS = ("why", "vibe", "best_side", "schools_note", "safety_note",
             "market_note", "spots", "sources", "confidence", "name")


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
    town, hood = {}, {}
    for r in results or []:
        g = r.get("geoid")
        if not g or not r.get("why"):
            continue
        town[g] = {k: r.get(k) for k in TOWN_KEYS if r.get(k) not in (None, "", [])}
        for nh in (r.get("neighborhoods") or []):
            nm = (nh.get("name") or "").strip()
            if nm and nh.get("blurb"):
                hood[g + "|" + nm] = {"blurb": nh["blurb"]}
    nt = merge(os.path.join(DATA, "town_research.json"), town)
    nh = merge(os.path.join(DATA, "neighborhoods_research.json"), hood)
    print(f"merged {len(town)} towns / {len(hood)} hoods -> "
          f"town_research.json ({nt} total), neighborhoods_research.json ({nh} total)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: build_research.py <results.json>"); sys.exit(1)
    main(sys.argv[1])
