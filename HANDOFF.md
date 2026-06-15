# Handoff — MA Real-Estate Opportunity Map

_Updated June 15, 2026. Everything below is built and verified in-browser; working tree is ready to commit.
Researched-town content currently covers 89 of 102 in-budget towns (the rest hit a usage limit mid-run;
re-run the research workflow + `build_research.py` to top up the remaining few — they fall back gracefully)._

A self-contained interactive map of all **351 Massachusetts municipalities** for a first-time
buyer (Drew, budget **$400–600k**, appreciation + landlord lens). Pure-Python stdlib pipeline
(no pip), single `index.html` (Leaflet). Optional stdlib `serve.py` for the ♥ Likes feature.

## Run it (30 seconds)

```bash
cd ~/ma-real-estate-opportunity-map
python3 serve.py            # -> http://localhost:8000/   (recommended: ♥ Likes persist to disk)
# or:  python3 -m http.server 8000   (likes stay in the browser only)
```
The committed `data/` files make it work immediately — **no rebuild needed** to run.

## The "living map" — nightly auto-update (on-market + pre-listing)

`update_listings.py` refreshes a prioritized slice of homes each night and writes
`data/listings.json` (live for-sale + coming-soon), `data/prelist.json` (homes predicted to list
soon), and `data/update_meta.json`. The map merges these so parcels show **For sale / Coming soon /
Possibly coming soon / Not currently listed**.

```bash
# install the 1 AM job (runs at next login if the Mac was off; once-per-day guard):
bash install_autoupdate.sh
# seed data manually any time:
MAP_FORCE=1 python3 update_listings.py
# knobs (env or in the .plist): MAP_TARGET_HOMES (default 500), MAP_MAX_REGIONS (45),
#   MAP_MIN_REGIONS (12), MAP_PRELIST_MIN (55), MAP_ALL_TOWNS=1 (cover all 40+ towns, not just in-budget)
```
**Prioritization** (so it never scans all ~2.8M MA homes): each night it ranks neighborhoods by
town quality + appreciation + rent demand + staleness, **always includes pockets with liked homes**,
walks down the list scraping ~Target homes, and rotates coverage via `data/raw/update_state.json`.
**Sources:** Redfin public `gis-csv` polygon endpoint (active + coming-soon) → matched to MassGIS
assessor parcels by normalized address. Best-effort: some MLS feeds exclude downloads, so
"not listed" can mean "not found".

## Rebuild the static data (only if refreshing sources)

```bash
python3 build_neighborhoods.py   # -> neighborhoods.geojson (+ sub-town subscores) + detail sidecar
python3 build_data.py            # -> towns.geojson + town_detail.json; adds future/rent/sub to hoods; manifest
# town research (real web info) — run the workflow, then:
python3 build_research.py <workflow_results.json>   # -> town_research.json + neighborhoods_research.json
```

## What's built (all verified, console clean)

- **Town choropleth** of all 351 towns; **Color by** is multi-select (⚡future, 💰rentability,
  📈rent outlook, opportunity, or any of 10 criteria — tick several to blend).
- **Live town leaderboard** (state side panel), **budget filter**, **🏘 best in-budget hoods**, **♥ Liked homes**.
- **Click a town →** KPIs · 💰 rentability · 🏛 local government · **🔎 "What it's really like"
  (real web-researched: why-live-here, most-desirable-area, schools/safety/market notes + sources)**
  · **🧭 "Which side of town is better?" lens** (recolor neighborhoods by parks / walk / transit /
  dining / culture / appreciation / rent / opportunity; schools & safety shown town-level) with a
  readable best-vs-weakest + geographic-lean read-out · neighborhoods ranked · buy/avoid · scorecard.
- **Click a neighborhood →** appreciation, 💰 rent here, **researched character blurb**, 🛣 streets, home values & deals.
- **Zoom past z15 → per-house AVM:** every parcel shows **est. market value** (assessment rolled by
  its own **fiscal year** + recent **sale-price anchor** + local $/sqft comps), **ideal buy target**,
  **⭐ deal score**, **est. rent**, and **market status**. Parcel legend: 🏷 Status / Market / Buy /
  ⭐ Deal / Rent / Assessed / Budget.
- **Click a specific home → 80%-screen detail overlay:** on-market price/DOM/Redfin link (or
  "not listed"), value + confidence + full valuation breakdown, rent + yield, ⭐ deal, **◇ likely-to-list
  prediction + reasons**, building facts, owner-occupied vs absentee, neighborhood context, **☆ Like**.

## File map

| File | Role |
|------|------|
| `index.html` | the whole app. ~1,150 lines. |
| `update_listings.py` | **nightly updater**: prioritize → Redfin scrape → match → pre-listing → write listings/prelist/meta. |
| `serve.py` | stdlib server: static + `POST /api/like` → `data/likes.json` + `GET /api/likes`. |
| `com.drew.ma-map-update.plist` / `install_autoupdate.sh` | launchd 1 AM job + installer. |
| `build_neighborhoods.py` | tracts→neighborhoods + **sub-town subscores**. |
| `build_data.py` | town scoring; adds future/rent/sub to neighborhoods; manifest. |
| `build_research.py` | turns a research-workflow result into `town_research.json` + `neighborhoods_research.json`. |
| `.claude/research_workflow*.js` | the web-research workflow (one agent per in-budget town). |
| `curated.py` | curated tables (universities, transit expansion, schools, gov forms…). |
| `data/*.json, *.geojson` | generated app data (committed; `raw/` + `likes.json` git-ignored). |
| `BUILD_PLAN.md` | internal plan/structure doc for this phase. |

## Data sources (all real, keyless/CORS-ok)

TIGERweb, Census decennial, Zillow ZHVI + **ZORI rents**, MBTA GTFS, OSM Overpass, FHFA tract HPI,
**MassGIS L3 Assessors' Parcels** (live — FY, last-sale, owner, rooms…), **Redfin gis-csv**
(live listings), and **public web research** (cited per town). Census ACS skipped (needs a key).

## Honest limitations (surfaced in UI + README)

- **Not a licensed appraisal.** No interior/condition/photo data → per-house error is real; deal &
  pre-listing flags are **leads to investigate, not guarantees**. "Not listed" can mean "not found".
- **Pre-listing is a prediction** from ownership tenure + absentee/out-of-state + redevelopment signals.
- Sub-town **schools & safety are town-level** (schools = curated tier; safety = a labeled proxy, not
  crime stats — sub-area crime isn't openly available). Parks/walk/transit/dining/appreciation are measured.
- Calibration constants (`ASR≈0.95`, fiscal-year roll-forward) are documented assumptions in `index.html`.

## Suggested next steps (ideas, nothing pending)

1. Dial `MAP_TARGET_HOMES` down toward ~100 once Drew's liked set defines the watch-list.
2. Add a real keyless town-level **crime** feed if one surfaces; live **DESE school** accountability.
3. Price-change / new-since-yesterday badges from `first_seen`/`last_seen` already tracked in `listings.json`.
4. Town/neighborhood comparison view; live composite weight sliders.

## Context for tomorrow

- Memory file (`~/.claude/projects/-Applications/memory/homebuying-profile.md`) holds the full feature
  history + Drew's preferences — auto-loads next session.
- The nightly job + research workflow are the two moving parts; everything else is static and committed.
