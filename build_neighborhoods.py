#!/usr/bin/env python3
"""
Build neighborhood-level data for the drill-down view.

Base unit = Census tract, but tracts sharing a neighborhood name are MERGED into
one real neighborhood (combined geometry + pop-weighted appreciation), so a city
shows clean named neighborhoods rather than raw tract numbers.

Each neighborhood carries:
  - REAL 5/1/10-yr home-price appreciation (FHFA tract House Price Index)
  - the town it belongs to, a human name (OSM neighbourhood/village, else directional)
  - walkability (density), transit access (dist to MBTA), amenity richness (OSM),
    water/green, university proximity
  - a blended appreciation-tilted "neighborhood score", rank within its town,
    a 'best neighborhood' flag, short insight chips, and top local spots.

Output: data/neighborhoods.geojson
"""
import csv
import json
import math
import os

import curated

HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "data", "raw")
OUT = os.path.join(HERE, "data", "neighborhoods.geojson")


# ---------- geometry / math helpers ----------
def ring_contains(ring, x, y):
    inside = False
    n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]; xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def polys(geom):
    if not geom: return
    if geom["type"] == "Polygon": yield geom["coordinates"]
    elif geom["type"] == "MultiPolygon":
        for p in geom["coordinates"]: yield p

def pip(geom, x, y):
    for poly in polys(geom):
        if poly and ring_contains(poly[0], x, y) and not any(ring_contains(h, x, y) for h in poly[1:]):
            return True
    return False

def bbox(geom):
    xs, ys = [], []
    for poly in polys(geom):
        for ring in poly:
            for c in ring: xs.append(c[0]); ys.append(c[1])
    return (min(xs), min(ys), max(xs), max(ys))

def to_multipolygon(geoms):
    coords = []
    for g in geoms:
        if not g: continue
        if g["type"] == "Polygon": coords.append(g["coordinates"])
        elif g["type"] == "MultiPolygon": coords.extend(g["coordinates"])
    return {"type": "MultiPolygon", "coordinates": coords}

