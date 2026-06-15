#!/usr/bin/env python3
"""
update_listings.py  —  nightly "living map" refresh (pure Python 3.9 stdlib, no pip)

What it does each run (designed to run at ~1 AM via launchd, or on next wake/login):
  1. PRIORITIZE  — rank neighborhoods (tracts) so we DON'T scan all ~2.8M MA homes. Liked homes,
     in-budget 40+ towns, hot/high-deal/high-tenure pockets, and stale-since-last-scrape areas
     float to the top. We walk the ranked list until ~TARGET homes are covered, then stop.
  2. SCRAPE      — for each chosen neighborhood we pull live ACTIVE + COMING-SOON listings from
     Redfin's public gis-csv endpoint (polygon query) — a real "search the web" pass. (realtor/
     zillow are kept as optional secondary verification hooks.)
  3. MATCH       — join each listing to a MassGIS assessor parcel by a normalized address key.
  4. PREDICT     — for parcels NOT currently listed, score "possibly coming soon" from ownership
     tenure (LS_DATE), absentee/out-of-state owner, redevelopment signals, hot-pocket, deal signal.
  5. WRITE       — data/listings.json, data/prelist.json, data/update_meta.json (+ rotation state),
     then bump data/manifest.json so the map cache-busts and shows the fresh data.

No API keys. Honest limits: listings are best-effort (some MLS feeds exclude downloads; "not
listed" can mean "not found"). Pre-listing is a PREDICTION, not a guarantee.
"""
import csv, io, json, math, os, re, ssl, sys, time, gzip, hashlib, fcntl
import urllib.request, urllib.parse
from datetime import datetime, date

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
RAW  = os.path.join(DATA, "raw")
os.makedirs(RAW, exist_ok=True)

# ---- config (env-overridable so Drew can dial 500 -> ~100 later) -----------------------------
TARGET_HOMES   = int(os.environ.get("MAP_TARGET_HOMES", "500"))   # ~actionable homes to surface/night
MAX_REGIONS    = int(os.environ.get("MAP_MAX_REGIONS", "45"))     # hard cap on neighborhoods/night
MIN_REGIONS    = int(os.environ.get("MAP_MIN_REGIONS", "12"))     # spread breadth even if target hits early
REQ_SLEEP      = float(os.environ.get("MAP_REQ_SLEEP", "1.4"))    # politeness delay between scrapes
ONLY_INBUDGET  = os.environ.get("MAP_ALL_TOWNS", "0") != "1"      # default: in/below-budget 40+ towns
COMPOSITE_MIN  = float(os.environ.get("MAP_COMPOSITE_MIN", "40")) # Drew's "40+" rule
PRELIST_CAP    = int(os.environ.get("MAP_PRELIST_CAP", "2500"))   # max pre-listing flags to store
KEEP_DAYS      = int(os.environ.get("MAP_KEEP_DAYS", "21"))       # drop listings not re-seen within N days
# daily WATCH-LIST: always scan these towns for affordable homes, pinned to the top of the deals menu
WATCH_TOWNS    = [t.strip() for t in os.environ.get("MAP_WATCH_TOWNS", "Boston,Chelsea,Cambridge,Brookline").split(",") if t.strip()]
WATCH_MAX      = int(os.environ.get("MAP_WATCH_MAX", "500000"))   # ceiling for the watch-list
WATCH_MIN      = int(os.environ.get("MAP_WATCH_MIN", "120000"))   # floor (drops parking spaces / junk)
VERBOSE        = os.environ.get("MAP_VERBOSE", "1") == "1"

PARCEL_URL  = "https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/AGOL/L3_Parcels_FeatureService_4326/FeatureServer/1/query"
REDFIN_CSV  = "https://www.redfin.com/stingray/api/gis-csv"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
TODAY = date.today()
NOWY  = TODAY.year + (TODAY.month - 0.5) / 12.0
ASR   = 0.95

def log(*a):
    if VERBOSE: print(*a, file=sys.stderr, flush=True)

def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    r = urllib.request.urlopen(req, timeout=timeout, context=CTX)
    data = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        data = gzip.decompress(data)
    return r.status, data

