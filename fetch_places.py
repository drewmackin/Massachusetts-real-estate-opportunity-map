#!/usr/bin/env python3
"""Fetch named place points (neighbourhoods, suburbs, villages) across MA from OSM,
used to give census-tract 'neighborhoods' human-friendly names.
Output: data/raw/osm_places.json -> [{name, lat, lon, kind}]"""
import json, os, time, urllib.parse, urllib.request

RAW = os.path.join(os.path.dirname(__file__), "data", "raw")
OUT = os.path.join(RAW, "osm_places.json")
EPS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

Q = """[out:json][timeout:120];
area["ISO3166-2"="US-MA"][admin_level=4]->.ma;
( node["place"~"^(suburb|neighbourhood|quarter|borough|hamlet|village|locality|town)$"]["name"](area.ma); );
out;"""

def run(q):
    last = None
    for ep in EPS:
        for a in range(2):
            try:
                data = urllib.parse.urlencode({"data": q}).encode()
                req = urllib.request.Request(ep, data=data, headers={"User-Agent": "ma-re-map/1.0"})
                with urllib.request.urlopen(req, timeout=140) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                last = e; print(f"  {ep} retry {a+1}: {e}"); time.sleep(4)
    raise SystemExit(f"overpass failed: {last}")

def main():
    res = run(Q)
    out = []
    for el in res.get("elements", []):
        t = el.get("tags", {}); name = t.get("name")
        if not name or el.get("lat") is None:
            continue
        out.append({"name": name, "lat": round(el["lat"], 5), "lon": round(el["lon"], 5), "kind": t.get("place")})
    json.dump(out, open(OUT, "w"))
    from collections import Counter
    print(f"Saved {len(out)} places -> {OUT}")
    print("  kinds:", dict(Counter(p["kind"] for p in out)))

if __name__ == "__main__":
    main()
