# Massachusetts Real-Estate Opportunity Map

An interactive choropleth of all **351 MA municipalities**, color-ranked (red → green)
by a composite **appreciation-opportunity** score built from 10 user-chosen criteria,
tuned for a first-time buyer with a **$400–600k budget**.

**Click any town to drill in:** the map zooms in and the panel opens with a clean
**KPI header** (opportunity rank · ⚡ future potential · 💰 rentability · typical
price), then the town's **rentability (landlord view)**, **local government**, its
**neighborhoods ranked by real home-price appreciation** (best ones highlighted),
**10 reasons to buy / 10 reasons not to buy** (each grounded in a real metric), the
10-criteria scorecard, and **cool local spots** with map pins. Click a neighborhood
for its 5/1/10-yr appreciation, insight chips, and local spots.

**Combine any factors:** the *Color by* control is a multi-select — tick **⚡ future
potential + 💰 rentability** (or any criteria) and the map recolors by their even
blend, so you can paint, say, "where will it appreciate *and* rent well."

**Live town leaderboard:** in the statewide view the side panel lists **all 351 towns
ranked best → worst by your current Color-by selection** (the blended score when you
combine factors), each with price + budget fit. It re-sorts instantly as you change
the metric or budget filter; click any row to drill into that town.

## Run it

```bash
cd ma-real-estate-opportunity-map
python3 serve.py            # http://localhost:8000/  (recommended — ♥ Likes persist to disk)
# or:  python3 -m http.server 8000   (likes stay in the browser only)
```

To rebuild the data from scratch:

```bash
# --- fetch sources (one-time / refresh) ---
python3 fetch_boundaries.py    # TIGERweb town polygons + area + centroid
python3 fetch_population.py     # 2020/2010 decennial population -> growth
python3 fetch_transit.py        # MBTA GTFS -> rail stations per town
python3 fetch_osm.py            # OpenStreetMap POIs (cool spots + amenities)
python3 fetch_osm_attractions.py # OSM attraction POIs (appended to osm_pois.json)
python3 fetch_tracts.py         # TIGERweb census-tract polygons (~1,620)
python3 fetch_places.py         # OSM neighbourhood/village names
# downloaded once into data/raw/:  zillow_city_zhvi.csv (home values),
#   zillow_city_zori.csv (ZORI rents), fhfa_tract_hpi_ma.csv (tract appreciation)

# --- build (order matters) ---
python3 build_neighborhoods.py  # tracts->neighborhoods -> data/neighborhoods.geojson
python3 build_data.py           # joins + scores -> data/towns.geojson; also adds the
                                #   forward score to neighborhoods + writes manifest.json
```

> Run `build_neighborhoods.py` **before** `build_data.py`: the town build folds
> neighborhood appreciation into the town score, writes the ⚡ future score back into
> the neighborhood file, and stamps `data/manifest.json` (the cache version) from both.

## Neighborhood drill-down

Base unit is the **census tract**; tracts that share a neighborhood name are
merged into one real neighborhood (e.g. East Cambridge, Webster Square). Each carries:

| Field | Source | Quality |
|-------|--------|:--:|
| 5 / 1 / 10-yr home-price appreciation | **FHFA tract House Price Index** (repeat-sales, thru 2025) | measured |
| Name | OSM neighbourhood/village (else directional) | measured |
| Walkability, transit distance, amenities, water, university | Census + MBTA + OpenStreetMap | measured |
| Neighborhood "opportunity score" | appreciation-tilted blend of the above | derived |

The **best neighborhood** = top score in the town; map color = 5-yr appreciation
(red→green), toggleable to ⚡ future or the opportunity score. ~90% of neighborhoods
have measured FHFA appreciation; the ~10% FHFA suppresses (often condo-dense downtown
tracts) get appreciation **estimated from their town/county and shown with a `~`** —
nothing reads "n/a". 110 larger towns are richly subdivided; ~100 small towns are a
single market.

