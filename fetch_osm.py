#!/usr/bin/env python3
"""
Fetch named points of interest across Massachusetts from OpenStreetMap (Overpass).
Serves two purposes downstream:
  - "Cool spots" lists shown when a town is clicked (museums, parks, beaches,
    breweries, theaters, notable cafes/restaurants, historic sites, viewpoints).
  - Amenity-density inputs for the green-space/culture and trendy criteria.

A handful of grouped statewide queries (not per-town) keep this to ~3 requests.
Output: data/raw/osm_pois.json  -> [{name, lat, lon, cat}]
"""
import json
import os
import time
import urllib.parse
import urllib.request

RAW = os.path.join(os.path.dirname(__file__), "data", "raw")
OUT = os.path.join(RAW, "osm_pois.json")

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Each group: list of (overpass_filter, normalized_category)
GROUPS = {
    "attractions": [
        ('["tourism"="museum"]', "Museum"),
        ('["amenity"="theatre"]', "Theater"),
        ('["amenity"="arts_centre"]', "Arts center"),
        ('["tourism"="attraction"]', "Attraction"),
        ('["tourism"="viewpoint"]', "Scenic view"),
        ('["tourism"="gallery"]', "Gallery"),
        ('["historic"="monument"]', "Historic site"),
        ('["historic"="memorial"]', "Historic site"),
        ('["historic"="fort"]', "Historic site"),
        ('["historic"="castle"]', "Historic site"),
        ('["historic"="ruins"]', "Historic site"),
    ],
    "nature": [
        ('["leisure"="park"]', "Park"),
        ('["leisure"="nature_reserve"]', "Nature reserve"),
        ('["natural"="beach"]', "Beach"),
        ('["leisure"="garden"]["garden:type"="botanical"]', "Garden"),
        ('["leisure"="marina"]', "Marina"),
    ],
    "food": [
        ('["craft"="brewery"]', "Brewery"),
        ('["microbrewery"="yes"]', "Brewery"),
        ('["amenity"="cafe"]', "Cafe"),
        ('["amenity"="restaurant"]', "Restaurant"),
        ('["amenity"="bar"]', "Bar"),
        ('["amenity"="marketplace"]', "Market"),
    ],
}


def build_query(filters):
    parts = []
    for filt, _ in filters:
        parts.append(f'  node{filt}["name"](area.ma);')
        parts.append(f'  way{filt}["name"](area.ma);')
    body = "\n".join(parts)
    return f"""[out:json][timeout:180];
area["ISO3166-2"="US-MA"][admin_level=4]->.ma;
(
{body}
);
out center tags;"""


def run_query(q):
    last = None
    for ep in ENDPOINTS:
        for attempt in range(2):
            try:
                data = urllib.parse.urlencode({"data": q}).encode()
                req = urllib.request.Request(ep, data=data,
                                             headers={"User-Agent": "ma-re-map/1.0"})
                with urllib.request.urlopen(req, timeout=200) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                last = e
                print(f"    {ep} attempt {attempt+1} failed: {e}")
                time.sleep(5 * (attempt + 1))
    raise SystemExit(f"All Overpass endpoints failed: {last}")


def cat_for(tags, filters):
    """Pick the normalized category for an element from its tags."""
    for filt, cat in filters:
        # crude: parse key=value out of the filter and test
        kv = filt.strip("[]").replace('"', "").split("=")
        if len(kv) == 2 and tags.get(kv[0]) == kv[1]:
            return cat
    return None


def main():
    pois = []
    seen = set()
    for group, filters in GROUPS.items():
        print(f"Querying group '{group}' ({len(filters)} filters)...")
        res = run_query(build_query(filters))
        n0 = len(pois)
        for el in res.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            if el["type"] == "node":
                lat, lon = el.get("lat"), el.get("lon")
            else:
                c = el.get("center") or {}
                lat, lon = c.get("lat"), c.get("lon")
            if lat is None or lon is None:
                continue
            cat = cat_for(tags, filters) or "Spot"
            key = (round(lat, 5), round(lon, 5), name)
            if key in seen:
                continue
            seen.add(key)
            pois.append({"name": name, "lat": round(lat, 5),
                         "lon": round(lon, 5), "cat": cat})
        print(f"  +{len(pois) - n0} POIs (total {len(pois)})")
        time.sleep(2)

    with open(OUT, "w") as fh:
        json.dump(pois, fh)
    from collections import Counter
    cc = Counter(p["cat"] for p in pois)
    print(f"\nSaved {len(pois)} POIs -> {OUT}")
    print("  by category:", dict(cc.most_common()))


if __name__ == "__main__":
    main()
