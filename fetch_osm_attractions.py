#!/usr/bin/env python3
"""Recovery: re-fetch the 'attractions' POIs (museums/theaters/galleries/historic/
viewpoints) that came back empty on the first run, and merge into osm_pois.json.
Splits into small per-tag queries so no single request is heavy."""
import json, os, time, urllib.parse, urllib.request

RAW = os.path.join(os.path.dirname(__file__), "data", "raw")
OUT = os.path.join(RAW, "osm_pois.json")
ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter"]

TAGS = [
    ('["tourism"="museum"]', "Museum"),
    ('["amenity"="theatre"]', "Theater"),
    ('["amenity"="arts_centre"]', "Arts center"),
    ('["tourism"="gallery"]', "Gallery"),
    ('["tourism"="viewpoint"]', "Scenic view"),
    ('["tourism"="attraction"]', "Attraction"),
    ('["historic"="monument"]', "Historic site"),
    ('["historic"="memorial"]', "Historic site"),
    ('["historic"="fort"]', "Historic site"),
    ('["historic"="castle"]', "Historic site"),
    ('["historic"="ruins"]', "Historic site"),
    ('["historic"="building"]', "Historic site"),
]

def run(q):
    last=None
    for ep in ENDPOINTS:
        for a in range(2):
            try:
                data=urllib.parse.urlencode({"data":q}).encode()
                req=urllib.request.Request(ep,data=data,headers={"User-Agent":"ma-re-map/1.0"})
                with urllib.request.urlopen(req,timeout=120) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                last=e; print(f"   {ep} retry {a+1}: {e}"); time.sleep(4*(a+1))
    print("   giving up:", last); return {"elements":[]}

def main():
    pois = json.load(open(OUT))
    seen = {(p["lat"],p["lon"],p["name"]) for p in pois}
    added=0
    for filt,cat in TAGS:
        q=f"""[out:json][timeout:90];
area["ISO3166-2"="US-MA"][admin_level=4]->.ma;
( node{filt}["name"](area.ma); way{filt}["name"](area.ma); );
out center tags;"""
        res=run(q); n=0
        for el in res.get("elements",[]):
            tags=el.get("tags",{}); name=tags.get("name")
            if not name: continue
            if el["type"]=="node": lat,lon=el.get("lat"),el.get("lon")
            else:
                c=el.get("center") or {}; lat,lon=c.get("lat"),c.get("lon")
            if lat is None or lon is None: continue
            lat,lon=round(lat,5),round(lon,5)
            key=(lat,lon,name)
            if key in seen: continue
            seen.add(key); pois.append({"name":name,"lat":lat,"lon":lon,"cat":cat}); n+=1; added+=1
        print(f"  {cat:14s} {filt:32s} +{n}")
        time.sleep(1)
    json.dump(pois,open(OUT,"w"))
    from collections import Counter
    print(f"\nAdded {added}; total {len(pois)}")
    print("  by cat:", dict(Counter(p['cat'] for p in pois).most_common()))

if __name__=="__main__": main()