Each neighborhood panel also carries:

- **💰 Rent here** — an **estimated monthly rent** that varies *within* the town: the
  town's Zillow rent scaled by this area's transit access, walkability, university pull
  and appreciation (so East Cambridge reads +25% vs the Cambridge average, a quiet
  outer tract reads −25%). Plus a **rental-demand** score and **who rents here**
  (students near a university, transit commuters, families) — because rent genuinely
  varies block to block. Clearly labeled an estimate.
- **🛣 Streets & character** — the actual **named streets inside the neighborhood
  polygon**, pulled live from OpenStreetMap and clipped to the tract, split into main
  roads vs. residential side streets with a one-line read of the street pattern (e.g.
  "Binney Street is the spine; the rest are quiet residential side streets").

## Street / parcel level (zoom in)

Zoom past **z15** inside any town and the map lazily loads, for the current
viewport:

- **Every property parcel**, colored by **real assessed value**, from the
  **MassGIS Standardized Assessors' Parcels** feature service (live, on demand).
  Click a lot for its address, total/land/building assessed value, style, year
  built, square footage and **$/sqft**.
- The **OSM street network** drawn on top, so individual streets read clearly.

Both are fetched client-side at interaction time (CORS-enabled), so nothing is
pre-baked — the property data is always the assessors' latest.

## 🏠 Per-house valuation engine (AVM) — market value · ideal buy · deal finder

Every parcel you zoom to gets **its own estimate**, computed live from the real
assessor data — an Automated Valuation Model (the method behind Zillow's Zestimate,
Redfin, and assessor mass-appraisal), with **transparent, self-authored equations**:

- **Estimated market value** = a blend of two of the classic appraisal approaches:
  - *(A) assessment, rolled to today* — MA assesses at "full and fair cash value" as of
    Jan 1 of the prior year (median assessment-to-sale ratio 90–110%, so `market ≈
    assessed / 0.95`), then rolled forward ~2 yrs by the town's appreciation rate.
  - *(B) sales-comparison* — building sqft × the **single-family** median $/sqft of the
    parcels in view (age/size-adjusted). Used only for single-family (apples-to-apples);
    condos & multi-family lean on the calibrated assessment. The comp's influence is
    bounded so a stray $/sqft can't blow up the estimate. A **confidence** flag reflects
    how well the two agree.
- **Ideal buy target** — a **disciplined value-buyer** number: a few % under market,
  widened toward ~10–12 % under for properties with genuine deal signals.
- **⭐ Deal finder** — flags **overlooked / discountable** homes (the map can color by it):
  single-family priced 28–55 % under the block's $/sqft, **land-heavy + underbuilt lots**
  (rebuild / ADU / expansion upside), **fixer-uppers** (old + low building value), large
  homes at a low $/sqft, and **real homes under $600k in high-demand pockets**. Each home
  shows its single strongest reason; non-homes (parking, fractional, sub-half-median
  anomalies) are filtered out.

Parcel popups show all four (assessed · est. market · ideal buy · deal). The legend's
property toggle switches the map between **Market / Buy / ⭐ Deal / Assessed / Budget**,
and each neighborhood panel gets a **"Home values & deals here"** summary (median value,
$/sqft, disciplined buy target, and the top-3 deals to investigate with addresses).

