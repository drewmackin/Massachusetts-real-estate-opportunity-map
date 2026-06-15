#!/usr/bin/env python3
"""
Scoring engine for the MA Real-Estate Opportunity Map.

Joins all sources, normalizes each of the user's 10 criteria to 0-100 across the
351 towns, applies the appreciation-tilt weights, computes a composite score +
rank + budget-fit, attaches "cool spots", and generates 10 buy / 10 don't-buy
reasons grounded in real metric values.

Inputs (data/raw/): ma_towns.geojson, population.json, zillow_city_zhvi.csv,
transit.json, osm_pois.json  +  curated.py
Output: data/towns.geojson  (geometry + all computed properties; map loads this)
"""
import csv
import json
import math
import os
import urllib.parse
import urllib.request
from collections import defaultdict

import curated

# MassGIS parcels (for filling town prices Zillow doesn't cover, via assessed value)
PARCEL_URL = ("https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/"
              "AGOL/L3_Parcels_FeatureService_4326/FeatureServer/1/query")

HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "data", "raw")
OUT = os.path.join(HERE, "data", "towns.geojson")

BUDGET_LO, BUDGET_HI = 400_000, 600_000

# Appreciation-tilt weights (sum=100) -- forward-looking factors heaviest.
WEIGHTS = {
    "transit": 16,
    "population_growth": 14,
    "employer": 13,
    "schools": 12,
    "trendy": 11,
    "universities": 9,
    "walkability": 8,
    "second_home": 7,
    "water_beach": 5,
    "green_culture": 5,
}
CRIT_LABEL = {
    "transit": "Rail transit access & expansion",
    "population_growth": "Population growth / in-migration",
    "employer": "Major-employer expansion nearby",
    "schools": "School quality & trend",
    "trendy": "Trendy / young-buyer demand",
    "universities": "Proximity to top universities",
    "walkability": "Walkability",
    "second_home": "Vacation / second-home demand",
    "water_beach": "Water frontage & beach access",
    "green_culture": "Green space & local culture",
}
CRIT_QUALITY = {
    "transit": "measured",        # MBTA GTFS stations (+curated expansion flag)
    "population_growth": "measured",  # decennial census
    "employer": "curated",
    "schools": "curated",
    "trendy": "proxy",
    "universities": "measured",   # distance to curated university list
    "walkability": "proxy",       # population density
    "second_home": "proxy",       # vacation region + coastal
    "water_beach": "measured",    # census water area + OSM beaches (+curated tier)
    "green_culture": "measured",  # OSM parks/museums/theaters
}

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def norm_name(s):
    if not s:
        return ""
    s = s.lower().strip()
    for suf in (" town", " city"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    s = s.replace("-by-the-sea", "").replace("borough of ", "")
    s = s.replace(".", "").replace("'", "").strip()
    return s

ALIAS = {  # normalized -> canonical normalized used in our keys
    "manchester by the sea": "manchester",
}

def key_of(name):
    n = norm_name(name)
    return ALIAS.get(n, n)


def zfind(zillow, k):
    """Look up a town in Zillow data, tolerating the -borough/-boro spelling
    difference Zillow uses for several MA towns (e.g. North Attleborough)."""
    if k in zillow:
        return zillow[k]
    if k.endswith("borough"):
        alt = k[:-7] + "boro"
        if alt in zillow:
            return zillow[alt]
    return {}


def fetch_town_median_value(geom, bbox):
    """Median residential assessed value for a town from MassGIS parcels — used to
    fill a real price for the few tiny towns Zillow doesn't cover (MA assesses at
    full market value, so this approximates a market median). Returns None on failure."""
    params = {
        "geometry": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "geometryType": "esriGeometryEnvelope", "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "TOTAL_VAL,BLD_AREA", "returnGeometry": "true",
        "resultRecordCount": "2000", "f": "geojson",
    }
    url = PARCEL_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ma-re-map/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        geo = json.loads(r.read().decode("utf-8"))
    vals = []
    for ft in geo.get("features", []):
        pr = ft.get("properties", {})
        g = ft.get("geometry")
        v = pr.get("TOTAL_VAL")
        area = pr.get("BLD_AREA") or 0
        if not g or not v or v < 50_000 or v > 3_000_000 or area < 400:
            continue
        # representative point = first vertex of first ring, must fall in the town
        try:
            ring = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
            px, py = ring[0][0], ring[0][1]
        except (KeyError, IndexError, TypeError):
            continue
        if point_in_geom(geom, px, py):
            vals.append(v)
    if len(vals) < 3:
        return None
    vals.sort()
    return float(vals[len(vals) // 2])


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def pct_ranks(values):
    """Map each value -> percentile 0..100 (None stays None)."""
    present = sorted(v for v in values if v is not None)
    n = len(present)
    out = []
    if n <= 1:
        return [50.0 if v is not None else None for v in values]
    # rank by count strictly-less (ties share lower rank), average for fairness
    import bisect
    for v in values:
        if v is None:
            out.append(None)
            continue
        lo = bisect.bisect_left(present, v)
        hi = bisect.bisect_right(present, v)
        rank = (lo + hi - 1) / 2.0
        out.append(rank / (n - 1) * 100.0)
    return out


def ring_contains(ring, x, y):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def polygons_of(geom):
    """Yield lists of rings (outer first, then holes) for Polygon/MultiPolygon."""
    if geom["type"] == "Polygon":
        yield geom["coordinates"]
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            yield poly


def point_in_geom(geom, x, y):
    for poly in polygons_of(geom):
        if not poly:
            continue
        if ring_contains(poly[0], x, y):
            in_hole = any(ring_contains(h, x, y) for h in poly[1:])
            if not in_hole:
                return True
    return False


def bbox_of(geom):
    xs, ys = [], []
    for poly in polygons_of(geom):
        for ring in poly:
            for xx, yy in ring:
                xs.append(xx)
                ys.append(yy)
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# load sources
# ---------------------------------------------------------------------------

def load_zillow():
    """Return {norm_name: {price, appr5, mom3}} from MA Zillow rows."""
    path = os.path.join(RAW, "zillow_city_zhvi.csv")
    out = {}
    with open(path, newline="") as f:
        rd = csv.reader(f)
        header = next(rd)
        date_cols = [(i, c) for i, c in enumerate(header) if c[:2] == "20" and "-" in c]
        idx_name = header.index("RegionName")
        idx_state = header.index("State")
        for row in rd:
            if row[idx_state] != "MA":
                continue
            # series of (date, value)
            series = []
            for i, c in date_cols:
                v = row[i].strip()
                if v:
                    try:
                        series.append((c, float(v)))
                    except ValueError:
                        pass
            if not series:
                continue
            price = series[-1][1]
            def val_n_months_ago(n):
                if len(series) > n:
                    return series[-1 - n][1]
                return series[0][1]
            p60 = val_n_months_ago(60)
            p36 = val_n_months_ago(36)
            appr5 = (price / p60 - 1) * 100 if p60 else None
            mom3 = (price / p36 - 1) * 100 if p36 else None
            out[key_of(row[idx_name])] = {"price": price, "appr5": appr5, "mom3": mom3}
    return out


def load_zori():
    """Return {norm_name: {rent, rent_growth3}} from MA Zillow Observed Rent Index
    (ZORI) rows — typical monthly asking rent (all homes, smoothed)."""
    path = os.path.join(RAW, "zillow_city_zori.csv")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="") as f:
        rd = csv.reader(f)
        header = next(rd)
        date_cols = [i for i, c in enumerate(header) if c[:2] == "20" and "-" in c]
        idx_name = header.index("RegionName")
        idx_state = header.index("State")
        for row in rd:
            if row[idx_state] != "MA":
                continue
            series = []
            for i in date_cols:
                v = row[i].strip()
                if v:
                    try:
                        series.append(float(v))
                    except ValueError:
                        pass
            if not series:
                continue
            rent = series[-1]
            # only a TRUE 36-month-ago point counts as 3-yr growth; a short ZORI
            # series (many smaller MA towns) leaves it None -> backfilled from the
            # county/state median below, so we never label a 0-1 month move as "3yr".
            r36 = series[-37] if len(series) >= 37 else None
            growth3 = (rent / r36 - 1) * 100 if r36 else None
            out[key_of(row[idx_name])] = {"rent": rent, "rent_growth3": growth3}
    return out


def round_coords(obj, nd=5):
    """Round all coordinates in a GeoJSON geometry in place (~1 m at 5 dp) to shrink
    the file. Returns the same object for convenience."""
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, list):
        return [round_coords(x, nd) for x in obj]
    return obj


def compute_rentability(towns):
    """Landlord view per town. Two outputs (0-100 percentile):
      rentability  = how attractive to rent out NOW   (gross yield + rental demand)
      rent_future  = forward rent outlook (next ~5 yrs) (rent growth + demand + catalysts)
    Also fills a real/estimated monthly rent (ZORI) and gross yield for display."""
    zori = load_zori()
    for t in towns:
        zr = zfind(zori, t["key"]) or {}
        t["rent"] = zr.get("rent")
        t["rent_growth3"] = zr.get("rent_growth3")
        t["rent_est"] = None

    # gross yield = annual rent / price (%), where both are known
    for t in towns:
        if t.get("rent") and t.get("price"):
            t["gross_yield"] = t["rent"] * 12 / t["price"] * 100
        else:
            t["gross_yield"] = None

    # fill missing rent from county- (else state-) median yield applied to the price
    def cmed(by, c):
        vals = sorted(v for v in by.get(c, []) if v is not None)
        return vals[len(vals) // 2] if vals else None
    yc = defaultdict(list)
    ally = []
    for t in towns:
        if t["gross_yield"] is not None:
            yc[t["county"]].append(t["gross_yield"])
            ally.append(t["gross_yield"])
    state_yield = sorted(ally)[len(ally) // 2] if ally else 5.0
    rgc = defaultdict(list)
    allg = []
    for t in towns:
        if t["rent_growth3"] is not None:
            rgc[t["county"]].append(t["rent_growth3"])
            allg.append(t["rent_growth3"])
    state_rg = sorted(allg)[len(allg) // 2] if allg else 0.0
    for t in towns:
        if t["gross_yield"] is None and t.get("price"):
            gy = cmed(yc, t["county"]) or state_yield
            t["gross_yield"] = gy
            t["rent"] = round(gy / 100 * t["price"] / 12)
            t["rent_est"] = "est."
        if t["rent_growth3"] is None:
            t["rent_growth3"] = cmed(rgc, t["county"]) or state_rg
            t["rent_growth3_est"] = True   # borrowed county/state median, not measured

    # percentile inputs
    p_yield = pct_ranks([t.get("gross_yield") for t in towns])
    p_rg = pct_ranks([t.get("rent_growth3") for t in towns])
    p_dens = pct_ranks([t["density"] for t in towns])
    p_uni = pct_ranks([-t["nearest_uni_mi"] for t in towns])
    p_grow = pct_ranks([t["pop_growth"] for t in towns])
    p_price = pct_ranks([t["price"] for t in towns])

    def g(a, i, d=40):
        return a[i] if a[i] is not None else d

    rent_now_raw, rent_fut_raw = [], []
    for i, t in enumerate(towns):
        sc = t["scores"]
        tr = t["transit"]
        rail = 100 if (tr and (tr["has_commuter_rail"] or tr["has_subway"] or tr["has_lightrail"])) else 30
        emp = {3: 100, 2: 75, 1: 55}.get(curated.EMPLOYER.get(t["name"], 0), 30)
        # rental demand: who will rent it & support rent growth
        demand = (0.22 * g(p_uni, i) + 0.22 * g(p_dens, i) + 0.18 * sc["transit"]
                  + 0.16 * sc["trendy"] + 0.12 * g(p_grow, i, 50) + 0.10 * emp)
        t["rent_demand"] = round(demand, 1)
        # NOW: cash-flow yield + ability to keep it rented
        rent_now_raw.append(0.50 * g(p_yield, i, 50) + 0.50 * demand)
        # FUTURE: rent growth momentum + demand + new-transit catalyst + headroom
        catalyst = 100 if curated.TRANSIT_EXPANSION.get(t["name"]) else rail
        headroom = 100 - g(p_price, i, 50)
        rent_fut_raw.append(0.30 * g(p_rg, i, 50) + 0.27 * demand + 0.18 * catalyst
                            + 0.15 * g(p_grow, i, 50) + 0.10 * headroom)
    fn = pct_ranks(rent_now_raw)
    ff = pct_ranks(rent_fut_raw)
    for i, t in enumerate(towns):
        t["rentability"] = round(fn[i] if fn[i] is not None else 50.0, 1)
        t["rent_future"] = round(ff[i] if ff[i] is not None else 50.0, 1)


def compute_future_towns(towns):
    """Forward-looking 'future potential' score per town (0-100 percentile): rewards
    NEW transit catalysts, affordability headroom, walkability, town demand growth &
    universities; penalizes places that already spiked (mean reversion). Not past price."""
    p_price = pct_ranks([t["price"] for t in towns])
    p_dens = pct_ranks([t["density"] for t in towns])
    p_grow = pct_ranks([t["pop_growth"] for t in towns])
    p_uni = pct_ranks([-t["nearest_uni_mi"] for t in towns])
    p_water = pct_ranks([t["water_frac"] for t in towns])
    raw = []
    for i, t in enumerate(towns):
        exp = 100 if curated.TRANSIT_EXPANSION.get(t["name"]) else 0
        emp = {0: 25, 1: 55, 2: 80, 3: 100}.get(curated.EMPLOYER.get(t["name"], 0), 25)
        tr = t["transit"]
        rail = 100 if (tr and (tr["has_commuter_rail"] or tr["has_subway"] or tr["has_lightrail"])) else 30
        catalyst = 0.62 * exp + 0.38 * rail
        afford = 100 - (p_price[i] if p_price[i] is not None else 50)   # cheaper = more runway
        walk = p_dens[i] if p_dens[i] is not None else 30
        demand = 0.55 * (p_grow[i] if p_grow[i] is not None else 50) + 0.45 * emp
        univ = p_uni[i] if p_uni[i] is not None else 30
        watergreen = p_water[i] if p_water[i] is not None else 30
        a5 = t["appr5"] or 0
        mr = max(0, (a5 - 65) / 3.5) if a5 > 65 else 0
        raw.append(0.26 * catalyst + 0.22 * afford + 0.18 * walk + 0.16 * demand
                   + 0.10 * univ + 0.08 * watergreen - mr)
    fp = pct_ranks(raw)
    for i, t in enumerate(towns):
        t["future"] = round(fp[i] if fp[i] is not None else 50.0, 1)


def augment_neighborhoods(towns):
    """Add a forward-looking 'future' score to each neighborhood (same thesis as the
    town score but at tract granularity), then rewrite data/neighborhoods.geojson."""
    path = os.path.join(HERE, "data", "neighborhoods.geojson")
    if not os.path.exists(path):
        return
    geo = json.load(open(path))
    feats = geo["features"]
    tw_by = {t["gid"]: t for t in towns}

    def s(v, d):
        return v if v is not None else d
    prox = [math.exp(-s(f["properties"].get("station_mi"), 6) / 1.5) for f in feats]
    dens = [f["properties"].get("density") for f in feats]
    uni = [-(f["properties"].get("uni_mi") or 30) for f in feats]
    price = [(tw_by.get(f["properties"]["town_geoid"]) or {}).get("price") for f in feats]
    grow = [(tw_by.get(f["properties"]["town_geoid"]) or {}).get("pop_growth") for f in feats]
    fprox, fdens, funi, fprice, fgrow = (pct_ranks(prox), pct_ranks(dens), pct_ranks(uni),
                                         pct_ranks(price), pct_ranks(grow))
    raw = []
    for i, f in enumerate(feats):
        p = f["properties"]
        tw = tw_by.get(p["town_geoid"]) or {}
        exp = 100 if curated.TRANSIT_EXPANSION.get(tw.get("name")) else 0
        emp = {0: 20, 1: 55, 2: 80, 3: 100}.get(curated.EMPLOYER.get(tw.get("name"), 0), 20)
        pr = fprox[i] if fprox[i] is not None else 30
        de = fdens[i] if fdens[i] is not None else 30
        un = funi[i] if funi[i] is not None else 30
        pp = fprice[i] if fprice[i] is not None else 50
        gr = fgrow[i] if fgrow[i] is not None else 50
        catalyst = 0.6 * exp + 0.4 * pr
        afford = 100 - pp
        fund = (pr + de + un) / 3
        valuegap = max(0, fund - pp)
        demand = 0.6 * gr + 0.4 * emp
        a5 = p.get("appr5") or 0
        mr = max(0, (a5 - 70) / 4) if a5 > 70 else 0
        raw.append(0.26 * catalyst + 0.22 * afford + 0.16 * de + 0.14 * valuegap
                   + 0.12 * demand + 0.10 * un - mr)
    fp = pct_ranks(raw)

    # ---- per-NEIGHBORHOOD rent insight (rent varies block to block within a town) ----
    # rent pressure = transit access + walkable density + university pull + appreciation.
    fappr = pct_ranks([f["properties"].get("appr5") for f in feats])
    pressure = []
    for i in range(len(feats)):
        pr = fprox[i] if fprox[i] is not None else 30
        de = fdens[i] if fdens[i] is not None else 30
        un = funi[i] if funi[i] is not None else 30
        ap = fappr[i] if fappr[i] is not None else 50
        pressure.append(0.34 * pr + 0.26 * de + 0.20 * un + 0.20 * ap)
    # within-town percentile of that pressure -> a rent multiplier around the town's rent
    by_town = defaultdict(list)
    for i, f in enumerate(feats):
        by_town[f["properties"]["town_geoid"]].append(i)
    within = [0.5] * len(feats)
    for idxs in by_town.values():
        if len(idxs) > 1:
            order = sorted(idxs, key=lambda j: pressure[j])
            for rank, j in enumerate(order):
                within[j] = rank / (len(order) - 1)
    for i, f in enumerate(feats):
        p = f["properties"]
        tw = tw_by.get(p["town_geoid"]) or {}
        trent = tw.get("rent")
        factor = max(0.7, min(1.35, 1.0 + 0.5 * (within[i] - 0.5)))   # ~ -15% .. +18%
        p["rent_est"] = int(round(trent * factor / 10) * 10) if trent else None
        p["rent_vs_town"] = round((factor - 1) * 100)
        pr = fprox[i] if fprox[i] is not None else 30
        de = fdens[i] if fdens[i] is not None else 30
        un = funi[i] if funi[i] is not None else 30
        ap = fappr[i] if fappr[i] is not None else 50
        emp = {0: 20, 1: 55, 2: 80, 3: 100}.get(curated.EMPLOYER.get(tw.get("name"), 0), 20)
        p["rent_demand"] = round(0.30 * pr + 0.22 * un + 0.22 * de + 0.16 * ap + 0.10 * emp, 1)
        umi, smi, dens = p.get("uni_mi"), p.get("station_mi"), (p.get("density") or 0)
        if umi is not None and umi <= 1.6 and p.get("uni_nm"):
            p["renter_profile"] = f"Students & young renters — {p['uni_nm']} is {umi} mi"
        elif smi is not None and smi <= 1.0 and dens >= 3000:
            p["renter_profile"] = "Young professionals & transit commuters"
        elif dens and dens < 1600:
            p["renter_profile"] = "Families & long-term tenants — quieter, residential"
        else:
            p["renter_profile"] = "A mix of young renters & families"

    import bisect
    def clamp(v, lo=0, hi=100): return max(lo, min(hi, v))
    # within-town neighborhood opportunity ranking, so the safety ESTIMATE can vary by area
    town_scores = {g: sorted(feats[j]["properties"].get("score") or 50 for j in idxs)
                   for g, idxs in by_town.items()}
    for i, f in enumerate(feats):
        p = f["properties"]
        tw = tw_by.get(p["town_geoid"]) or {}
        p["future"] = round(fp[i] if fp[i] is not None else 50.0, 1)
        # enrich the sub-town subscores with town-level context dimensions for the "which side" lens.
        # schools = curated district tier; safety = a transparent PROXY (NOT reported crime data,
        # which isn't openly available sub-town) — both are town-level so they read flat within a town.
        schools = (tw.get("scores") or {}).get("schools", 60)
        ts = town_scores.get(p["town_geoid"]) or []
        mysc = p.get("score") or 50
        if len(ts) > 1:                                  # neighborhood's within-town desirability percentile
            lo = bisect.bisect_left(ts, mysc); hi = bisect.bisect_right(ts, mysc)
            pos = (lo + hi) / 2.0 / len(ts)
        else:
            pos = 0.5
        sub = p.get("sub") or {}
        sub["schools"] = round(schools)                  # schools/district is genuinely town-level
        # safety estimate: town baseline shifted ±14 by the area's relative desirability (proxy, labeled)
        sub["safety"] = round(clamp((tw.get("safety") or 50) + (pos - 0.5) * 28))
        sub["rent"] = round(p.get("rent_demand") or 50)
        sub["opp"] = round(p.get("score") or 50)
        p["sub"] = sub
        g = f.get("geometry")
        if g and "coordinates" in g:
            g["coordinates"] = round_coords(g["coordinates"])
    with open(path, "w") as fh:
        json.dump(geo, fh, separators=(",", ":"))
    print(f"  added future + rent insight + sub-town subscores to {len(feats)} neighborhoods")


def main():
    geo = json.load(open(os.path.join(RAW, "ma_towns.geojson")))
    pop = json.load(open(os.path.join(RAW, "population.json")))
    transit = json.load(open(os.path.join(RAW, "transit.json")))
    osm_path = os.path.join(RAW, "osm_pois.json")
    if os.path.exists(osm_path) and os.path.getsize(osm_path) > 2:
        pois = json.load(open(osm_path))
    else:
        print("  WARNING: osm_pois.json missing/empty -> cool spots & OSM amenities degraded")
        pois = []
    zillow = load_zillow()

    pop_by_gid = pop  # already keyed by GEOID
    # name fallback: a few city-form municipalities (Watertown, Methuen, Amesbury,
    # Easthampton) carry their 2020 population under a GEOID that differs from the
    # boundary file's, so the GEOID join misses them -> recover by normalized name.
    pop_by_name = {}
    for rec in pop.values():
        nm = rec.get("name")
        if nm and rec.get("pop2020") is not None:
            pop_by_name.setdefault(key_of(nm), rec)
    transit_by_key = {key_of(k): v for k, v in transit.items()}

    feats = geo["features"]
    # ---- base attributes per town ----
    towns = []
    for f in feats:
        p = f["properties"]
        gid = p["GEOID"]
        name = (p.get("BASENAME") or p.get("NAME") or "").replace(" Town", "").strip()
        k = key_of(name)
        land_m2 = float(p["AREALAND"]) if p.get("AREALAND") else 0.0
        water_m2 = float(p["AREAWATER"]) if p.get("AREAWATER") else 0.0
        land_sqmi = land_m2 / 2_589_988.0
        clat = float(p["INTPTLAT"])
        clon = float(p["INTPTLON"])
        pr = pop_by_gid.get(gid) or {}
        if pr.get("pop2020") is None:
            alt = pop_by_name.get(k)
            if alt and alt.get("pop2020") is not None:
                pr = alt
        pop2020 = pr.get("pop2020")
        density = (pop2020 / land_sqmi) if (pop2020 and land_sqmi > 0.05) else None
        water_frac = water_m2 / (land_m2 + water_m2) if (land_m2 + water_m2) else 0.0
        z = zfind(zillow, k)
        towns.append({
            "f": f, "gid": gid, "name": name, "key": k,
            "county": p.get("COUNTY"), "clat": clat, "clon": clon,
            "land_sqmi": land_sqmi, "water_frac": water_frac,
            "pop2020": pop2020, "pop_growth": pr.get("pop_growth_pct"),
            "density": density,
            "price": z.get("price"), "appr5": z.get("appr5"), "mom3": z.get("mom3"),
            "transit": transit_by_key.get(k),
            "bbox": bbox_of(f["geometry"]),
            "pois": [],
        })

    # validate transit: only count stations actually near the town. Fixes cross-state name
    # collisions (e.g. MA "Warwick" inheriting Rhode Island Warwick's TF Green Airport station).
    def _mi(la1, lo1, la2, lo2):
        R = 3958.8; p1, p2 = math.radians(la1), math.radians(la2)
        dp = math.radians(la2 - la1); dl = math.radians(lo2 - lo1)
        a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2 * R * math.asin(math.sqrt(a))
    for t in towns:
        tr = t.get("transit")
        if not tr or not tr.get("stations"):
            continue
        near = [s for s in tr["stations"] if _mi(t["clat"], t["clon"], s["lat"], s["lon"]) <= 12]
        if len(near) == len(tr["stations"]):
            continue
        if not near:
            t["transit"] = None
        else:
            modes = set()
            for s in near:
                modes.update(s.get("modes", []))
            low = " ".join(modes).lower()
            t["transit"] = {"has_subway": "subway" in low, "has_lightrail": "light" in low,
                            "has_commuter_rail": "commuter" in low, "station_count": len(near),
                            "modes": sorted(modes), "stations": near}

    # ---- assign POIs to towns (bbox prefilter + point-in-polygon) ----
    for poi in pois:
        x, y = poi["lon"], poi["lat"]
        for t in towns:
            bx0, by0, bx1, by1 = t["bbox"]
            if bx0 <= x <= bx1 and by0 <= y <= by1:
                if point_in_geom(t["f"]["geometry"], x, y):
                    t["pois"].append(poi)
                    break

    # ---- university proximity score ----
    unis = curated.university_list()
    for t in towns:
        s = 0.0
        nearest = None
        nd = 1e9
        within10 = 0
        for (un, ula, ulo, draw) in unis:
            d = haversine_km(t["clat"], t["clon"], ula, ulo)
            s += draw * math.exp(-d / 12.0)
            if d <= 16.1:  # ~10 mi
                within10 += 1
            if d < nd:
                nd, nearest = d, un
        t["uni_raw"] = s
        t["nearest_uni"] = nearest
        t["nearest_uni_mi"] = nd * 0.621371
        t["uni_within10"] = within10

    # ---- POI category counts ----
    for t in towns:
        cc = {}
        for poi in t["pois"]:
            cc[poi["cat"]] = cc.get(poi["cat"], 0) + 1
        t["poi_counts"] = cc
        green = cc.get("Park", 0) + cc.get("Nature reserve", 0) + cc.get("Garden", 0)
        culture = (cc.get("Museum", 0) + cc.get("Theater", 0) +
                   cc.get("Arts center", 0) + cc.get("Gallery", 0))
        food = cc.get("Cafe", 0) + cc.get("Brewery", 0) + cc.get("Restaurant", 0) + cc.get("Bar", 0)
        t["green_n"] = green
        t["culture_n"] = culture
        t["food_n"] = food
        # per-capita food density; None (not /1) when population is unknown so it
        # is excluded from the percentile rank instead of spiking the trendy score
        t["food_density"] = (food / t["pop2020"] * 1000.0) if t["pop2020"] else None
        t["beach_n"] = cc.get("Beach", 0)

    # ---- transit raw ----
    for t in towns:
        tr = t["transit"]
        raw = 0.0
        if tr:
            if tr["has_subway"]:
                raw += 2.2
            if tr["has_lightrail"]:
                raw += 1.7
            if tr["has_commuter_rail"]:
                raw += 1.0
            raw += 0.3 * min(tr["station_count"], 6)
        exp = curated.TRANSIT_EXPANSION.get(t["name"])
        if exp:
            raw += 2.0
        t["transit_exp"] = exp
        t["transit_raw"] = raw

    # ---- second-home raw ----
    for t in towns:
        vac = curated.VACATION.get(t["name"], 0)
        coast = curated.COASTAL.get(t["name"], 0)
        raw = {3: 100, 2: 80, 1: 60}.get(vac, 0)
        if raw == 0 and coast >= 2:
            raw = 50
        elif raw == 0 and coast == 1:
            raw = 30
        t["vac_tier"] = vac
        t["coast_tier"] = coast
        t["second_home_raw"] = raw

    # ---- fill data gaps so nothing reads "n/a" ----
    # 1) remaining town prices from MassGIS assessed value, then county median
    missing = [t for t in towns if t["price"] is None]
    if missing:
        print(f"  filling {len(missing)} town prices from MassGIS assessed values...")
    for t in missing:
        try:
            mv = fetch_town_median_value(t["f"]["geometry"], t["bbox"])
        except Exception as e:
            mv = None
            print(f"    {t['name']}: MassGIS fetch failed ({e})")
        if mv:
            t["price"], t["price_est"] = mv, "assessed"
    def cmed(by, c):
        vals = sorted(v for v in by.get(c, []) if v is not None)
        return vals[len(vals) // 2] if vals else None
    pc = defaultdict(list)
    for t in towns:
        if t["price"]:
            pc[t["county"]].append(t["price"])
    for t in towns:
        if t["price"] is None:
            t["price"], t["price_est"] = cmed(pc, t["county"]), "county est."
    # 2) population growth + density from county medians where missing
    gc, dc = defaultdict(list), defaultdict(list)
    for t in towns:
        gc[t["county"]].append(t["pop_growth"]); dc[t["county"]].append(t["density"])
    for t in towns:
        if t["pop_growth"] is None:
            t["pop_growth"], t["growth_est"] = cmed(gc, t["county"]), True
        if t["density"] is None:
            t["density"] = cmed(dc, t["county"])

    # ---- percentile-normalized helper metrics ----
    def col(attr):
        return [t.get(attr) for t in towns]

    p_growth = pct_ranks(col("pop_growth"))
    p_density = pct_ranks(col("density"))
    p_uni = pct_ranks(col("uni_raw"))
    p_transit = pct_ranks(col("transit_raw"))
    p_waterfrac = pct_ranks(col("water_frac"))
    p_green = pct_ranks(col("green_n"))
    p_culture = pct_ranks(col("culture_n"))
    p_mom3 = pct_ranks(col("mom3"))
    p_fooddens = pct_ranks(col("food_density"))
    p_appr5 = pct_ranks(col("appr5"))

    for i, t in enumerate(towns):
        # criterion scores 0..100
        sc = {}
        sc["transit"] = p_transit[i]
        sc["population_growth"] = p_growth[i] if p_growth[i] is not None else 50.0
        sc["employer"] = {3: 100, 2: 80, 1: 60}.get(curated.EMPLOYER.get(t["name"], 0), 35)
        sc["schools"] = {5: 100, 4: 82, 3: 60, 2: 38, 1: 20}.get(curated.SCHOOL_TIER.get(t["name"], 3), 60)
        # trendy: price momentum + food density + walk density
        sc["trendy"] = (0.5 * (p_mom3[i] if p_mom3[i] is not None else 50)
                        + 0.3 * (p_fooddens[i] if p_fooddens[i] is not None else 40)
                        + 0.2 * (p_density[i] if p_density[i] is not None else 40))
        sc["universities"] = p_uni[i]
        sc["walkability"] = p_density[i] if p_density[i] is not None else 30.0
        sc["second_home"] = t["second_home_raw"]
        # water/beach: water fraction + coastal tier + osm beaches
        coast_score = {3: 100, 2: 75, 1: 50}.get(t["coast_tier"], 0)
        beach_bonus = min(t["beach_n"] * 6, 30)
        sc["water_beach"] = min(100, 0.45 * (p_waterfrac[i] or 0) + 0.4 * coast_score + beach_bonus)
        # green & culture
        sc["green_culture"] = 0.5 * (p_green[i] or 0) + 0.5 * (p_culture[i] or 0)

        t["scores"] = {k: round(v, 1) for k, v in sc.items()}
        t["crit_comp"] = sum(WEIGHTS[k] * sc[k] for k in WEIGHTS) / 100.0

    # ---- fold in REALIZED appreciation now known from the neighborhoods ----
    # Unified town appreciation = Zillow 5-yr price growth where available, else the
    # pop-weighted FHFA appreciation of the town's neighborhoods, else county median.
    fpath = os.path.join(RAW, "town_appr_fhfa.json")
    fhfa = json.load(open(fpath)) if os.path.exists(fpath) else {"towns": {}, "counties": {}}
    for t in towns:
        ft = fhfa["towns"].get(t["gid"]) or {}
        if t["appr5"] is not None:
            t["appr5_u"], t["appr_src"] = t["appr5"], "Zillow 5-yr"
        elif ft.get("appr5") is not None:
            t["appr5_u"], t["appr_src"] = ft["appr5"], "FHFA tract index"
        else:
            t["appr5_u"], t["appr_src"] = None, "county est."
    cv = defaultdict(list)
    for t in towns:
        if t["appr5_u"] is not None:
            cv[t["county"]].append(t["appr5_u"])
    allv = sorted(t["appr5_u"] for t in towns if t["appr5_u"] is not None)
    state_med_appr = allv[len(allv) // 2] if allv else 0.0
    for t in towns:
        if t["appr5_u"] is None:
            t["appr5_u"] = cmed(cv, t["county"]) or state_med_appr
    appr_pctls = pct_ranks([t["appr5_u"] for t in towns])
    for i, t in enumerate(towns):
        t["appr5"] = round(t["appr5_u"], 1)          # display value, now never None
        ap = appr_pctls[i] if appr_pctls[i] is not None else 50.0
        # 80% user's 10 criteria + 20% realized 5-yr appreciation (appreciation tilt)
        t["composite"] = round(0.80 * t["crit_comp"] + 0.20 * ap, 1)

    # ---- ranks ----
    order = sorted(towns, key=lambda t: t["composite"], reverse=True)
    n = len(order)
    for rank, t in enumerate(order, 1):
        t["rank"] = rank
        t["pctl"] = round((n - rank) / (n - 1) * 100, 1)

    # ---- budget fit ----
    for t in towns:
        pr = t["price"]
        if pr is None:
            t["budget_fit"] = "unknown"
        elif pr < BUDGET_LO:
            t["budget_fit"] = "below"
        elif pr <= BUDGET_HI:
            t["budget_fit"] = "in"
        else:
            t["budget_fit"] = "above"
        t["sweet_spot"] = (t["budget_fit"] in ("in", "below")) and t["pctl"] >= 70

    # ---- forward-looking 'future potential' score ----
    compute_future_towns(towns)

    # ---- landlord rentability (now + forward) ----
    compute_rentability(towns)

    # ---- safety / crime estimate (a transparent PROXY, higher = safer / less crime) ----
    #      Reported sub-municipal crime data isn't openly available statewide, so this is an
    #      ESTIMATE from signals that correlate with safety (school tier, home value, appreciation).
    #      The real, cited per-town crime picture lives in each town's researched `safety_note`.
    def _clamp(v, lo=0.0, hi=100.0): return max(lo, min(hi, v))
    for t in towns:
        sch = (t.get("scores") or {}).get("schools", 60)
        appr = t["appr5"] if t.get("appr5") is not None else 25
        val = t.get("price") or 0
        t["safety"] = round(_clamp(0.45 * sch + 0.25 * _clamp((appr - 10) / 60 * 100)
                                   + 0.30 * _clamp((val - 250000) / 450000 * 100)))

    # ---- local government (form + authoritative links) ----
    for t in towns:
        form, kind = curated.gov_form(t["name"])
        q = urllib.parse.quote(f"{t['name']}, Massachusetts")
        wiki = "https://en.wikipedia.org/wiki/" + t["name"].replace(" ", "_") + ",_Massachusetts"
        t["gov"] = {
            "form": form, "kind": kind,
            "site": f"https://duckduckgo.com/?q=!ducky+{urllib.parse.quote(t['name'] + ' MA official ' + kind + ' government website')}",
            "wiki": wiki,
            "budget": f"https://duckduckgo.com/?q={urllib.parse.quote(t['name'] + ' MA property tax rate town budget')}",
        }

    # ---- reasons + cool spots + write ----
    prices = sorted(t["price"] for t in towns if t["price"])
    state_median = prices[len(prices) // 2] if prices else None
    for t in towns:
        build_reasons(t, state_median)
        t["cool_spots"] = pick_cool_spots(t)

    # ---- emit: a LIGHT towns.geojson (only what the map paint + panel header need)
    #      and a town_detail.json sidecar (reasons + cool spots) loaded lazily so the
    #      ~0.6 MB of drill-only text doesn't block first paint. ----
    out_feats = []
    detail = {}
    for t in towns:
        props = {
            "geoid": t["gid"], "name": t["name"], "county": t["county"],
            "composite": t["composite"], "rank": t["rank"], "pctl": t["pctl"],
            "future": t["future"],
            "rentability": t["rentability"], "rent_future": t["rent_future"], "safety": t["safety"],
            "rent": round(t["rent"]) if t.get("rent") else None,
            "rent_est": t.get("rent_est"),
            "gross_yield": round(t["gross_yield"], 1) if t.get("gross_yield") is not None else None,
            "rent_growth3": round(t["rent_growth3"], 1) if t.get("rent_growth3") is not None else None,
            "rent_growth3_est": t.get("rent_growth3_est", False),
            "gov": t["gov"],
            "scores": t["scores"],
            "price": round(t["price"]) if t["price"] else None,
            "price_est": t.get("price_est"),
            "appr5": round(t["appr5"], 1) if t["appr5"] is not None else None,
            "appr_src": t.get("appr_src"),
            "budget_fit": t["budget_fit"], "sweet_spot": t["sweet_spot"],
            "pop2020": t["pop2020"], "pop_growth": round(t["pop_growth"], 1) if t["pop_growth"] is not None else None,
            "density": round(t["density"]) if t["density"] else None,
        }
        geom = t["f"]["geometry"]
        geom["coordinates"] = round_coords(geom["coordinates"])
        out_feats.append({"type": "Feature", "geometry": geom, "properties": props})
        detail[t["gid"]] = {
            "cool_spots": t["cool_spots"],
            "reasons_buy": t["reasons_buy"], "reasons_avoid": t["reasons_avoid"],
        }

    meta = {
        "weights": WEIGHTS, "labels": CRIT_LABEL, "quality": CRIT_QUALITY,
        "budget_lo": BUDGET_LO, "budget_hi": BUDGET_HI, "n_towns": n,
    }
    out = {"type": "FeatureCollection", "meta": meta, "features": out_feats}
    with open(OUT, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    detail_path = os.path.join(HERE, "data", "town_detail.json")
    with open(detail_path, "w") as fh:
        json.dump(detail, fh, separators=(",", ":"))
    print(f"Wrote {n} towns -> {OUT} ({os.path.getsize(OUT)/1e6:.2f} MB) "
          f"+ town_detail.json ({os.path.getsize(detail_path)/1e6:.2f} MB)")
    augment_neighborhoods(towns)  # add forward-looking 'future' score to neighborhoods

    # ---- version manifest so the browser can cache the data files between loads but
    #      bust the cache whenever any of them is rebuilt ----
    import hashlib
    h = hashlib.md5()
    data_dir = os.path.join(HERE, "data")
    for fn in ("towns.geojson", "neighborhoods.geojson", "town_detail.json", "neighborhoods_detail.json"):
        p = os.path.join(data_dir, fn)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                h.update(fh.read())
    ver = h.hexdigest()[:10]
    with open(os.path.join(data_dir, "manifest.json"), "w") as fh:
        json.dump({"v": ver}, fh)
    print(f"  manifest version {ver}")
    print("\nTop 12 opportunity towns:")
    for t in order[:12]:
        print(f"  {t['rank']:3d}. {t['name']:<18} score={t['composite']:5.1f} "
              f"price={'$%dk'%(t['price']//1000) if t['price'] else 'n/a':>7} fit={t['budget_fit']}")
    print("\nTop 10 IN-BUDGET ($400-600k) sweet spots:")
    inb = [t for t in order if t["budget_fit"] == "in"][:10]
    for t in inb:
        print(f"  rank#{t['rank']:3d} {t['name']:<18} score={t['composite']:5.1f} price=${t['price']//1000}k")


# ---------------------------------------------------------------------------
# reasons + cool spots
# ---------------------------------------------------------------------------

def _fmt_price(p):
    if not p:
        return "n/a"
    return f"${p/1000:.0f}k" if p < 1_000_000 else f"${p/1e6:.2f}M"


def build_reasons(t, state_median):
    """Generate concrete, metric-grounded reasons. Each generator emits distinct
    facts; we then dedupe exact text, allow <=2 per criterion, and take the top 10
    by strength so richer towns surface more reasons without fabricating any."""
    buy, avoid = [], []
    s = t["scores"]
    tr = t["transit"]

    def topshare(score):
        return f"top {max(1, round(100 - score))}% statewide"

    # ---------- transit (split by mode + expansion) ----------
    if tr:
        if tr["has_subway"]:
            buy.append((s["transit"], f"Subway access — MBTA rapid transit ({tr['station_count']} "
                        f"station{'s' if tr['station_count'] != 1 else ''} in town)", "transit", "measured"))
        if tr["has_lightrail"] and not tr["has_subway"]:
            buy.append((s["transit"] - 1, "Green Line / light-rail access into Boston", "transit", "measured"))
        if tr["has_commuter_rail"]:
            buy.append((s["transit"] - 2, "On the MBTA commuter rail to Boston", "transit", "measured"))
    else:
        avoid.append((100 - s["transit"], "No MBTA rail station — car-dependent commute", "transit", "measured"))
    if t["transit_exp"]:
        buy.append((96, f"Transit upgrade underway: {t['transit_exp']}", "transit", "curated"))

    # ---------- population growth ----------
    g = t["pop_growth"]
    if g is not None:
        if g >= 8:
            buy.append((s["population_growth"], f"Fast in-migration: population +{g:.0f}% (2010–20), {topshare(s['population_growth'])}", "population_growth", "measured"))
        elif g >= 3:
            buy.append((s["population_growth"] - 6, f"Growing population: +{g:.0f}% (2010–20)", "population_growth", "measured"))
        elif g <= 0:
            avoid.append((100 - s["population_growth"], f"Population is shrinking ({g:+.0f}% 2010–20)", "population_growth", "measured"))
        elif g <= 2:
            avoid.append((58, f"Population nearly flat (+{g:.0f}% 2010–20)", "population_growth", "measured"))

    # ---------- budget fit + value vs. state median ----------
    pr = t["price"]
    if t["budget_fit"] == "in":
        buy.append((88, f"Typical home {_fmt_price(pr)} — right in your $400–600k budget", "budget", "measured"))
    elif t["budget_fit"] == "below":
        buy.append((82, f"Under budget at {_fmt_price(pr)} — room to invest or upgrade", "budget", "measured"))
    elif t["budget_fit"] == "above":
        avoid.append((min(96, 72 + pr / 600000 * 6), f"Typical home {_fmt_price(pr)} — above your $400–600k budget", "budget", "measured"))
    if pr and state_median:
        if pr <= state_median * 0.8 and t["budget_fit"] in ("in", "below"):
            buy.append((64, f"~{round((1 - pr / state_median) * 100)}% below the MA median ({_fmt_price(state_median)}) — value entry", "appreciation", "measured"))
        elif pr >= state_median * 1.7:
            avoid.append((52, f"Among the priciest in MA (~{round((pr / state_median - 1) * 100)}% over the median)", "budget", "measured"))

    # ---------- appreciation + momentum ----------
    if t["appr5"] is not None:
        if t["appr5"] >= 45:
            buy.append((74, f"Strong track record — values up {t['appr5']:.0f}% in 5 years", "appreciation", "measured"))
        elif t["appr5"] >= 30:
            buy.append((58, f"Values up {t['appr5']:.0f}% over the last 5 years", "appreciation", "measured"))
        elif t["appr5"] <= 18:
            avoid.append((56, f"Slower appreciation: {t['appr5']:+.0f}% over 5 years", "appreciation", "measured"))
    if t["mom3"] is not None:
        if t["mom3"] >= 18:
            buy.append((62, f"Hot lately — up {t['mom3']:.0f}% in the last 3 years", "trendy", "proxy"))
        elif t["mom3"] <= 2:
            avoid.append((44, f"Market cooling — {t['mom3']:+.0f}% over 3 years", "trendy", "proxy"))

    # ---------- schools ----------
    tier = curated.SCHOOL_TIER.get(t["name"], 3)
    if tier >= 5:
        buy.append((s["schools"], "Top-tier public schools (among MA's best, 5/5)", "schools", "curated"))
    elif tier == 4:
        buy.append((s["schools"] - 3, "Strong public schools (4/5)", "schools", "curated"))
    elif tier == 2:
        avoid.append((100 - s["schools"], "Schools below the state average (2/5)", "schools", "curated"))
    elif tier == 1:
        avoid.append((100 - s["schools"] + 6, "Struggling school district (1/5)", "schools", "curated"))

    # ---------- universities ----------
    if t["nearest_uni_mi"] <= 6:
        umi = "<1 mi" if t["nearest_uni_mi"] < 1 else f"{t['nearest_uni_mi']:.0f} mi"
        buy.append((s["universities"], f"Next to {t['nearest_uni']} ({umi}) — steady rental demand", "universities", "measured"))
    if t["uni_within10"] >= 3:
        buy.append((s["universities"] - 5, f"{t['uni_within10']} colleges within ~10 mi", "universities", "measured"))
    if t["nearest_uni_mi"] >= 35:
        avoid.append((38, f"Far from major universities (nearest {t['nearest_uni']}, {t['nearest_uni_mi']:.0f} mi)", "universities", "measured"))

    # ---------- walkability ----------
    if s["walkability"] >= 80:
        buy.append((s["walkability"], f"Very walkable, urban density (~{t['density']:,.0f}/sq mi)", "walkability", "proxy"))
    elif s["walkability"] >= 65:
        buy.append((s["walkability"] - 6, f"Walkable town center (~{t['density']:,.0f}/sq mi)", "walkability", "proxy"))
    elif s["walkability"] <= 20 and t["density"]:
        avoid.append((100 - s["walkability"], f"Car-dependent, low density (~{t['density']:,.0f}/sq mi)", "walkability", "proxy"))

    # ---------- second home / vacation ----------
    if t["second_home_raw"] >= 80:
        region = "islands / outer Cape" if t["vac_tier"] == 3 else "Cape / Berkshires"
        buy.append((s["second_home"], f"Premier vacation market ({region}) — strong second-home demand", "second_home", "proxy"))
    elif t["second_home_raw"] >= 50:
        buy.append((s["second_home"] - 6, "Real vacation / second-home appeal", "second_home", "proxy"))
    elif s["second_home"] <= 10:
        avoid.append((30, "Little vacation / second-home demand", "second_home", "proxy"))

    # ---------- water / beach (split) ----------
    if t["coast_tier"] >= 2:
        buy.append((s["water_beach"], "Oceanfront town", "water_beach", "curated"))
    if t["beach_n"] >= 1:
        buy.append((s["water_beach"] - 3, f"{t['beach_n']} public beach{'es' if t['beach_n'] != 1 else ''} in town", "water_beach", "measured"))
    if s["water_beach"] <= 9:
        avoid.append((27, "Landlocked — no beach or notable water frontage", "water_beach", "measured"))

    # ---------- employer ----------
    et = curated.EMPLOYER.get(t["name"], 0)
    if et >= 3:
        buy.append((s["employer"], "Major jobs hub — biotech/tech employer growth", "employer", "curated"))
    elif et == 2:
        buy.append((s["employer"] - 4, "Near major-employer expansion", "employer", "curated"))

    # ---------- culture, green space, food scene (split) ----------
    if t["culture_n"] >= 4:
        buy.append((s["green_culture"], f"Rich culture — {t['culture_n']} museums, theaters & galleries", "green_culture", "measured"))
    if t["green_n"] >= 12:
        buy.append((s["green_culture"] - 4, f"Plenty of green space — {t['green_n']} parks & reserves", "green_culture", "measured"))
    breweries = t["poi_counts"].get("Brewery", 0)
    cafes = t["poi_counts"].get("Cafe", 0)
    if breweries >= 2 or cafes >= 6:
        bits = []
        if breweries >= 2:
            bits.append(f"{breweries} breweries")
        if cafes >= 4:
            bits.append(f"{cafes} cafés")
        if bits:
            buy.append((50, "Lively local scene — " + " & ".join(bits), "trendy", "measured"))
    if t["culture_n"] == 0 and t["green_n"] <= 3:
        avoid.append((34, "Few cultural venues or parks mapped here", "green_culture", "measured"))
    if s["trendy"] <= 22:
        avoid.append((32, "Quiet market — limited buzz / young-buyer pull", "trendy", "proxy"))
    if s["employer"] <= 35 and et == 0:
        avoid.append((24, "Not near a major-employer growth hub", "employer", "curated"))

    # floor: a remote town can score low on everything — still surface its single
    # best criterion so the buy list is never empty (sorts last; cut for rich towns).
    best_k = max(s, key=lambda k: s[k])
    buy.append((s[best_k] * 0.25, f"Its strongest factor: {CRIT_LABEL[best_k].lower()} ({s[best_k]:.0f}/100)", best_k, CRIT_QUALITY[best_k]))

    # dedupe exact text, allow up to 2 per criterion, sort by strength, take top 10
    def dedup(rs):
        seen, per_cat, out = set(), {}, []
        for strength, text, cat, q in sorted(rs, key=lambda r: -r[0]):
            if text in seen or per_cat.get(cat, 0) >= 2:
                continue
            seen.add(text)
            per_cat[cat] = per_cat.get(cat, 0) + 1
            out.append({"text": text, "cat": cat, "q": q})
            if len(out) >= 10:
                break
        return out

    t["reasons_buy"] = dedup(buy)
    t["reasons_avoid"] = dedup(avoid)


def pick_cool_spots(t, limit=12):
    # prioritize distinctive categories, then fill with food
    priority = ["Beach", "Museum", "Theater", "Arts center", "Gallery", "Brewery",
                "Nature reserve", "Park", "Scenic view", "Historic site",
                "Attraction", "Garden", "Marina", "Market", "Cafe", "Restaurant", "Bar"]
    rank = {c: i for i, c in enumerate(priority)}
    spots = sorted(t["pois"], key=lambda p: rank.get(p["cat"], 99))
    caps = {"Restaurant": 2, "Cafe": 2, "Bar": 1, "Park": 2, "Brewery": 2,
            "Nature reserve": 2, "Historic site": 2, "Museum": 2, "Theater": 2,
            "Arts center": 2, "Scenic view": 2, "Garden": 1,
            "Marina": 1, "Market": 1, "Gallery": 1, "Attraction": 2}
    out, per_cat = [], {}
    for p in spots:
        # cap per category so a town's spot list stays diverse
        cap = caps.get(p["cat"], 99)
        if per_cat.get(p["cat"], 0) >= cap:
            continue
        per_cat[p["cat"]] = per_cat.get(p["cat"], 0) + 1
        out.append({"name": p["name"], "cat": p["cat"], "lat": p["lat"], "lon": p["lon"]})
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    main()
