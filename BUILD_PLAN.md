# Build Plan — "Living map" upgrade (Jun 2026)

Internal structure doc for the big multi-system add. Constraints: **pure Python 3.9 stdlib**
(no pip), single static `index.html`, no backend except an optional stdlib `serve.py`.
**Claude Desktop app only — no `claude`/node/npm CLI on this machine**, so the nightly job is
pure-Python HTTP (no unattended LLM); deeper LLM web-research is an in-session enrichment.

## What Drew asked for (this phase)
1. **Intra-town insight** — "one side of town is better" (schools / crime / parks …), visual + readable.
2. **More robust, insightful interface.**
3. **Bigger/better** neighborhood characteristics, cool spots, why-live-here — **real researched info**.
4. **Click a home → ~80% of the page** is that home's detail.
5. **More accurate** home value + rent estimates.
6. **On-market status** + **flag homes suspected to list soon**; if not listed, say so on the map.
7. **Auto-update at 1 AM daily** (run on next wake/login if Mac was off). 
8. **A variety of web searches/sources** for value + listing status.
9. **A prioritization algorithm** so it doesn't scan every MA house nightly.
10. **Like/tag homes** to tune what gets refreshed (start 500/night → ~100).

## Ground truth discovered
- **MassGIS L3 parcel fields** (live, keyless): `FY, LS_DATE, LS_PRICE, OWNER1, OWN_ADDR, OWN_STATE,
  NUM_ROOMS, RES_AREA, UNITS, STORIES, STYLE, ZONING, CITY, ZIP, BLD_AREA, LAND_VAL, BLDG_VAL,
  TOTAL_VAL, USE_CODE, SITE_ADDR, LOC_ID, MAP_PAR_ID, LOT_SIZE` …
  → FY = precise assessment date (Jan 1 of FY−1) for roll-forward; LS_* = sale anchor + per-town ASR;
    OWN_ADDR≠SITE_ADDR ⇒ absentee; tenure = today−LS_DATE ⇒ pre-listing signal; NUM_ROOMS/RES_AREA ⇒ rent.
- **Redfin `stingray/api/gis-csv`** works from plain urllib with a browser UA. Accepts a `poly=`
  lon/lat polygon → returns **active + "Pre On-Market" (coming-soon)** listings: ADDRESS, CITY, ZIP,
  PRICE, BEDS, BATHS, SQFT, LOT, YEAR, DAYS ON MARKET, $/sqft, URL. `status=9` = for sale. ~350/region cap.
- Redfin autocomplete = 403 (blocked). realtor.com / zillow return parseable HTML (heavy) — fallback only.
- Nominatim geocode works (rate-limited) — last-resort address match; parcels already carry geometry.

## Data contracts (new files in `data/`, all lazy-loaded, manifest-versioned)
- `listings.json` — `{updated, regions:[...], by_key:{ <key>: {status:active|coming_soon|pending,
  price,beds,baths,sqft,dom,url,src,addr,city,zip,first_seen,last_seen} }}`. key = normalized
  `addr_num|street|zip` (matches a parcel's normalized SITE_ADDR/ADDR_NUM+FULL_STR+ZIP).
- `prelist.json` — `{updated, by_key:{ <parcel LOC_ID>: {score,reasons[],addr,years_owned,absentee} }}`.
- `update_meta.json` — run log: timestamp, shortlist size, regions, #listings, #matched, sources, errors.
- `likes.json` — `{ keys:[...], homes:{key:{addr,note,ts}} }` written by serve.py POST; read by nightly job.
- `town_research.json` / `neighborhood_research.json` — researched real content (workflow output).
- Sub-town subscores ride **inside neighborhoods.geojson** properties (`sub:{schools,safety,...}` + `side` summary).

## Components
- `update_listings.py` (nightly, stdlib): prioritize → scrape Redfin polygons → match → pre-listing → write JSON.
  - **Prioritization** (which homes to refresh, ~500): per parcel `lk = w1·tenure + w2·absentee +
    w3·dealscore + w4·in-budget + w5·liked/similar + w6·high-appreciation pocket`; take top-N regions
    by aggregate likelihood so scraping stays polygon-batched, not per-house. Liked homes always included.
  - **Sources**: Redfin polygon CSV (primary) + realtor/zillow HTML (secondary verify) — "variety of searches".
  - **Match**: normalize addresses both sides; join listing↔parcel; carry over first_seen for new-listing/DOM.
- `serve.py` (stdlib http server): static + `POST /api/like` → likes.json, `GET /api/likes`. Recommend over `python3 -m http.server`.
- `com.drew.ma-map-update.plist` LaunchAgent + `install_autoupdate.sh`: 01:00 + RunAtLoad catch-up + daily lockfile.
- `index.html`: richer parcel fields, sharper AVM, per-house rent, listings/pre-listing merge, **80% home overlay**,
  **sub-town lens + side summary**, bigger researched neighborhood content, **likes/favorites**, market-status legend.
- `build_neighborhoods.py` / `build_data.py`: emit per-neighborhood subscores + side-of-town summary; fetch schools.

## Build order
22 updater → 26 estimates+listings wiring → 27 home overlay → 24 sub-town data → 28 sub-town UI →
25 research workflow → 23 launchd+serve → 29 audit/verify/optimize/docs.

## Honesty rails (UI + README)
- On-market = best-effort multi-source scrape; "not listed" can mean "not found", not "definitely off-market".
- "Possibly coming soon" = a **prediction** from ownership signals, not a guarantee.
- Sub-town safety/schools are proxies/tiers (clearly flagged); parks/walk/transit/dining are measured.
- Estimates remain AVM leads, not appraisals.
