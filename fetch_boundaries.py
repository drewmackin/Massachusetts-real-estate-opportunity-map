#!/usr/bin/env python3
"""
Fetch all Massachusetts municipality boundaries (county subdivisions = the 351
cities/towns) from the U.S. Census TIGERweb ArcGIS REST service, as simplified
GeoJSON. Comes with POP100 (2020 pop), HU100 (housing units), land/water area,
and centroid -- which feed density (walkability), water-fraction, and distance
calculations downstream.

Pure stdlib (urllib) so no pip install is required.
Output: data/raw/ma_towns.geojson
"""
import json
import os
import time
import urllib.parse
import urllib.request

BASE = ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
        "Places_CouSub_ConCity_SubMCD/MapServer/1/query")
OUT = os.path.join(os.path.dirname(__file__), "data", "raw", "ma_towns.geojson")

# Fields we keep. INTPTLAT/LON = internal point (good label point inside polygon).
OUT_FIELDS = "NAME,BASENAME,GEOID,COUSUB,COUNTY,AREALAND,AREAWATER,INTPTLAT,INTPTLON,POP100,HU100,FUNCSTAT"


def fetch_page(offset, count=75):
    params = {
        "where": "STATE='25'",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        # Generalize geometry server-side: ~0.0007 deg ~= 75m. Keeps file light.
        "maxAllowableOffset": "0.0007",
        "geometryPrecision": "5",
        "f": "geojson",
        "resultOffset": str(offset),
        "resultRecordCount": str(count),
        "orderByFields": "GEOID",
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ma-re-map/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    features = []
    offset = 0
    while True:
        for attempt in range(4):
            try:
                fc = fetch_page(offset)
                break
            except Exception as e:
                print(f"  page@{offset} attempt {attempt+1} failed: {e}")
                time.sleep(2 * (attempt + 1))
        else:
            raise SystemExit(f"Failed to fetch page at offset {offset}")

        batch = fc.get("features", [])
        if not batch:
            break
        features.extend(batch)
        print(f"  fetched {len(batch)} (total {len(features)})")
        if len(batch) < 75:
            break
        offset += 75
        time.sleep(0.4)

    # Keep only real municipalities: FUNCSTAT 'A' (active govt) or with population.
    # Drops "County subdivisions not defined" (water) entries.
    kept = []
    for f in features:
        p = f.get("properties", {})
        name = (p.get("NAME") or "").strip()
        if not name or "not defined" in name.lower():
            continue
        if not f.get("geometry"):
            continue
        kept.append(f)

    out = {"type": "FeatureCollection", "features": kept}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh)
    size_mb = os.path.getsize(OUT) / 1e6
    print(f"\nSaved {len(kept)} municipalities -> {OUT} ({size_mb:.2f} MB)")
    # quick sanity: list a few
    sample = sorted(x["properties"]["NAME"] for x in kept)
    print("First:", sample[:3], "Last:", sample[-3:])


if __name__ == "__main__":
    main()
