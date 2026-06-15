#!/usr/bin/env python3
"""
Fetch 2020 and 2010 decennial population per MA municipality (keyless) from the
Census TIGERweb mapping services, and compute 10-year population growth.

  2020: TIGERweb/tigerWMS_Census2020 layer 20 (County Subdivisions) POP100, HU100
  2010: TIGERweb/tigerWMS_Census2010 layer 28 (County Subdivisions) POP100

Output: data/raw/population.json  (keyed by 10-digit GEOID)
  { GEOID: {name, pop2020, hu2020, pop2010, pop_growth_pct} }
"""
import json
import os
import urllib.parse
import urllib.request

RAW = os.path.join(os.path.dirname(__file__), "data", "raw")
OUT = os.path.join(RAW, "population.json")

SVC2020 = ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
           "tigerWMS_Census2020/MapServer/20/query")
SVC2010 = ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
           "tigerWMS_Census2010/MapServer/28/query")


def query_all(svc, fields):
    out = []
    offset = 0
    while True:
        params = {
            "where": "STATE='25'",
            "outFields": fields,
            "returnGeometry": "false",
            "f": "json",
            "resultOffset": str(offset),
            "resultRecordCount": "1000",
            "orderByFields": "GEOID",
        }
        url = svc + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "ma-re-map/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
        feats = d.get("features", [])
        if not feats:
            break
        out.extend(a["attributes"] for a in feats)
        if len(feats) < 1000:
            break
        offset += 1000
    return out


def main():
    data = {}

    print("Fetching 2020 population...")
    for a in query_all(SVC2020, "NAME,BASENAME,POP100,HU100,GEOID"):
        gid = a["GEOID"]
        data[gid] = {
            "name": a.get("BASENAME") or a.get("NAME"),
            "pop2020": a.get("POP100"),
            "hu2020": a.get("HU100"),
        }
    print(f"  2020 records: {len(data)}")

    print("Fetching 2010 population...")
    pop2010_by_gid = {}
    pop2010_by_name = {}
    for a in query_all(SVC2010, "NAME,BASENAME,POP100,GEOID"):
        gid = a["GEOID"]
        nm = a.get("BASENAME") or a.get("NAME")
        pop2010_by_gid[gid] = a.get("POP100")
        if nm:
            pop2010_by_name[nm.lower()] = a.get("POP100")
    print(f"  2010 records: {len(pop2010_by_gid)}")

    matched_gid = matched_name = 0
    for gid, rec in data.items():
        p10 = pop2010_by_gid.get(gid)
        if p10 is not None:
            matched_gid += 1
        else:
            # fall back to name match (COUSUB codes occasionally shift)
            p10 = pop2010_by_name.get((rec["name"] or "").lower())
            if p10 is not None:
                matched_name += 1
        rec["pop2010"] = p10
        p20 = rec["pop2020"]
        rec["pop_growth_pct"] = ((p20 - p10) / p10 * 100) if (p20 and p10) else None

    os.makedirs(RAW, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(data, fh, indent=0)

    have = sum(1 for r in data.values() if r["pop_growth_pct"] is not None)
    print(f"\nSaved {len(data)} towns -> {OUT}")
    print(f"  2010 matched by GEOID: {matched_gid}, by name: {matched_name}, growth computed: {have}")
    for nm in ("Cambridge", "Somerville", "Worcester", "Provincetown", "Boston"):
        for r in data.values():
            if r["name"] == nm:
                g = r["pop_growth_pct"]
                print(f"  {nm}: 2010={r['pop2010']} 2020={r['pop2020']} growth={g:.1f}%" if g is not None else f"  {nm}: n/a")
                break


if __name__ == "__main__":
    main()
