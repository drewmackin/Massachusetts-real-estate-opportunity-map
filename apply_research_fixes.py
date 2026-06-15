#!/usr/bin/env python3
"""One-off: apply the town-by-town QA review's factual corrections to town_research.json.
Each patch is (town, field, find, replace); reports any that didn't match so nothing fails silently."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
tr = json.load(open(os.path.join(DATA, "town_research.json")))
_towns = json.load(open(os.path.join(DATA, "towns.geojson")))
TP = {f["properties"]["name"]: f["properties"]["geoid"] for f in _towns["features"]}

PATCHES = [
    ("Oxford", "why",
     "It's the headquarters of IPG Photonics, a global fiber-laser manufacturer adding hundreds of local jobs, which anchors the local economy.",
     "It hosts a major IPG Photonics manufacturing campus (a global fiber-laser maker whose world headquarters is now in Marlborough), adding hundreds of local jobs that anchor the local economy."),
    ("Worcester", "safety_note", "The West and southeast sides are safest", "The West Side is safest"),
    ("New Bedford", "safety_note", "parts of the North End near Buttonwood Park", "parts of the West End near Buttonwood Park"),
    ("Fall River", "best_side", "The southwest of the city is the most desired", "The north/northwest of the city is the most desired"),
    ("Ayer", "why", "manufacturing employers like Vitasoy and Pepsi", "manufacturing employers like Nasoya (Pulmuone Foods) and Pepsi"),
    ("Freetown", "why", "Long Pond (the largest natural body of water in Massachusetts)",
     "Long Pond (one of the state's largest natural ponds, shared with Lakeville; the largest is nearby Assawompset Pond)"),
    ("Marlborough", "vibe", "a working corporate-campus mill city, quietly revitalizing",
     "a working corporate-campus former shoe city, quietly revitalizing"),
    ("Marlborough", "why", "giving a once industrial mill city a more well-rounded, livable feel",
     "giving a once industrial shoe-manufacturing city a more well-rounded, livable feel"),
    ("Abington", "safety_note", "roughly 55% below the national rate", "roughly a third below the national rate"),
    ("Hampden", "why", "At a typical ~$448k it sits near the MA state median with low crime.",
     "At a typical ~$448k it sits well below the ~$667k MA state median, with low crime."),
    ("Hampden", "market_note", "Typical home ~$448k, near the MA median,", "Typical home ~$448k, well below the ~$667k MA median,"),
    ("Ashburnham", "why", "the Wachusett MBTA commuter rail station in neighboring Westminster",
     "the Wachusett MBTA commuter rail station in nearby Fitchburg"),
    ("Sandisfield", "best_side", "North Sandisfield — specifically the New Boston village at the junction of Routes 8 and 57.",
     "New Boston village (in central/southeast Sandisfield), at the junction of Routes 8 and 57."),
    ("Rutland", "why", "Worcester's Union Station (Amtrak/MBTA Heart-to-Hub commuter rail to Boston)",
     "Worcester's Union Station (Amtrak and the MBTA Worcester/Framingham Line to Boston)"),
    ("North Adams", "why", "Berkshire Health Systems (former North Adams Regional Hospital campus)",
     "Berkshire Health Systems (North Adams Regional Hospital, reopened 2024)"),
    ("Easthampton", "best_side", "vs. 1 in 35 in northern neighborhoods per CrimeGrade",
     "versus ~1 in 35 in the eastern/southeastern neighborhoods per CrimeGrade"),
    ("Paxton", "why", "hosted Anna Maria College for 80 years", "hosted Anna Maria College since 1952"),
    ("New Ashford", "schools_note", "ranked around 25th in Massachusetts by U.S. News", "ranked around 33rd in Massachusetts by U.S. News"),
    ("Williamstown", "safety_note", "NeighborhoodScout notes it's safer than ~43% of MA communities;",
     "NeighborhoodScout notes it's safer than ~43% of MA communities (Massachusetts sets a high bar — Williamstown's absolute crime rate is low);"),
    ("Norton", "why", "the former TPC Boston golf club (host of the PGA Tour's Deutsche Bank/Dell Technologies Championship through 2018)",
     "TPC Boston, the championship course that hosted the PGA Tour's Deutsche Bank/Dell Technologies Championship through 2018"),
]

ok = miss = 0
for town, field, find, repl in PATCHES:
    g = TP.get(town); r = tr.get(g) if g else None
    if not r or field not in r or find not in (r.get(field) or ""):
        print(f"  MISS  {town}.{field}: pattern not found"); miss += 1; continue
    r[field] = r[field].replace(find, repl); ok += 1
    print(f"  ok    {town}.{field}")

with open(os.path.join(DATA, "town_research.json"), "w") as f:
    json.dump(tr, f, separators=(",", ":"))
print(f"\napplied {ok} / {len(PATCHES)} patches ({miss} missed)")
