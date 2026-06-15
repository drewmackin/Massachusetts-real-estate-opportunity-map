#!/usr/bin/env python3
"""
Fetch real per-town data from the U.S. Census APIs for all MA county subdivisions
(the 351 municipalities). Pure stdlib.

Outputs (keyed by 10-digit GEOID = state+county+cousub):
  data/raw/acs.json

Fields gathered (all REAL, dataQuality=measured):
  pop2022            ACS5 2022 total population
  pop2020            Decennial 2020 (P1_001N)
  pop2010            Decennial 2010 (P001001)
  pop_growth_pct     (pop2020 - pop2010)/pop2010 * 100   <- population growth criterion
  housing_units      ACS5 2022 B25001_001E
  seasonal_units     ACS5 2022 B25004_006E  (seasonal/recreational/occasional use)
  seasonal_pct       seasonal_units / housing_units * 100 <- 2nd-home demand criterion
  age25_39_pct       share of population aged 25-39        <- trendy/young-buyer proxy
  median_value       ACS5 2022 B25077_001E owner median home value (fallback price)
  median_income      ACS5 2022 B19013_001E
  median_rent        ACS5 2022 B25064_001E
"""
import json
import os
import urllib.parse
import urllib.request

RAW = os.path.join(os.path.dirname(__file__), "data", "raw")
OUT = os.path.join(RAW, "acs.json")

ACS = "https://api.census.gov/data/2022/acs/acs5"
DEC2020 = "https://api.census.gov/data/2020/dec/pl"
DEC2010 = "https://api.census.gov/data/2010/dec/sf1"

# ACS5 variables to pull in one shot
ACS_VARS = [
    "B01003_001E",  # total pop
    "B25001_001E",  # housing units
    "B25004_006E",  # seasonal/recreational/occasional
    "B25077_001E",  # median value (owner-occupied)
    "B19013_001E",  # median household income
    "B25064_001E",  # median gross rent
    # age 25-39 (male then female)
    "B01001_011E", "B01001_012E", "B01001_013E",
    "B01001_035E", "B01001_036E", "B01001_037E",
    "B01001_001E",  # age table total
]


def get(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "ma-re-map/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def rows_to_dicts(rows):
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:]]


def num(v):
    try:
        x = float(v)
        # Census uses big negative sentinels for missing
        if x < -1e6:
            return None
        return x
    except (TypeError, ValueError):
        return None


def geoid_of(d):
    return d["state"] + d["county"] + d["county subdivision"]


def main():
    data = {}

    print("Fetching ACS5 2022 (county subdivisions, all MA)...")
    acs = rows_to_dicts(get(ACS, {
        "get": "NAME," + ",".join(ACS_VARS),
        "for": "county subdivision:*",
        "in": "state:25 county:*",
    }))
    for d in acs:
        gid = geoid_of(d)
        pop = num(d["B01003_001E"])
        hu = num(d["B25001_001E"])
        seasonal = num(d["B25004_006E"])
        age_total = num(d["B01001_001E"])
        age2539 = sum(num(d[v]) or 0 for v in (
            "B01001_011E", "B01001_012E", "B01001_013E",
            "B01001_035E", "B01001_036E", "B01001_037E"))
        data[gid] = {
            "name": d["NAME"].split(",")[0],
            "pop2022": pop,
            "housing_units": hu,
            "seasonal_units": seasonal,
            "seasonal_pct": (seasonal / hu * 100) if (hu and seasonal is not None) else None,
            "age25_39_pct": (age2539 / age_total * 100) if age_total else None,
            "median_value": num(d["B25077_001E"]),
            "median_income": num(d["B19013_001E"]),
            "median_rent": num(d["B25064_001E"]),
        }
    print(f"  ACS rows: {len(acs)}")

    print("Fetching Decennial 2020 (P1_001N)...")
    dec20 = rows_to_dicts(get(DEC2020, {
        "get": "P1_001N",
        "for": "county subdivision:*",
        "in": "state:25 county:*",
    }))
    for d in dec20:
        gid = geoid_of(d)
        if gid in data:
            data[gid]["pop2020"] = num(d["P1_001N"])

    print("Fetching Decennial 2010 (P001001)...")
    dec10 = rows_to_dicts(get(DEC2010, {
        "get": "P001001",
        "for": "county subdivision:*",
        "in": "state:25 county:*",
    }))
    for d in dec10:
        gid = geoid_of(d)
        if gid in data:
            data[gid]["pop2010"] = num(d["P001001"])

    # population growth 2010->2020
    for gid, rec in data.items():
        p20, p10 = rec.get("pop2020"), rec.get("pop2010")
        rec["pop_growth_pct"] = ((p20 - p10) / p10 * 100) if (p20 and p10) else None

    os.makedirs(RAW, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(data, fh, indent=0)

    # sanity
    have_growth = sum(1 for r in data.values() if r["pop_growth_pct"] is not None)
    have_seas = sum(1 for r in data.values() if r["seasonal_pct"] is not None)
    have_val = sum(1 for r in data.values() if r["median_value"] is not None)
    print(f"\nSaved {len(data)} towns -> {OUT}")
    print(f"  with pop_growth: {have_growth}, seasonal_pct: {have_seas}, median_value: {have_val}")
    # show a couple
    for nm in ("Cambridge", "Provincetown", "Worcester"):
        for r in data.values():
            if r["name"] == nm:
                print(f"  {nm}: pop2022={r['pop2022']}, growth={r['pop_growth_pct']:.1f}% "
                      f"seasonal={r['seasonal_pct']:.1f}% age25-39={r['age25_39_pct']:.1f}% "
                      f"val={r['median_value']}")
                break


if __name__ == "__main__":
    main()