# ---- address normalization (MUST match the JS normAddr() in index.html) -----------------------
# Canonicalize the street suffix and KEEP it (so 'Grove Ave' != 'Grove St', but 'St'=='Street').
SUF_CANON = {"ST":"ST","STREET":"ST","AVE":"AVE","AV":"AVE","AVENUE":"AVE","RD":"RD","ROAD":"RD",
    "DR":"DR","DRIVE":"DR","LN":"LN","LANE":"LN","CT":"CT","COURT":"CT","PL":"PL","PLACE":"PL",
    "BLVD":"BLVD","BOULEVARD":"BLVD","TER":"TER","TERR":"TER","TERRACE":"TER","CIR":"CIR","CIRCLE":"CIR",
    "HWY":"HWY","HIGHWAY":"HWY","PKWY":"PKWY","PARKWAY":"PKWY","WAY":"WAY","SQ":"SQ","SQUARE":"SQ",
    "ROW":"ROW","PATH":"PATH","RUN":"RUN","XING":"XING","CROSSING":"XING","TRL":"TRL","TRAIL":"TRL",
    "PT":"PT","POINT":"PT","LOOP":"LOOP","ALY":"ALY","ALLEY":"ALY","BND":"BND","CV":"CV","EXT":"EXT",
    "PIKE":"PIKE","PARK":"PARK","GRN":"GRN","GREEN":"GREEN","COMMON":"COMMON"}
UNIT_RE = re.compile(r"(#|\bAPT\b|\bUNIT\b|\bSTE\b|\bFL\b|\bFLOOR\b|\bRM\b|\bBLDG\b).*$")
def norm_addr(full, zip5=None):
    """Return 'num|streetname|suffix' or None. MassGIS parcels often lack ZIP and use number
    ranges ('194 196 UNION ST'), so we key on house-number + street name + a CANONICAL suffix.
    Keeping the suffix prevents Grove Ave / Grove St collisions; canonicalizing it keeps
    St==Street. Cross-town collisions handled by the town_geoid prefix at storage time.
    MUST stay in lock-step with normAddr() in index.html."""
    s = re.sub(r"\s+", " ", str(full or "")).strip().upper()
    s = UNIT_RE.sub("", s).strip()
    if not s: return None
    toks = s.split(" ")
    m = re.match(r"^(\d+)", toks[0])           # leading house number (12A -> 12)
    if not m: return None
    num = m.group(1)
    rest = [t for t in toks[1:] if t]
    suf = ""
    if rest and rest[-1] in SUF_CANON:
        suf = SUF_CANON[rest[-1]]; rest = rest[:-1]
    # street name = remaining alpha/dir tokens (skip stray numbers like the '196' in a range)
    name = " ".join(t for t in rest if re.match(r"^[A-Z][A-Z0-9]*$", t))
    name = re.sub(r"[^A-Z0-9 ]", "", name).strip()
    if not name: return None
    return "%s|%s|%s" % (num, name, suf)

def parcel_full(p):
    return p.get("SITE_ADDR") or ((str(p.get("ADDR_NUM") or "")+" "+str(p.get("FULL_STR") or "")).strip())

