#!/usr/bin/env python3
"""
qa_check.py — exhaustive town-by-town + neighborhood integrity sweep over the built data.
Loads every data file and verifies each of the 351 towns and all neighborhoods: required
fields, value ranges, rank/percentile integrity, cross-field consistency, research↔data
matching, listings/prelist integrity, and manifest freshness. Prints findings grouped by
severity. Read-only — changes nothing.
"""
import json, os, re, hashlib
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
def load(n, d=None):
    try: return json.load(open(os.path.join(DATA, n)))
    except Exception: return d
HIGH, MED, LOW = [], [], []
def hi(t): HIGH.append(t)
def med(t): MED.append(t)
def low(t): LOW.append(t)

towns_geo = load("towns.geojson"); neigh_geo = load("neighborhoods.geojson")
tres = load("town_research.json", {}); nres = load("neighborhoods_research.json", {})
listings = load("listings.json", {}); prelist = load("prelist.json", {})
manifest = load("manifest.json", {})
TP = {f["properties"]["geoid"]: f["properties"] for f in towns_geo["features"]}
COUNTY = {"001","003","005","007","009","011","013","015","017","019","021","023","025","027"}
CRIT = list((towns_geo.get("meta", {}).get("weights") or {}).keys())

# ---- TOWNS: one pass per town ----
ranks = []; names = Counter()
for g, p in TP.items():
    nm = p.get("name", g)
    names[nm] += 1
    def num(k):
        v = p.get(k); return v if isinstance(v, (int, float)) else None
    # required + ranges
    for k in ("composite", "rank", "pctl", "future", "rentability", "safety"):
        v = num(k)
        if v is None: hi(f"{nm}: missing/non-numeric '{k}'")
        elif k != "rank" and not (0 <= v <= 100): med(f"{nm}: {k}={v} out of 0-100")
    if num("rank"): ranks.append(p["rank"])
    if p.get("county") not in COUNTY: hi(f"{nm}: bad county code {p.get('county')!r}")
    if not re.match(r"^25\d{8}$", str(g)): low(f"{nm}: geoid {g} not 25########")
    a5 = num("appr5")
    if a5 is None: med(f"{nm}: appr5 missing")
    elif not (-40 <= a5 <= 200): med(f"{nm}: appr5={a5} implausible")
    pr = p.get("price")
    if not pr and not p.get("price_est"): low(f"{nm}: no price and not flagged price_est")
    elif pr and not (50000 <= pr <= 5_000_000): med(f"{nm}: price={pr} implausible")
    if p.get("budget_fit") not in ("in", "below", "above", "unknown"): med(f"{nm}: budget_fit={p.get('budget_fit')}")
    gov = p.get("gov") or {}
    for k in ("form", "site", "wiki", "budget"):
        if not gov.get(k): med(f"{nm}: gov.{k} missing")
    sc = p.get("scores") or {}
    for c in CRIT:
        if c not in sc: med(f"{nm}: scores missing '{c}'")
        elif not (0 <= sc[c] <= 100): med(f"{nm}: score {c}={sc[c]} out of range")
    gy = num("gross_yield")
    if gy is not None and not (1 <= gy <= 15): low(f"{nm}: gross_yield={gy} unusual")

# rank integrity
if ranks:
    dup = [r for r, c in Counter(ranks).items() if c > 1]
    if dup: hi(f"duplicate ranks: {dup[:10]}")
    miss = sorted(set(range(1, len(TP)+1)) - set(ranks))
    if miss: hi(f"missing ranks (gaps): {miss[:10]}")
for nm, c in names.items():
    if c > 1: hi(f"duplicate town name '{nm}' x{c}")
print(f"towns: {len(TP)} | criteria: {len(CRIT)} | ranks ok: {not dup and not miss}" if ranks else "no ranks")

# safety sanity — known affluent/safe should be high, known higher-crime lower
SAFE_HI = {"Weston","Wellesley","Lexington","Lincoln","Dover","Sherborn","Carlisle","Hingham","Concord","Duxbury"}
SAFE_LO = {"Springfield","Brockton","Holyoke","Chelsea","Lawrence","Fall River","New Bedford","Lynn","Worcester"}
for g, p in TP.items():
    s = p.get("safety"); nm = p.get("name")
    if s is None: continue
    if nm in SAFE_HI and s < 70: med(f"safety sanity: {nm} safety={s} (expected high)")
    if nm in SAFE_LO and s > 65: med(f"safety sanity: {nm} safety={s} (expected lower)")

