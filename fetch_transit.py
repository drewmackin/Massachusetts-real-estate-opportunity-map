#!/usr/bin/env python3
"""
Build a real per-town rail-transit profile from the MBTA GTFS feed.

GTFS stops.txt carries a `municipality` field, so we can attribute each rail
station to its town without geocoding. We classify stops by the route types that
serve them:
    route_type 2 -> Commuter Rail
    route_type 1 -> Subway (Red/Orange/Blue)
    route_type 0 -> Light rail / trolley (Green Line incl. GLX, Mattapan)

Output: data/raw/transit.json  keyed by municipality name:
  { town: {has_commuter_rail, has_subway, has_lightrail, station_count,
           modes:[...], stations:[{name,lat,lon,modes}] } }
"""
import csv
import io
import json
import os
import zipfile

RAW = os.path.join(os.path.dirname(__file__), "data", "raw")
GTFS = os.path.join(RAW, "mbta_gtfs.zip")
OUT = os.path.join(RAW, "transit.json")

MODE = {"2": "Commuter Rail", "1": "Subway", "0": "Light Rail"}


def main():
    z = zipfile.ZipFile(GTFS)

    # route_id -> route_type
    route_type = {}
    with z.open("routes.txt") as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
            route_type[r["route_id"]] = r["route_type"]

    # trip_id -> mode (only for rail-ish route types we care about)
    trip_mode = {}
    with z.open("trips.txt") as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
            rt = route_type.get(r["route_id"])
            if rt in MODE:
                trip_mode[r["trip_id"]] = MODE[rt]
    print(f"  rail trips: {len(trip_mode)}")

    # stream stop_times: collect stop_id -> set(modes) for rail trips only
    stop_modes = {}
    with z.open("stop_times.txt") as f:
        rd = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        for r in rd:
            m = trip_mode.get(r["trip_id"])
            if m:
                stop_modes.setdefault(r["stop_id"], set()).add(m)
    print(f"  rail-served stop_ids: {len(stop_modes)}")

    # stops.txt: attributes per stop_id; roll child platforms up to parent station
    stops = {}
    with z.open("stops.txt") as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
            stops[r["stop_id"]] = r

    # aggregate per municipality, deduping stations by parent station / name
    towns = {}
    seen_station = {}  # town -> set of station keys
    for sid, modes in stop_modes.items():
        s = stops.get(sid)
        if not s:
            continue
        muni = (s.get("municipality") or "").strip()
        if not muni:
            continue
        # resolve to parent station record if present
        parent = s.get("parent_station") or ""
        prec = stops.get(parent) or s
        name = prec.get("stop_name") or s.get("stop_name")
        try:
            lat = float(prec.get("stop_lat") or s["stop_lat"])
            lon = float(prec.get("stop_lon") or s["stop_lon"])
        except (ValueError, KeyError):
            continue
        key = parent or name  # dedupe platforms of same station

        t = towns.setdefault(muni, {"modes": set(), "stations": {}})
        t["modes"] |= modes
        st = t["stations"].setdefault(key, {"name": name, "lat": lat, "lon": lon, "modes": set()})
        st["modes"] |= modes
        seen_station.setdefault(muni, set()).add(key)

    out = {}
    for muni, t in towns.items():
        stations = []
        for st in t["stations"].values():
            stations.append({"name": st["name"], "lat": round(st["lat"], 5),
                             "lon": round(st["lon"], 5), "modes": sorted(st["modes"])})
        modes = sorted(t["modes"])
        out[muni] = {
            "has_commuter_rail": "Commuter Rail" in modes,
            "has_subway": "Subway" in modes,
            "has_lightrail": "Light Rail" in modes,
            "station_count": len(stations),
            "modes": modes,
            "stations": stations,
        }

    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=0)
    print(f"\nSaved transit for {len(out)} municipalities -> {OUT}")
    for nm in ("Cambridge", "Somerville", "Medford", "Worcester", "Framingham", "Newton", "Lynn"):
        if nm in out:
            o = out[nm]
            print(f"  {nm}: {o['station_count']} stations, modes={o['modes']}")


if __name__ == "__main__":
    main()