# ---- region (neighborhood) catalog from the built data ----------------------------------------
def bbox_of(geom):
    xs=[]; ys=[]
    def walk(c):
        if not c: return
        if isinstance(c[0], (int,float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c: walk(x)
    walk(geom.get("coordinates"))
    if not xs: return None
    return [min(xs), min(ys), max(xs), max(ys)]

def load_regions():
    towns = {}
    tg = json.load(open(os.path.join(DATA, "towns.geojson")))
    for f in tg["features"]:
        towns[f["properties"]["geoid"]] = f["properties"]
    regions = []
    ng = json.load(open(os.path.join(DATA, "neighborhoods.geojson")))
    for f in ng["features"]:
        p = f["properties"]; tp = towns.get(p["town_geoid"])
        if not tp: continue
        if ONLY_INBUDGET and not (tp.get("composite",0) >= COMPOSITE_MIN and tp.get("budget_fit") in ("in","below")):
            continue
        bb = bbox_of(f["geometry"])
        if not bb: continue
        regions.append({
            "key": p["town_geoid"] + "|" + p["name"],
            "town_geoid": p["town_geoid"], "town_name": p.get("town_name",""),
            "name": p["name"], "bbox": bb,
            "appr5": tp.get("appr5"), "rent_demand": p.get("rent_demand"),
            "score": p.get("score", 50), "composite": tp.get("composite", 0),
            "budget_fit": tp.get("budget_fit"), "price": tp.get("price"),
        })
    return towns, regions

# ---- prioritization: which regions to refresh tonight -----------------------------------------
def load_json(path, default):
    try: return json.load(open(path))
    except Exception: return default

def liked_region_keys(likes):
    """Regions that contain a liked home (by town_geoid|hood stored on the like)."""
    keys = set()
    for h in (likes.get("homes") or {}).values():
        rk = h.get("region")
        if rk: keys.add(rk)
    return keys

def region_priority(r, state, liked_keys):
    days_since = 999
    last = state.get("last_scraped", {}).get(r["key"])
    if last:
        try: days_since = (TODAY - datetime.strptime(last, "%Y-%m-%d").date()).days
        except Exception: pass
    p = 0.0
    p += min(30, (r.get("composite") or 0) * 0.30)                 # better towns first
    p += min(18, max(0, (r.get("appr5") or 0)) * 0.18)             # hotter appreciation
    p += min(14, (r.get("rent_demand") or 0) * 0.14)               # rental demand
    p += min(16, (r.get("score") or 0) * 0.16)                     # neighborhood opportunity
    if r.get("budget_fit") == "in": p += 10
    p += min(22, days_since * 1.1)                                 # staleness -> rotate coverage
    if r["key"] in liked_keys: p += 80                             # liked pockets: always tonight
    return p

# ---- scrape: Redfin active + coming-soon by polygon -------------------------------------------
def _poly_str(bbox):
    w,s,e,n = bbox
    return "%f %f,%f %f,%f %f,%f %f,%f %f" % (w,s, e,s, e,n, w,n, w,s)
def _redfin_rows(qs):
    hdr = {"User-Agent":UA, "Accept":"text/csv,*/*", "Accept-Language":"en-US,en;q=0.9"}
    st, body = http_get(REDFIN_CSV + "?" + qs, hdr)
    if st != 200:
        raise RuntimeError("redfin HTTP %s" % st)
    lines = body.decode("utf-8","replace").splitlines()
    hi = next((i for i,l in enumerate(lines) if l.upper().startswith("SALE TYPE,")), None)
    if hi is None:                              # no CSV header => soft block / markup change, not "0 listings"
        raise RuntimeError("redfin: no CSV header (blocked? len=%d)" % len(body))
    return list(csv.DictReader(io.StringIO("\n".join(lines[hi:]))))
def _row_to_rec(row):
    addr = (row.get("ADDRESS") or "").strip()
    if not addr: return None
    if (row.get("SOLD DATE") or "").strip(): return None        # defensive: skip solds
    dom_raw = (row.get("DAYS ON MARKET") or "").strip()
    coming = "PRE ON-MARKET" in dom_raw.upper() or "COMING" in dom_raw.upper()
    def num(x):
        try: return float(re.sub(r"[^0-9.]","", str(row.get(x) or "")) or 0) or None
        except Exception: return None
    url=""; lat=None; lon=None
    for kcol, vcol in row.items():
        kk=(kcol or "").upper().strip(); vv=(vcol or "").strip()
        if not url and "URL" in kk and vv.startswith("http"): url=vv
        elif kk=="LATITUDE":
            try: lat=float(vv)
            except Exception: pass
        elif kk=="LONGITUDE":
            try: lon=float(vv)
            except Exception: pass
    try: dom = int(float(dom_raw))
    except Exception: dom = None
    return {"addr": addr, "city": (row.get("CITY") or "").strip(),
            "zip": (row.get("ZIP OR POSTAL CODE") or "").strip()[:5],
            "price": num("PRICE"), "beds": num("BEDS"), "baths": num("BATHS"),
            "sqft": num("SQUARE FEET"), "year": num("YEAR BUILT"),
            "ptype": (row.get("PROPERTY TYPE") or "").strip(),
            "dom": dom, "status": ("coming_soon" if coming else "active"),
            "url": url, "lat": lat, "lon": lon, "src": "redfin"}
def redfin_poly(bbox):
    qs = urllib.parse.urlencode({
        "al":"1","num_homes":"350","ord":"redfin-recommended-asc","page_number":"1",
        "sf":"1,2,3,5,6,7","status":"9","uipt":"1,2,3,4,5,6,7,8","v":"8","poly":_poly_str(bbox)})
    return [r for r in (_row_to_rec(row) for row in _redfin_rows(qs)) if r]
def redfin_watch(bbox):
    """Affordable homes/condos/townhouses in a watch town: price-capped, newest first."""
    qs = urllib.parse.urlencode({
        "al":"1","num_homes":"350","ord":"days-on-redfin-asc","page_number":"1",
        "sf":"1,2,3,5","status":"9","uipt":"1,2,3,5","max_price":str(WATCH_MAX),"v":"8","poly":_poly_str(bbox)})
    return [r for r in (_row_to_rec(row) for row in _redfin_rows(qs)) if r]

# ---- parcels for a region (for matching + pre-listing) ----------------------------------------
PARCEL_FIELDS = ("LOC_ID,TOTAL_VAL,LAND_VAL,BLDG_VAL,YEAR_BUILT,USE_CODE,SITE_ADDR,ADDR_NUM,"
                 "FULL_STR,CITY,ZIP,BLD_AREA,RES_AREA,NUM_ROOMS,UNITS,LOT_SIZE,LOT_UNITS,FY,"
                 "LS_DATE,LS_PRICE,OWNER1,OWN_ADDR,OWN_CITY,OWN_STATE,STYLE")
def fetch_parcels(bbox, max_pages=6):
    w,s,e,n = bbox
    feats = []; offset = 0
    for page in range(max_pages):                       # page by the server's ACTUAL returned count + exceededTransferLimit
        qs = urllib.parse.urlencode({
            "geometry": "%f,%f,%f,%f" % (w,s,e,n), "geometryType":"esriGeometryEnvelope",
            "inSR":"4326","outSR":"4326","spatialRel":"esriSpatialRelIntersects",
            "outFields":PARCEL_FIELDS,"returnGeometry":"true",
            "resultRecordCount":"2000","resultOffset":str(offset),"f":"geojson"})
        st, body = http_get(PARCEL_URL + "?" + qs, {"User-Agent":UA})
        obj = json.loads(body.decode("utf-8","replace"))
        chunk = obj.get("features") or []
        feats.extend(chunk); offset += len(chunk)
        if not chunk or not obj.get("exceededTransferLimit"): break   # server caps page size itself; trust its flag
        time.sleep(0.4)
    out = []
    for f in feats:
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        # representative point (first vertex)
        pt = None
        try:
            c = g.get("coordinates")
            while c and not isinstance(c[0], (int,float)): c = c[0]
            if c: pt = [c[0], c[1]]
        except Exception: pass
        p["_pt"] = pt
        out.append(p)
    return out

def parse_year(v):
    s = re.sub(r"[^0-9]","", str(v or ""))
    if len(s) >= 4:
        y = int(s[:4])
        if 1700 <= y <= TODAY.year: return y
    return None

def sale_year_int(v):
    """Extract a plausible sale year from LS_DATE — handles YYYYMMDD, MM/DD/YYYY, epoch-ms.
    MUST stay in lock-step with saleYearJS() in index.html."""
    s = str(v or ""); digits = re.sub(r"[^0-9]", "", s)
    yr = None
    if len(digits) >= 12:                                  # epoch millis
        try: yr = datetime.utcfromtimestamp(int(digits) / 1000).year
        except Exception: yr = None
    elif len(digits) == 8:                                 # YYYYMMDD or MMDDYYYY — pick the 4 that look like a year
        a, b = int(digits[:4]), int(digits[4:8])
        yr = a if 1950 <= a <= TODAY.year else (b if 1950 <= b <= TODAY.year else None)
    elif len(digits) == 4:
        yr = int(digits)
    return yr if (yr and 1900 <= yr <= TODAY.year) else None

def years_owned(ls_date):
    yr = sale_year_int(ls_date)
    return (TODAY.year - yr, yr) if yr else (None, None)

def is_res(p):  return str(p.get("USE_CODE") or "").startswith("1")
def is_sf(p):   return str(p.get("USE_CODE") or "")[:3] == "101"

# ---- valuation (mirrors estMarket() in index.html) so the deals board can rank list-vs-est ----
def town_rate(appr5):
    a = appr5 if appr5 is not None else 25
    a = max(-25, min(120, a))
    return (1 + a / 100.0) ** (1 / 5.0) - 1
def rolled_assessed(p, rate):
    tv = float(p.get("TOTAL_VAL") or 0)
    if tv <= 0: return None
    fy = 0
    try: fy = int(re.sub(r"[^0-9]", "", str(p.get("FY") or ""))[:4] or 0)
    except Exception: fy = 0
    ry = max(0.3, NOWY - (fy - 1)) if 2015 <= fy <= 2030 else 2.0
    return tv / ASR * ((1 + rate) ** ry)
def region_psf(parcels, rate):
    arr = []
    for p in parcels:
        if is_sf(p) and float(p.get("BLD_AREA") or 0) >= 400:
            ra = rolled_assessed(p, rate)
            if ra:
                v = ra / float(p["BLD_AREA"])
                if 60 < v < 2000: arr.append(v)
    arr.sort()
    return arr[len(arr)//2] if len(arr) >= 4 else None
def est_market(p, psf, rate):
    a = rolled_assessed(p, rate)
    if a is None: return None
    b = None
    sqft = float(p.get("BLD_AREA") or 0)
    if psf and is_sf(p) and sqft >= 400:
        yr = parse_year(p.get("YEAR_BUILT")); age = (NOWY - yr) if yr else 0
        age_adj = 0.92 if age > 100 else 0.96 if age > 70 else 0.99 if age > 40 else 1.0
        size_adj = 0.88 if sqft > 4500 else 0.94 if sqft > 3200 else 1.05 if sqft < 900 else 1.0
        b = sqft * psf * age_adj * size_adj
    base = a if b is None else 0.65 * a + 0.35 * max(0.8 * a, min(1.25 * a, b))
    lp = float(p.get("LS_PRICE") or 0); y = sale_year_int(p.get("LS_DATE"))
    if lp > 0 and y and 0.45 * float(p.get("TOTAL_VAL") or 0) <= lp <= 3.0 * float(p.get("TOTAL_VAL") or 0):
        age = max(0, NOWY - y)
        if age <= 7:
            w = 0.60 if age <= 2 else 0.42 if age <= 4 else 0.25 if age <= 6 else 0.12
            sv = max(0.6 * base, min(1.8 * base, lp * ((1 + rate) ** age)))
            return w * sv + (1 - w) * base
    return base
def confidence_py(p, psf, rate):
    """high/med/low — mirrors confidence() in index.html. Gates the deal flag so we don't
    cry 'deal' on a shaky estimate."""
    lp = float(p.get("LS_PRICE") or 0); a0 = float(p.get("TOTAL_VAL") or 0); y = sale_year_int(p.get("LS_DATE"))
    if lp > 0 and y and 0.45 * a0 <= lp <= 3.0 * a0 and (NOWY - y) <= 3: return "high"
    a = rolled_assessed(p, rate)
    if a is None: return "low"
    sqft = float(p.get("BLD_AREA") or 0)
    if psf and is_sf(p) and sqft >= 400:
        yr = parse_year(p.get("YEAR_BUILT")); age = (NOWY - yr) if yr else 0
        age_adj = 0.92 if age > 100 else 0.96 if age > 70 else 0.99 if age > 40 else 1.0
        size_adj = 0.88 if sqft > 4500 else 0.94 if sqft > 3200 else 1.05 if sqft < 900 else 1.0
        b = sqft * psf * age_adj * size_adj
        d = abs(a - b) / ((a + b) / 2); return "high" if d <= 0.12 else "med" if d <= 0.28 else "low"
    return "med" if is_res(p) else "low"

PRELIST_MIN = int(os.environ.get("MAP_PRELIST_MIN", "55"))   # flag ~top 2-6% (notably elevated odds)
def prelist_score(p, town_appr):
    """0-100 'elevated odds of coming to market in ~12 mo' + reasons. A PREDICTION, not a
    guarantee. The strongest real, data-available signals are ownership tenure and absentee /
    out-of-state (investor) ownership — investor-held & long-held homes transact and are
    approachable far more than typical owner-occupied stock."""
    if not is_res(p) or not (float(p.get("TOTAL_VAL") or 0) > 0):
        return 0, []
    sqft = float(p.get("BLD_AREA") or 0)
    if sqft and sqft < 400: return 0, []
    reasons = []; s = 0.0
    yo, yr = years_owned(p.get("LS_DATE"))
    if yo is not None:
        if   yo >= 30: s += 30; reasons.append("Held %d yrs — estate / downsizing window" % yo)
        elif yo >= 20: s += 27; reasons.append("Owned %d yrs — well past the typical move cycle" % yo)
        elif yo >= 14: s += 22; reasons.append("Owned %d yrs — past the typical move cycle" % yo)
        elif yo >= 10: s += 16; reasons.append("Owned %d yrs — entering the move window" % yo)
        elif yo >= 7:  s += 9;  reasons.append("Owned %d yrs" % yo)
    # absentee / investor owner (mailing address differs from the property)
    own_st = str(p.get("OWN_STATE") or "").upper()
    own_city = str(p.get("OWN_CITY") or "").upper().strip()
    site_city = str(p.get("CITY") or "").upper().strip()
    own_addr = norm_addr(p.get("OWN_ADDR")) if p.get("OWN_ADDR") else None
    site_key = norm_addr(parcel_full(p))
    absentee = bool(own_city and site_city and own_city != site_city)
    if own_addr and site_key and own_addr != site_key: absentee = True
    if absentee:
        s += 20; reasons.append("Absentee / investor owner — far more likely to sell or deal")
    if own_st and own_st not in ("MA",""):
        s += 14; reasons.append("Out-of-state owner (%s) — higher disposition odds" % own_st)
    # redevelopment / aging signals
    land = float(p.get("LAND_VAL") or 0); tot = float(p.get("TOTAL_VAL") or 0)
    ls = land/tot if tot>0 else 0
    yb = parse_year(p.get("YEAR_BUILT"))
    if ls >= 0.60 and yb and yb < 1965:
        s += 10; reasons.append("Land-heavy older lot — redevelopment candidate")
    # hot pocket -> higher transaction odds
    if (town_appr or 0) >= 45:
        s += 6; reasons.append("High-appreciation area — stock turns over faster")
    s = max(0, min(100, round(s)))
    # rank reasons by the signal strength order they were added isn't ideal; keep strongest first
    return s, reasons[:3]

# ---- daily watch-list scan of the priority towns ---------------------------------------------
def scrape_watch_towns(prev_addr):
    """Scan WATCH_TOWNS every run for residential homes/condos/townhouses in [WATCH_MIN, WATCH_MAX],
    returning {akey: rec(watch=True)} to pin at the top of the deals menu. No parcel/est needed."""
    out = {}; used = []
    try:
        feats = {f["properties"]["name"]: f for f in json.load(open(os.path.join(DATA, "towns.geojson")))["features"]}
    except Exception:
        return out, used
    for name in WATCH_TOWNS:
        f = feats.get(name)
        if not f: continue
        geoid = f["properties"]["geoid"]; bb = bbox_of(f["geometry"])
        if not bb: continue
        try:
            rows = redfin_watch(bb)
        except Exception as e:
            log("  watch %-12s FAILED %r" % (name, e)); continue
        time.sleep(REQ_SLEEP)
        rkey = geoid + "|__watch__"; kept = 0
        for L in rows:
            pt = (L.get("ptype") or "").lower(); a = (L.get("addr") or "").lower(); price = L.get("price") or 0
            if "land" in pt or "lot" in pt: continue                       # not a home
            if re.search(r"pkg|parking|garage|\bpk:", a): continue          # drop parking spaces
            if not (WATCH_MIN <= price <= WATCH_MAX): continue
            k = norm_addr(L.get("addr"), L.get("zip"))
            if not k: continue
            akey = geoid + "#" + k
            rec = dict(L); rec["watch"] = True; rec["town_geoid"] = geoid; rec["region"] = rkey
            rec["first_seen"] = (prev_addr.get(akey) or {}).get("first_seen") or TODAY.isoformat()
            rec["last_seen"] = TODAY.isoformat()
            out[akey] = rec; kept += 1
        used.append({"key": rkey, "name": name, "town": name, "listings": kept, "watch": True})
        log("  watch %-12s kept=%d / %d scraped" % (name, kept, len(rows)))
    return out, used

# ---- main -------------------------------------------------------------------------------------
LAST_RUN = os.path.join(RAW, "last_run.txt")
def already_ran_today():
    try:
        return open(LAST_RUN).read().strip() == TODAY.isoformat()
    except Exception:
        return False
def mark_ran_today():
    try:
        with open(LAST_RUN, "w") as f: f.write(TODAY.isoformat())
    except Exception:
        pass

def main():
    t0 = time.time()
    # launchd may fire this at 1 AM AND again at the next login/wake (catch-up). The daily
    # guard makes the catch-up a no-op once the day's run is done. Manual runs always go.
    if os.environ.get("MAP_SCHEDULED") == "1" and os.environ.get("MAP_FORCE") != "1" and already_ran_today():
        log("already ran today (%s) — skipping scheduled catch-up" % TODAY.isoformat()); return
    # exclusive lock so an overlapping 1 AM fire + login catch-up can't both write concurrently
    lock = open(os.path.join(RAW, "update.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("another update is already running — exiting"); return
    log("== update_listings: TARGET_HOMES=%d ONLY_INBUDGET=%s ==" % (TARGET_HOMES, ONLY_INBUDGET))
    towns, regions = load_regions()
    state = load_json(os.path.join(RAW, "update_state.json"), {"last_scraped": {}})
    state.setdefault("last_scraped", {})
    likes = load_json(os.path.join(DATA, "likes.json"), {"keys": [], "homes": {}})
    liked_keys = liked_region_keys(likes)

    # ACCUMULATE across nights: keep prior listings/predictions for regions NOT scraped tonight,
    # dropping only entries that have gone stale (not re-seen within KEEP_DAYS). Without this the
    # file would shrink to just tonight's ~45 regions and the rest would vanish from the map.
    prev = load_json(os.path.join(DATA, "listings.json"), {})
    prev_addr = prev.get("by_addr", {})
    def recent(rec):
        try: return (TODAY - datetime.strptime(rec.get("last_seen", ""), "%Y-%m-%d").date()).days <= KEEP_DAYS
        except Exception: return False
    by_addr = {k: v for k, v in prev_addr.items() if recent(v)}   # by_loc is derived client-side from this
    prelist = dict(load_json(os.path.join(DATA, "prelist.json"), {}).get("by_key") or {})

    regions.sort(key=lambda r: region_priority(r, state, liked_keys), reverse=True)

    used = []; errors = []; src_counts = {"redfin": 0}; matched_count = 0
    run_surfaced = 0     # listings + new pre-listing flags found THIS run (drives the nightly budget)

    # daily WATCH-LIST: always scan the priority towns (e.g. Boston/Chelsea/Cambridge/Brookline)
    # for affordable homes, pinned to the top of the deals menu. Runs every night, regardless of rotation.
    by_addr = {k: v for k, v in by_addr.items() if not str(v.get("region", "")).endswith("__watch__")}
    watch_geoids = []
    try:
        watch_recs, watch_used = scrape_watch_towns(prev_addr)
        by_addr.update(watch_recs); used.extend(watch_used)
        watch_geoids = [u["key"].split("|")[0] for u in watch_used]
        log("watch-list: %d listings across %d towns" % (len(watch_recs), len(watch_used)))
    except Exception as e:
        errors.append("watch: %r" % e)

    for r in regions:
        if len(used) >= MAX_REGIONS or (run_surfaced >= TARGET_HOMES and len(used) >= MIN_REGIONS):
            break
        rkey, tgeo = r["key"], r["town_geoid"]
        try:
            rf = redfin_poly(r["bbox"]); src_counts["redfin"] += len(rf)
        except Exception as e:
            errors.append("redfin %s: %r" % (r["name"], e)); rf = None
        time.sleep(REQ_SLEEP)
        try:
            parcels = fetch_parcels(r["bbox"])
        except Exception as e:
            errors.append("parcels %s: %r" % (r["name"], e)); parcels = []
        time.sleep(REQ_SLEEP * 0.6)
        if rf is None and not parcels:
            continue                                   # total failure here -> leave prior data intact
        rf = rf or []

        # refresh this region: drop its stale entries, then re-add what we just found
        by_addr = {k: v for k, v in by_addr.items() if v.get("region") != rkey}
        prelist = {k: v for k, v in prelist.items() if v.get("region") != rkey}

        by_key = {}
        for p in parcels:
            k = norm_addr(parcel_full(p))
            if k: by_key.setdefault(k, p)
        rate = town_rate(r.get("appr5")); psf = region_psf(parcels, rate)   # for the est/disc on listings

        listed_keys = set()
        for L in rf:
            k = norm_addr(L["addr"], L["zip"])
            if not k: continue
            listed_keys.add(k)
            p = by_key.get(k)
            akey = tgeo + "#" + k                       # client looks up by town_geoid + normalized addr
            old = prev_addr.get(akey)
            rec = dict(L); rec["region"] = rkey; rec["town_geoid"] = tgeo
            rec["first_seen"] = (old or {}).get("first_seen") or TODAY.isoformat()
            rec["last_seen"]  = TODAY.isoformat()
            if p:
                rec["loc_id"] = p.get("LOC_ID"); rec["assessed"] = p.get("TOTAL_VAL")
                # est/disc only for WHOLE-home sales: skip condos/units (a unit listing matched to its
                # whole-building parcel gives an absurd "discount"), and bound disc to drop bad matches.
                ptype = (L.get("ptype") or "").lower()
                is_unit = bool(re.search(r"#|\bunit\b|\bapt\b|\bbsmt\b", (L.get("addr") or "").lower()))
                is_condo = "condo" in ptype or "co-op" in ptype or str(p.get("USE_CODE") or "")[:3] == "102"
                is_land = "land" in ptype or "lot" in ptype
                if L.get("price") and not is_unit and not is_condo and not is_land:
                    ev = est_market(p, psf, rate); price = L["price"]
                    # only trust the est if it's in a believable band of the asking price; far
                    # outside => the listing matched the wrong parcel (e.g. new-construction lot).
                    if ev and 0.55 * price <= ev <= 1.8 * price:
                        rec["est"] = int(round(ev))
                        conf = confidence_py(p, psf, rate); rec["conf"] = conf
                        disc = round((ev - price) / ev * 100)        # +% = listed below our est
                        if conf != "low" and -35 <= disc <= 35:      # flag a deal only on a trustworthy est
                            rec["disc"] = disc
                matched_count += 1
            by_addr[akey] = rec
            run_surfaced += 1

        for p in parcels:
            k = norm_addr(parcel_full(p)); loc = p.get("LOC_ID")
            if not loc or (k and k in listed_keys): continue
            sc, why = prelist_score(p, r.get("appr5"))
            if sc >= PRELIST_MIN:
                yo, _ = years_owned(p.get("LS_DATE"))
                prelist[loc] = {"score": sc, "reasons": why, "addr": parcel_full(p),
                                "region": rkey, "town_geoid": tgeo,
                                "years_owned": yo, "key": k, "pt": p.get("_pt")}
                run_surfaced += 1

        state["last_scraped"][rkey] = TODAY.isoformat()
        used.append({"key": rkey, "name": r["name"], "town": r["town_name"],
                     "listings": len(rf), "parcels": len(parcels)})
        log("  %-26s %-13s listings=%-3d parcels=%-4d run=%d total=%d" %
            (r["name"][:26], r["town_name"][:13], len(rf), len(parcels), run_surfaced, len(by_addr)))

    if not used:
        log("no regions scraped successfully — keeping previous data, not bumping manifest"); return

    if len(prelist) > PRELIST_CAP:
        prelist = dict(sorted(prelist.items(), key=lambda kv: kv[1]["score"], reverse=True)[:PRELIST_CAP])

    updated = datetime.now().isoformat(timespec="seconds")
    write_json(os.path.join(DATA, "listings.json"),
               {"updated": updated, "regions": [u["key"] for u in used],
                "watch_geoids": watch_geoids, "watch_max": WATCH_MAX, "by_addr": by_addr})
    write_json(os.path.join(DATA, "prelist.json"),
               {"updated": updated, "by_key": prelist})
    meta = {"updated": updated, "target_homes": TARGET_HOMES, "regions_scraped": len(used),
            "listings_total": len(by_addr), "listings_fresh": run_surfaced, "matched_to_parcel": matched_count,
            "prelist_total": len(prelist), "sources": src_counts, "errors": errors[:20],
            "seconds": round(time.time()-t0, 1), "regions": used}
    write_json(os.path.join(DATA, "update_meta.json"), meta)
    write_json(os.path.join(RAW, "update_state.json"), state)
    bump_manifest()
    mark_ran_today()
    log("== done in %.1fs: %d listings total (%d fresh, %d matched), %d pre-listing, %d regions ==" %
        (meta["seconds"], len(by_addr), run_surfaced, matched_count, len(prelist), len(used)))
    print(json.dumps({k: meta[k] for k in
          ("updated","regions_scraped","listings_total","listings_fresh","matched_to_parcel","prelist_total","seconds")}, indent=2))

def write_json(path, obj):
    tmp = "%s.%d.tmp" % (path, os.getpid())          # pid-unique temp avoids concurrent-run collisions
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
        f.flush(); os.fsync(f.fileno())              # durable before the atomic rename
    os.replace(tmp, path)

def bump_manifest():
    """Re-hash the data files the map loads so the client cache-busts to the fresh data."""
    files = ["towns.geojson","neighborhoods.geojson","town_detail.json","neighborhoods_detail.json",
             "listings.json","prelist.json","town_research.json","neighborhoods_research.json"]
    h = hashlib.md5()
    for fn in files:
        fp = os.path.join(DATA, fn)
        if os.path.exists(fp):
            with open(fp, "rb") as f: h.update(f.read())
    write_json(os.path.join(DATA, "manifest.json"), {"v": h.hexdigest()[:10]})

if __name__ == "__main__":
    main()