**Honest limits:** this is *not* a licensed appraisal. There's no interior condition,
renovation, photo, or private-comp data, so per-house error is real (AVMs run ~2–7 %
median error with fatter tails on unusual homes). **Deal flags are leads to investigate,
not guarantees** — a low number can mean poor condition, not a bargain. The calibration
constants (assessment ratio ≈ 0.95, ~2-yr roll-forward) are documented, transparent
assumptions. Sources: [MA DLS FY2025 assessment standards](https://www.mass.gov/info-details/fy2025-assessment-update),
[Needham property-value process](https://www.needhamma.gov/195/Property-Value-Process),
[Wikipedia: Automated valuation model](https://en.wikipedia.org/wiki/Automated_valuation_model),
[sales-comparison approach](https://en.wikipedia.org/wiki/Sales_comparison_approach).

The estimate is sharpened with two MassGIS fields most AVMs ignore at this price: each parcel's
**assessment fiscal year** (`FY`) — so it rolls forward by its *own* assessment age rather than a
fixed window — and its **most recent arm's-length sale** (`LS_PRICE`/`LS_DATE`, rolled to today and
weighted by recency; $1 family transfers and bulk deals are filtered out). A recent real sale makes
the estimate **high-confidence**. Each home also gets a **per-house rent estimate** (the town's
Zillow ZORI rent scaled sub-linearly by the home's value, ×units for multi-families) and a yield.

## 🔴 Living map — on-market status, pre-listing flags & nightly auto-update

`update_listings.py` runs every night (1 AM via a launchd job — see `install_autoupdate.sh`; it
catches up at the next login if the Mac was off) and makes the map *live*:

- **On the market** — scrapes Redfin's public `gis-csv` polygon endpoint for **active and
  coming-soon** listings, matches each to its MassGIS parcel by a normalized address, and the map
  shows **For sale (price · days-on-market · link) / Coming soon / Sale pending / Not currently
  listed** on each home. (Best-effort: some MLS feeds exclude downloads, so "not listed" can mean
  "not found.")
- **Possibly coming soon** — a **prediction** for homes *not* currently listed, from ownership
  tenure (years since last sale), absentee / out-of-state ownership, redevelopment signals and a
  hot-market boost. A lead to watch or approach the owner — not a guarantee.
- **A prioritization algorithm** so it never scans all ~2.8M MA homes: it ranks neighborhoods by
  town quality + appreciation + rent demand + how long since they were last refreshed, **always
  includes the pockets around your ♥ liked homes**, and covers ~`MAP_TARGET_HOMES` (default 500,
  tunable toward 100) per night, rotating coverage over time.
- A **🏷 Status** parcel legend mode colors every home by its market status; the parcel legend also
  adds a **Rent** mode.

## 🏡 The home detail page (click any home)

Clicking a specific home opens a **full ~80%-screen detail page** instead of a small popup:
its on-market price/days/Redfin link (or "not currently listed"), estimated market value +
confidence + the full valuation breakdown (assessed → rolled-to-today → comps → last sale), rent +
yield, ⭐ deal score, the **◇ likely-to-list prediction with its reasons**, building facts
(beds/rooms/sqft/year/style/lot/zoning), **owner-occupied vs. absentee**, the neighborhood context,
and a **☆ Like** button. Liked homes are saved (and feed the nightly prioritization via `serve.py`).

## 🧭 Which side of town is better?

Drilling into a town shows a **lens** that recolors its neighborhoods by any single factor —
📈 appreciation, 🚶 walkability, 🚆 transit, 🌳 parks & green, 🍽 dining, 🎭 arts & culture,
💰 rent demand, ⭐ opportunity — with a plain-English read-out naming the **strongest and weakest
areas and which side of town leads** (e.g. *"the southern side of Worcester leads for parks"*). The
sub-scores come from real OSM + pipeline data per neighborhood. **🛡 Safety / crime** is also a
top-level **Color by** option (rank every town safest→riskiest) and varies by neighborhood — but it
is a **labelled estimate** from signals that correlate with safety (school tier, home value,
appreciation, area desirability), *not* reported crime stats, since sub-municipal crime data isn't
openly available statewide. The real, cited crime picture for each town lives in its **🔎 "What it's
really like"** safety note. **🎓 Schools** is the curated district tier (town-level, marked •).

## 🔎 Researched town content

Each in-budget 40+ town carries **real, web-researched** content (gathered by a fan-out of
web-research agents, cited): why people live there, the most desirable area, school and safety
reputation, recent market/development notes, and a character blurb per neighborhood — shown as the
**"What *town* is really like"** section and on each neighborhood. Rebuilt with `build_research.py`.

## Statewide views

- **🏘 Best in-budget hoods** (toolbar) — the top 40 neighborhoods across every
  town where a typical home is ≤ $600k, lit up on the map and ranked in a
  leaderboard. Tap any to drill straight in.
- **Budget filter** (All / ≤$600k / $400–600k / ★ Sweet) on the town layer.

## ⚡ Future potential (forward-looking)

A separate **forward** score — pick "⚡ Future potential" in *Color by* (towns) or
the "⚡ Future" map-color toggle (neighborhoods). Unlike the opportunity score
(which rewards *past* appreciation), this estimates the **next** five years:

- **+ new transit catalysts** (South Coast Rail to New Bedford/Fall River/Taunton,
  GLX in Somerville/Medford) — concrete, dated, not-yet-priced-in
- **+ affordability headroom** (cheaper = more room to run), walkability, town
  demand growth, jobs, universities, "good bones still cheap" value gap
- **− mean-reversion penalty** for neighborhoods that already spiked

Top forward picks land on the South Coast Rail corridor (New Bedford, Fall River),
Worcester, and Lowell — *not* the past winners that already ran up.

## 💰 Rentability (landlord view)

A score for **how well you'd do renting the place out** — now and forward — using
**real rents** from the **Zillow Observed Rent Index (ZORI)**:

- **Gross rental yield** = annual ZORI rent ÷ typical home value. The cash-flow core.
- **Rentability (now)** = even blend of *yield* + *rental demand* (universities,
  transit, jobs, walkability, young-buyer pull, in-migration) — who will rent it and
  keep rents rising. Normalized 0–100 statewide.
- **Rent outlook (5-yr)** = forward score from rent-growth momentum + demand + new
  transit catalysts + affordability headroom; surfaced as Strong / Moderate / Soft / Weak.

132 MA cities have a measured ZORI rent; the rest get a rent **estimated from their
county's yield** applied to their home value (flagged "est."). The 3-yr rent-change
figure is only computed where a full 36-month ZORI history exists; smaller towns
inherit a county-median estimate, shown with a leading `~`. Top landlord plays are
the high-yield Gateway cities — **Worcester, New Bedford, Lowell, Boston, Lynn** —
while luxury/seasonal towns (Weston, Provincetown) score low on yield.

## 🏛 Local government

Each town panel shows its **form of government** (curated from MA DLS / charters —
City Mayor-Council, City Council-Manager, Town Council, or Representative / Open Town
Meeting) plus quick links to the **official site**, a **Wikipedia overview**, and a
**property-tax & budget** search, so engaging the local government is one click away.

## ⚡ Combine factors (multi-select color)

*Color by* is a checklist. Pick one — Overall opportunity, ⚡ Future potential,
💰 Rentability, Rent outlook, or any of the 10 criteria — or **tick several** and the
map colors by their **even-weighted average** (all already on a 0–100 scale). The
legend and tooltips switch to "Combined · N factors."

## Performance

- **Light first paint + detail sidecars:** the map paints from a light
  `towns.geojson` (~0.55 MB) carrying only what the choropleth + panel header need.
  The drill-only payload — per-town reasons & cool spots, and per-neighborhood spots —
  lives in `town_detail.json` and `neighborhoods_detail.json`, fetched in the
  background after first paint. This roughly **halves the blocking download** (was
  ~1.3 MB).
- **Versioned caching:** the build writes `data/manifest.json` with a content hash of
  all four data files; the page loads each as `…?v=<hash>`, so the browser **caches
  between loads** and only re-downloads when the data actually changes.
- **Lazy neighborhoods:** the statewide town layer paints first; neighborhood geometry
  + the detail sidecars stream in afterward (drill-in waits only if you click early).
- **Smaller files:** geometry coordinates are rounded to ~1 m, dead fields are dropped,
  and JSON is written without whitespace.

## The 10 criteria & weights (appreciation tilt)

| Criterion | Weight | Data quality | Source |
|-----------|:--:|:--:|--------|
| Rail transit access & expansion | 16 | measured | MBTA GTFS stations (+ curated GLX/South Coast Rail flags) |
| Population growth / in-migration | 14 | measured | U.S. Census decennial 2010 → 2020 |
| Major-employer expansion nearby | 13 | curated | Documented recent/ongoing employer growth hubs |
| School quality & trend | 12 | curated | DESE MCAS/accountability reputation tiers |
| Trendy / young-buyer demand | 11 | proxy | Zillow price momentum + café/brewery density + density |
| Proximity to top universities | 9 | measured | Distance to curated list of 34 MA universities |
| Walkability | 8 | proxy | Population density (pop / land area) |
| Vacation / second-home demand | 7 | proxy | Cape & Islands / Berkshires / coastal classification |
| Water frontage & beach access | 5 | measured | Census water area + OSM beaches (+ curated beach tier) |
| Green space & local culture | 5 | measured | OSM parks, nature reserves, museums, theaters |

**Data-quality flags** are shown throughout the UI:
🔵 measured (real per-town data) · 🟡 proxy (computed stand-in) · 🟣 curated (judgment-based table).

## Methodology

1. Each criterion is reduced to a raw per-town metric, then **normalized 0–100**
   across all 351 towns (percentile rank for continuous metrics; fixed tier maps
   for curated tables).
2. The composite = **80 % of the weighted 10-criteria score + 20 % of the town's
   realized 5-yr appreciation** (Zillow price growth, or pop-weighted FHFA tract
   index where Zillow is thin) — folding the neighborhood-level price data back
   into the town ranking. Towns are then **ranked 1–351**.
3. **Budget fit** uses Zillow ZHVI typical home value: `in` = $400–600k,
   `below` = <$400k, `above` = >$600k. A **★ sweet spot** = in/under budget *and*
   top-30% opportunity score.
4. **Reasons** are generated from the same metrics: a town's strongest signals
   become "reasons to buy," its weakest become "reasons not to buy," each printed
   with its real value and criterion tag. If fewer than 10 genuine signals exist
   on a side, only the real ones are shown.

## Honest limitations

- **Census ACS** (second-home %, age mix, income) now requires an API key, so
  those criteria use transparent **proxies** rather than the exact ACS variables.
- **Schools** and **employer expansion** are **curated** reputation tiers, not a
  live academic feed. Highest-value upgrade: wire in live DESE MCAS/accountability
  data and a district→town crosswalk.
- **No "n/a" left:** the few towns Zillow misses get a real price from **MassGIS
  median assessed value** (flagged "assessed est."); the ~10 % of neighborhoods
  FHFA suppresses get appreciation **estimated from their town/county** (shown
  with a `~`). Everything visible is real or a clearly-labeled estimate.
- Scores rank *relative* opportunity within MA on these 10 criteria + realized
  appreciation — a research starting point, not financial advice.

## Files

```
index.html                     self-contained Leaflet map (loads the data files below)
build_data.py                  town scoring engine -> towns.geojson + town_detail.json
build_neighborhoods.py         neighborhoods.geojson + neighborhoods_detail.json
curated.py                     curated tables (universities, transit, coastal, gov, ...)
fetch_*.py                     data fetchers (boundaries, population, transit, osm,
                               osm_attractions, tracts, places). fetch_acs.py is a
                               legacy fetcher, unused since ACS started requiring a key.
data/towns.geojson             light town layer (geometry + scores + rentability + gov)
data/town_detail.json          per-town reasons + cool spots (lazy)
data/neighborhoods.geojson     neighborhood layer (tracts + appreciation + insights)
data/neighborhoods_detail.json per-neighborhood cool spots (lazy)
data/manifest.json             content-hash cache version
data/raw/                      downloaded/intermediate source files
```