# ---- NEIGHBORHOODS ----
hood_names_by_town = defaultdict(set); nbad = 0; nsub = 0
for f in neigh_geo["features"]:
    p = f["properties"]; tg = p["town_geoid"]; nm = p.get("name", "?")
    hood_names_by_town[tg].add(nm)
    if tg not in TP: hi(f"neighborhood '{nm}' references unknown town_geoid {tg}")
    sub = p.get("sub")
    if not sub: nbad += 1
    else:
        nsub += 1
        for d in ("schools","safety","parks","dining","culture","walk","transit","appr","rent","opp"):
            if d not in sub: low(f"{p.get('town_name')}/{nm}: sub missing '{d}'")
    if p.get("score") is None: med(f"{p.get('town_name')}/{nm}: neighborhood score missing")
if nbad: med(f"{nbad} neighborhoods missing sub-scores")
print(f"neighborhoods: {len(neigh_geo['features'])} | with sub: {nsub} | missing sub: {nbad}")

# ---- RESEARCH ↔ data matching ----
res_missing = []; res_neigh_unmatched = 0; res_neigh_total = 0
for g, p in TP.items():
    if not (p.get("composite", 0) >= 40 and p.get("budget_fit") in ("in", "below")): continue
    r = tres.get(g)
    if not r or not r.get("why"): res_missing.append(p.get("name")); continue
    if r.get("name") and r["name"] != p.get("name"):
        med(f"research name mismatch: {g} research='{r['name']}' data='{p.get('name')}'")
    for s in (r.get("sources") or []):
        if not str(s).startswith("http"): low(f"{p.get('name')}: non-URL source {s!r}")
# neighborhood research keys must match a real neighborhood name (else the blurb never shows)
for key in nres:
    res_neigh_total += 1
    if "|" not in key: low(f"bad neigh-research key {key!r}"); continue
    g, nm = key.split("|", 1)
    if nm not in hood_names_by_town.get(g, set()):
        res_neigh_unmatched += 1
if res_missing:
    med(f"{len(res_missing)} in-budget 40+ towns missing research: {sorted(res_missing)}")
if res_neigh_unmatched:
    med(f"{res_neigh_unmatched}/{res_neigh_total} neighborhood-research blurbs don't match a real neighborhood name (won't display)")
print(f"research: {len(tres)} towns, {res_neigh_total} hood blurbs ({res_neigh_unmatched} unmatched)")

# ---- LISTINGS / PRELIST ----
ba = (listings.get("by_addr") or {}); bl = (listings.get("by_loc") or {})
bad_keys = sum(1 for k in ba if "#" not in k or k.split("#")[0] not in TP)
if bad_keys: med(f"{bad_keys} listing by_addr keys have an invalid town_geoid prefix")
pk = (prelist.get("by_key") or {})
bad_pre = sum(1 for v in pk.values() if v.get("town_geoid") not in TP)
if bad_pre: med(f"{bad_pre} prelist entries reference an unknown town_geoid")
print(f"listings: {len(ba)} by_addr / {len(bl)} by_loc | prelist: {len(pk)}")

# ---- MANIFEST freshness ----
files = ["towns.geojson","neighborhoods.geojson","town_detail.json","neighborhoods_detail.json",
         "listings.json","prelist.json","town_research.json","neighborhoods_research.json"]
h = hashlib.md5()
for fn in files:
    fp = os.path.join(DATA, fn)
    if os.path.exists(fp): h.update(open(fp, "rb").read())
calc = h.hexdigest()[:10]
if manifest.get("v") != calc:
    hi(f"manifest stale: file={manifest.get('v')} computed={calc} (run bump_manifest)")

# ---- report ----
print("\n=== FINDINGS ===")
for label, lst in (("HIGH", HIGH), ("MED", MED), ("LOW", LOW)):
    print(f"\n[{label}] {len(lst)}")
    for t in lst[:60]: print("  -", t)
print(f"\nTOT:  HIGH={len(HIGH)}  MED={len(MED)}  LOW={len(LOW)}")
