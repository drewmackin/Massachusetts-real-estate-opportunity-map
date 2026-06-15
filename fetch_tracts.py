#!/usr/bin/env python3
"""
Fetch all Massachusetts census-tract boundaries (the ~1,620 sub-municipal units we
use as "neighborhoods") from Census TIGERweb as simplified GeoJSON, with POP100,
land/water area, and centroid.

Output: data/raw/ma_tracts.geojson
"""
import json
import os
import time
import urllib.parse
import urllib.request

RAW = os.path.join(os.path.dirname(__file__), "data", "raw")
OUT = os.path.join(RAW, "ma_tracts.geojson")
SVC = ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
       "tigerWMS_Census2020/MapServer/6/query")


def fetch_page(offset, count=150):
    params = {
        "where": "STATE='25'",
        "outFields": "GEOID,BASENAME,NAME,COUNTY,POP100,AREALAND,AREAWATER,INTPTLAT,INTPTLON",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": "0.0005",   # ~55 m generalization
        "geometryPrecision": "5",
        "f": "geojson",
        "resultOffset": str(offset),
        "resultRecordCount": str(count),
        "orderByFields": "GEOID",
    }
    url = SVC + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ma-re-map/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    feats = []
    offset = 0
    while True:
        for attempt in range(4):
            try:
                fc = fetch_page(offset)
                break
            except Exception as e:
                print(f"  page@{offset} attempt {attempt+1}: {e}")
                time.sleep(2 * (attempt + 1))
        else:
            raise SystemExit(f"failed at offset {offset}")
        batch = fc.get("features", [])
        if not batch:
            break
        feats.extend(batch)
        print(f"  +{len(batch)} (total {len(feats)})")
        if len(batch) < 150:
            break
        offset += 150
        time.sleep(0.3)

    # drop water-only / zero-pop tracts with no geometry
    kept = [f for f in feats if f.get("geometry") and f.get("properties", {}).get("GEOID")]
    out = {"type": "FeatureCollection", "features": kept}
    os.makedirs(RAW, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh)
    print(f"\nSaved {len(kept)} tracts -> {OUT} ({os.path.getsize(OUT)/1e6:.2f} MB)")
    g = kept[0]["properties"]
    print("sample props:", {k: g[k] for k in ("GEOID", "BASENAME", "COUNTY", "POP100")})


if __name__ == "__main__":
    main()