def hav_mi(la1, lo1, la2, lo2):
    R = 3958.8
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1); dl = math.radians(lo2 - lo1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def pct_ranks(vals):
    import bisect
    present = sorted(v for v in vals if v is not None)
    n = len(present)
    if n <= 1: return [50.0 if v is not None else None for v in vals]
    out = []
    for v in vals:
        if v is None: out.append(None); continue
        lo = bisect.bisect_left(present, v); hi = bisect.bisect_right(present, v)
        out.append((lo + hi - 1) / 2.0 / (n - 1) * 100.0)
    return out

DIRS = ["East", "Northeast", "North", "Northwest", "West", "Southwest", "South", "Southeast"]
def dir_label(tlat, tlon, lat, lon, r_frac):
    if r_frac < 0.34: return "Central"
    ang = (math.degrees(math.atan2(lat - tlat, lon - tlon)) + 360) % 360
    return DIRS[int(((ang + 22.5) % 360) / 45)]


def load_fhfa():
    series = {}
    with open(os.path.join(RAW, "fhfa_tract_hpi_ma.csv")) as f:
        for r in csv.DictReader(f):
            try: h = float(r["hpi"])
            except (ValueError, KeyError): continue
            series.setdefault(r["tract"], {})[int(r["year"])] = h
    out = {}
    for t, d in series.items():
        yrs = sorted(d)
        if not yrs: continue
        ly = yrs[-1]
        def chg(n): return (d[ly] / d[ly - n] - 1) * 100 if (ly - n) in d and d.get(ly - n) else None
        out[t] = {"appr1": chg(1), "appr5": chg(5), "appr10": chg(10), "latest_year": ly}
    return out


AMEN = {"Cafe", "Restaurant", "Bar", "Brewery", "Museum", "Theater", "Gallery",
        "Arts center", "Park", "Market", "Attraction"}
# place kinds we'll name neighborhoods after (town/locality excluded as too coarse)
KIND_W = {"neighbourhood": 5, "suburb": 5, "quarter": 4, "borough": 4, "village": 3, "hamlet": 2}


def main():
    towns_geo = json.load(open(os.path.join(RAW, "ma_towns.geojson")))
    tracts_geo = json.load(open(os.path.join(RAW, "ma_tracts.geojson")))
    pois = json.load(open(os.path.join(RAW, "osm_pois.json")))
    places = json.load(open(os.path.join(RAW, "osm_places.json")))
    transit = json.load(open(os.path.join(RAW, "transit.json")))
    fhfa = load_fhfa()

    towns = []
    for f in towns_geo["features"]:
        p = f["properties"]
        name = (p.get("BASENAME") or p.get("NAME") or "").replace(" Town", "").strip()
        towns.append({"geoid": p["GEOID"], "name": name, "geom": f["geometry"], "bbox": bbox(f["geometry"]),
                      "clat": float(p["INTPTLAT"]), "clon": float(p["INTPTLON"])})

    stations = []
    for o in transit.values():
        for st in o.get("stations", []):
            stations.append((st["lat"], st["lon"], st["name"]))

    place_pts = [(pl["lat"], pl["lon"], pl["name"], KIND_W[pl["kind"]])
                 for pl in places if pl["kind"] in KIND_W and "Historic District" not in pl["name"]]

    # ---- tract records ----
    tracts = []
    for f in tracts_geo["features"]:
        p = f["properties"]
        try: clat = float(p["INTPTLAT"]); clon = float(p["INTPTLON"])
        except (TypeError, ValueError): continue
        land = float(p["AREALAND"]) if p.get("AREALAND") else 0.0
        water = float(p["AREAWATER"]) if p.get("AREAWATER") else 0.0
        rec = {"f": f, "gid": p["GEOID"], "clat": clat, "clon": clon, "bbox": bbox(f["geometry"]),
               "pop": p.get("POP100") or 0, "land_sqmi": land / 2_589_988.0,
               "water_frac": water / (land + water) if (land + water) else 0.0, "pois": []}
        rec.update(fhfa.get(p["GEOID"]) or {"appr1": None, "appr5": None, "appr10": None, "latest_year": None})
        tracts.append(rec)

    # assign tracts -> town (centroid in town)
    for t in tracts:
        t["town"] = None
        for tw in towns:
            bx0, by0, bx1, by1 = tw["bbox"]
            if bx0 <= t["clon"] <= bx1 and by0 <= t["clat"] <= by1 and pip(tw["geom"], t["clon"], t["clat"]):
                t["town"] = tw; break

    # assign POIs -> tract
    for poi in pois:
        x, y = poi["lon"], poi["lat"]
        for t in tracts:
            bx0, by0, bx1, by1 = t["bbox"]
            if bx0 <= x <= bx1 and by0 <= y <= by1 and pip(t["f"]["geometry"], x, y):
                t["pois"].append(poi); break

    # name each tract
    def name_tract(t):
        best, bw = None, -1e9
        for (pla, plo, pnm, w) in place_pts:
            if abs(pla - t["clat"]) > 0.03: continue
            d = hav_mi(t["clat"], t["clon"], pla, plo)
            if d <= 1.1 and (w - d) > bw:
                bw, best = (w - d), pnm
        return best

    by_town = {}
    for t in tracts:
        if t["town"]: by_town.setdefault(t["town"]["geoid"], []).append(t)

    for geoid, group in by_town.items():
        tw = group[0]["town"]
        rmax = max((hav_mi(tw["clat"], tw["clon"], t["clat"], t["clon"]) for t in group), default=1.0) or 1.0
        for t in group:
            nm = name_tract(t)
            if not nm:
                r = hav_mi(tw["clat"], tw["clon"], t["clat"], t["clon"]) / rmax
                d = dir_label(tw["clat"], tw["clon"], t["clat"], t["clon"], r)
                nm = f"Central {tw['name']}" if d == "Central" else f"{d} {tw['name']}"
            t["name"] = nm

    # ---- merge tracts sharing (town, name) into neighborhoods ----
    hoods = {}
    for t in tracts:
        if not t["town"]: continue
        key = (t["town"]["geoid"], t["name"])
        hoods.setdefault(key, []).append(t)

    neigh = []
    for (tgeoid, name), grp in hoods.items():
        tw = grp[0]["town"]
        pop = sum(t["pop"] for t in grp)
        land = sum(t["land_sqmi"] for t in grp)
        def wavg(field):
            num = sum((t[field]) * t["pop"] for t in grp if t[field] is not None)
            den = sum(t["pop"] for t in grp if t[field] is not None)
            return num / den if den else None
        cc = {}
        allpois = []
        for t in grp:
            allpois.extend(t["pois"])
            for poi in t["pois"]: cc[poi["cat"]] = cc.get(poi["cat"], 0) + 1
        amen = sum(v for k, v in cc.items() if k in AMEN)
        green = cc.get("Park", 0) + cc.get("Nature reserve", 0)
        # nearest station / university across member tracts
        nd, nnm = 1e9, None
        for t in grp:
            for (sla, slo, snm) in stations:
                if abs(sla - t["clat"]) > 2.0: continue  # ~138 mi: covers all of MA
                d = hav_mi(t["clat"], t["clon"], sla, slo)
                if d < nd: nd, nnm = d, snm
        ud, unm = 1e9, None
        clat = sum(t["clat"] * (t["pop"] or 1) for t in grp) / sum((t["pop"] or 1) for t in grp)
        clon = sum(t["clon"] * (t["pop"] or 1) for t in grp) / sum((t["pop"] or 1) for t in grp)
        for (un, ula, ulo, draw) in curated.UNIVERSITIES:
            d = hav_mi(clat, clon, ula, ulo)
            if d < ud: ud, unm = d, un
        density = (pop / land) if land > 0.02 else None
        water_frac = wavg("water_frac") or 0.0
        neigh.append({
            "town_geoid": tgeoid, "town_name": tw["name"], "name": name,
            "geom": to_multipolygon([t["f"]["geometry"] for t in grp]),
            "pop": pop, "density": density, "water_frac": water_frac,
            "appr5": wavg("appr5"), "appr1": wavg("appr1"), "appr10": wavg("appr10"),
            "latest_year": max((t["latest_year"] or 0) for t in grp) or None,
            "amen": amen, "green_n": green, "cc": cc, "pois": allpois,
            "station_mi": round(nd, 1) if nd < 1e8 else None, "station_nm": nnm,
            "uni_mi": round(ud, 1), "uni_nm": unm,
            "amen_raw": math.sqrt(amen), "transit_raw": math.exp(-nd / 2.0) if nd < 1e8 else 0.0,
            "watergreen_raw": water_frac + 0.015 * green,
        })

    # ---- fill gaps so nothing reads "n/a": estimate missing appreciation from the
    #      town's (then county's) real FHFA neighborhoods; same for density ----
    from collections import defaultdict
    def wmean(pairs):
        num = sum(v * w for v, w in pairs if v is not None and w)
        den = sum(w for v, w in pairs if v is not None and w)
        return (num / den) if den else None
    tg, cg = defaultdict(list), defaultdict(list)
    for h in neigh:
        tg[h["town_geoid"]].append(h); cg[h["town_geoid"][2:5]].append(h)
    town_appr = {g: {k: wmean([(h[k], h["pop"]) for h in hs]) for k in ("appr5", "appr1", "appr10")}
                 for g, hs in tg.items()}
    county_appr = {c: {k: wmean([(h[k], h["pop"]) for h in hs]) for k in ("appr5", "appr1", "appr10")}
                   for c, hs in cg.items()}
    town_dens = {g: sorted([h["density"] for h in hs if h["density"]]) for g, hs in tg.items()}
    cty_dens = {c: sorted([h["density"] for h in hs if h["density"]]) for c, hs in cg.items()}
    def med(a): return a[len(a) // 2] if a else None
    for h in neigh:
        cty = h["town_geoid"][2:5]
        est = False
        for k in ("appr5", "appr1", "appr10"):
            if h[k] is None:
                v = town_appr[h["town_geoid"]][k]
                if v is None: v = county_appr[cty][k]
                h[k] = v
                if v is not None and k == "appr5": est = True
        h["appr_est"] = est
        if not h["density"]:
            h["density"] = med(town_dens[h["town_geoid"]]) or med(cty_dens[cty])
    # export town-level FHFA appreciation (real, pop-weighted) for the town score redo
    json.dump({"towns": town_appr, "counties": county_appr},
              open(os.path.join(RAW, "town_appr_fhfa.json"), "w"))

    # raw signals for the per-neighborhood "which side of town is better" subscores
    for h in neigh:
        cc = h["cc"]
        h["parks_raw"] = h["green_n"] + 8.0 * h["water_frac"]                       # parks + water access
        h["food_raw"] = math.sqrt(cc.get("Cafe", 0) + cc.get("Restaurant", 0)
                                  + cc.get("Bar", 0) + cc.get("Brewery", 0) + cc.get("Market", 0))
        h["culture_raw"] = (cc.get("Museum", 0) + cc.get("Theater", 0) + cc.get("Gallery", 0)
                            + cc.get("Arts center", 0) + 0.5 * cc.get("Historic site", 0))

    # statewide percentiles across neighborhoods
    P = {k: pct_ranks([h[v] for h in neigh]) for k, v in
         {"appr": "appr5", "walk": "density", "amen": "amen_raw", "transit": "transit_raw", "wg": "watergreen_raw",
          "parks": "parks_raw", "food": "food_raw", "culture": "culture_raw"}.items()}
    for i, h in enumerate(neigh):
        ap = P["appr"][i] if P["appr"][i] is not None else 50.0
        h["appr_pctl"] = round(ap, 1)
        h["score"] = round(0.34 * ap + 0.20 * (P["walk"][i] or 30) + 0.20 * (P["amen"][i] or 20)
                           + 0.16 * (P["transit"][i] or 0) + 0.10 * (P["wg"][i] or 20), 1)
        # subscores (0-100, statewide-relative) — the dimensions that genuinely vary block to block
        h["sub"] = {
            "appr": round(ap),
            "walk": round(P["walk"][i] if P["walk"][i] is not None else 30),
            "transit": round(P["transit"][i] if P["transit"][i] is not None else 0),
            "parks": round(P["parks"][i] if P["parks"][i] is not None else 0),
            "dining": round(P["food"][i] if P["food"][i] is not None else 0),
            "culture": round(P["culture"][i] if P["culture"][i] is not None else 0),
        }

    # rank within town
    bytown = {}
    for h in neigh: bytown.setdefault(h["town_geoid"], []).append(h)
    for geoid, g in bytown.items():
        g.sort(key=lambda h: h["score"], reverse=True)
        n = len(g)
        for rank, h in enumerate(g, 1):
            h["rank_in_town"] = rank; h["n_in_town"] = n
            h["is_best"] = (rank == 1 and n >= 2)
            h["is_top"] = rank <= max(1, round(n * 0.25))

    out_feats = [make_feature(h) for h in neigh]
    out = {"type": "FeatureCollection",
           "meta": {"n_neigh": len(out_feats), "n_towns": len(bytown),
                    "latest_year": max((h.get("latest_year") or 0) for h in neigh)},
           "features": out_feats}
    for f in out_feats:                      # round coords (~1 m) to shrink the file
        g = f.get("geometry")
        if g and "coordinates" in g:
            g["coordinates"] = _round_coords(g["coordinates"])
    with open(OUT, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    # spots sidecar (drill-only) keyed by town_geoid|name, loaded lazily by the map
    detail = {f"{h['town_geoid']}|{h['name']}": top_spots(h) for h in neigh}
    detail_path = os.path.join(HERE, "data", "neighborhoods_detail.json")
    with open(detail_path, "w") as fh:
        json.dump(detail, fh, separators=(",", ":"))
    print(f"Wrote {len(out_feats)} neighborhoods in {len(bytown)} towns -> {OUT} "
          f"({os.path.getsize(OUT)/1e6:.2f} MB) + neighborhoods_detail.json "
          f"({os.path.getsize(detail_path)/1e6:.2f} MB)")
    for nm in ("Worcester", "Cambridge", "Lynn", "Boston"):
        tw = next((x for x in towns if x["name"] == nm), None)
        if not tw: continue
        g = sorted(bytown.get(tw["geoid"], []), key=lambda h: h["rank_in_town"])
        print(f"\n{nm}: {len(g)} neighborhoods")
        for h in g[:5]:
            a = f"+{h['appr5']:.0f}%" if h["appr5"] is not None else "n/a"
            print(f"  #{h['rank_in_town']:2d} {h['name']:<24} score={h['score']:.0f} 5yr={a:>6} "
                  f"{'★' if h['is_best'] else ''}")


def insights(h):
    out = []
    if h["appr5"] is not None:
        tag = "🔥 " if h["appr_pctl"] >= 70 else ""
        out.append(f"{tag}+{h['appr5']:.0f}% home-price growth (5 yr)")
    d = h["density"]
    if d and d >= 6000:
        out.append(f"Very walkable (~{d:,.0f}/sq mi)")
    elif d and d >= 2800:
        out.append("Walkable, in-town feel")
    elif d and d <= 1400:
        out.append("Quiet, residential feel")
    if h["station_mi"] is not None and h["station_nm"]:
        if h["station_mi"] <= 0.8:
            out.append(f"Walk to the {h['station_nm']} MBTA station")
        elif h["station_mi"] <= 2.5:
            out.append(f"~{h['station_mi']} mi to {h['station_nm']} (MBTA)")
    if h["amen"] >= 10:
        bits = [f"{h['cc'][k]} {k.lower()}{'s' if h['cc'][k]!=1 else ''}"
                for k in ("Cafe", "Restaurant", "Brewery") if h["cc"].get(k)]
        if bits:
            out.append("Lively — " + ", ".join(bits[:2]))
    if h["green_n"] >= 4:
        out.append(f"Leafy — {h['green_n']} parks & green spaces")
    if h["water_frac"] >= 0.10:
        out.append("On the water")
    if h["uni_mi"] <= 2.5:
        out.append(f"Near {h['uni_nm']} ({h['uni_mi']} mi)")
    cult = h["cc"].get("Museum", 0) + h["cc"].get("Theater", 0) + h["cc"].get("Gallery", 0)
    if cult >= 2:
        out.append(f"Arts & culture ({cult} venues)")
    return out[:5]


def top_spots(h, lim=6):
    pr = ["Beach", "Museum", "Theater", "Brewery", "Park", "Nature reserve", "Historic site",
          "Scenic view", "Gallery", "Arts center", "Cafe", "Restaurant", "Marina", "Bar"]
    rank = {c: i for i, c in enumerate(pr)}
    seen, out = {}, []
    for p in sorted(h["pois"], key=lambda p: rank.get(p["cat"], 99)):
        if seen.get(p["cat"], 0) >= 2: continue
        seen[p["cat"]] = seen.get(p["cat"], 0) + 1
        out.append({"name": p["name"], "cat": p["cat"], "lat": p["lat"], "lon": p["lon"]})
        if len(out) >= lim: break
    return out


def _round_coords(obj, nd=5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, list):
        return [_round_coords(x, nd) for x in obj]
    return obj


def make_feature(h):
    # LIGHT feature (geometry + scoring + insights). `spots` go to the detail sidecar.
    return {"type": "Feature", "geometry": h["geom"], "properties": {
        "town_geoid": h["town_geoid"], "town_name": h["town_name"], "name": h["name"],
        "appr5": round(h["appr5"], 1) if h["appr5"] is not None else None,
        "appr1": round(h["appr1"], 1) if h["appr1"] is not None else None,
        "appr10": round(h["appr10"], 1) if h["appr10"] is not None else None,
        "latest_year": h.get("latest_year"),
        "appr_est": h.get("appr_est", False),
        "score": h["score"], "rank_in_town": h["rank_in_town"], "n_in_town": h["n_in_town"],
        "is_best": h["is_best"],
        "pop": h["pop"], "density": round(h["density"]) if h["density"] else None,
        "station_mi": h["station_mi"], "station_nm": h["station_nm"],
        "uni_mi": h["uni_mi"], "uni_nm": h["uni_nm"],
        "sub": h.get("sub"),
        "insights": insights(h),
    }}


if __name__ == "__main__":
    main()
