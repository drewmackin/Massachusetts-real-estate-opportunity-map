# Handoff — MA Real-Estate Opportunity Map

_Snapshot: June 14, 2026. Everything below is built, verified in-browser, and committed._

A self-contained interactive map of all **351 Massachusetts municipalities** for a
first-time buyer (Drew, budget **$400–600k**, appreciation + landlord lens). Pure-Python
stdlib data pipeline (no pip), single `index.html` (Leaflet). No backend.

## Run it (30 seconds)

```bash
cd ~/ma-real-estate-opportunity-map
python3 -m http.server 8000
# open http://localhost:8000/   (must be http, not file://, so fetch() works)
```

The committed `data/` geojson files make it work immediately — **no rebuild needed** to run.

## Rebuild the data (only if refreshing sources)

```bash
# fetch sources (one-time; large CSVs in data/raw/ are git-ignored, re-download if missing)
python3 fetch_boundaries.py fetch_population.py fetch_transit.py fetch_osm.py \
        fetch_osm_attractions.py fetch_tracts.py fetch_places.py   # (run each)
# build — ORDER MATTERS:
python3 build_neighborhoods.py   # -> neighborhoods.geojson + neighborhoods_detail.json
python3 build_data.py            # -> towns.geojson + town_detail.json; rewrites neighborhoods
                                 #    with future+rent fields; stamps data/manifest.json
```
Data downloaded once into `data/raw/` (git-ignored, ~130 MB): `zillow_city_zhvi.csv`
(home values), `zillow_city_zori.csv` (rents), `fhfa_tract_hpi_ma.csv` (tract appreciation),
plus the fetched TIGER/MBTA/OSM files.

## What's built (all verified, console clean)

- **Town choropleth** of all 351 towns, color = composite opportunity (red→green).
- **Color by — multi-select / combine:** ⚡ Future potential, 💰 Rentability, 📈 Rent
  outlook, Overall opportunity, or any of the 10 criteria — **tick several to blend evenly**.
- **Live town leaderboard** (state view side panel): all 351 towns ranked best→worst by the
  current Color-by selection; re-sorts on color/budget change; row hover highlights, click drills in.
- **Click a town →** KPI header (rank · ⚡ future · 💰 rentability · price), **💰 Rentability
  (landlord)** (ZORI yield + demand + 5-yr outlook), **🏛 Local government** (form + links),
  neighborhoods ranked by real appreciation, 10 buy / 10 avoid reasons, scorecard, cool spots.
- **Click a neighborhood →** 5/1/10-yr appreciation, **💰 Rent here** (per-neighborhood
  estimated rent ±% vs town + demand + who-rents-here), **🏛 Home values & deals** (live),
  **🛣 Streets & character** (named streets clipped to the tract, live from OSM), insights, spots.
- **Zoom past z15 → per-house AVM valuation engine:** every parcel shows **est. market value**,
  **ideal buy target**, and **⭐ deal score** (overlooked/discount finder), from real MassGIS
  assessor data + self-authored equations. Legend toggle: Market / Buy / ⭐ Deal / Assessed /
  Budget. Neighborhood "Home values & deals here" lists the top-3 deals with addresses.
- **🏘 Best in-budget hoods** (toolbar) — top 40 affordable-city neighborhoods statewide.
- **Budget filter** (All / ≤$600k / $400–600k / ★ Sweet).
- **Perf:** light first paint (towns.geojson ~0.55 MB) + lazy detail sidecars; content-hash
  `manifest.json` cache versioning (cached across reloads).

## File map

| File | Role |
|------|------|
| `index.html` | the whole app (Leaflet map, panels, leaderboard, valuation engine). ~880 lines. |
| `build_data.py` | town scoring engine → `towns.geojson` + `town_detail.json`; augments neighborhoods (future + rent); writes manifest. |
| `build_neighborhoods.py` | tracts→neighborhoods → `neighborhoods.geojson` + `neighborhoods_detail.json`. |
| `curated.py` | curated tables: universities, transit expansion, coastal, vacation, employer, school tiers, **gov forms**. |
| `fetch_*.py` | data fetchers (boundaries, population, transit, osm, osm_attractions, tracts, places). `fetch_acs.py` is legacy/unused (ACS needs a key). |
| `data/*.geojson, *_detail.json, manifest.json` | generated app data (committed). |
| `data/raw/` | downloaded sources (git-ignored). |
| `README.md` | full methodology + sources. |

## Data sources (all real, keyless/CORS-ok)

TIGERweb (boundaries, decennial population), Zillow ZHVI + **ZORI rents**, MBTA GTFS,
OpenStreetMap Overpass (POIs, places, streets), FHFA tract House Price Index, MassGIS
Standardized Assessors' Parcels (live). Census ACS skipped (needs a key) → those criteria
proxied; schools / employer / gov-form are curated tiers.

## Honest limitations (already surfaced in UI + README)

- **Valuation engine is NOT a licensed appraisal** — no interior condition / renovation /
  photo / private-comp data, so per-house error is real. **Deal flags are leads to
  investigate, not guarantees.** Calibration constants (assessment ratio ≈ 0.95, ~2-yr
  roll-forward) are documented assumptions in `index.html` (`ASR`, `ROLL_YEARS`).
- Rent and some criteria (seasonal %, age, schools, employer) are proxies/curated, clearly flagged.
- Scores rank *relative* opportunity within MA — a research starting point, not financial advice.

## Suggested next steps (ideas, nothing pending)

1. **Sharpen the valuation:** pull each town's assessment **fiscal year** + recent **sale
   price/date** from MassGIS to replace the fixed 2-yr roll-forward and calibrate the ASR
   per town; wire per-town **list-to-sale / days-on-market** into the offer model.
2. Live **DESE school** accountability data + **DLS tax-rate** feed (currently curated/linked).
3. Town/neighborhood **comparison view**; live **weight sliders** for the composite.
4. Minor cleanup: `fhfa['counties']` is computed/exported by `build_neighborhoods.py` but
   unused by `build_data.py` (harmless; from the audit).

## Context for tomorrow

- Memory file (`~/.claude/projects/-Applications/memory/homebuying-profile.md`) has the full
  feature history and Drew's preferences — it'll auto-load next session.
- Two adversarial audit workflows were run this session; all confirmed findings were fixed.
- The local dev server I used for verification (port 8766) is stopped; just run the command above.
