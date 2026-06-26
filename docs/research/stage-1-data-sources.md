# Stage 1 — Data-Source Landscape (Source Catalog)

*Research output for Workplan Stage 1. Compiled June 19, 2026. Pilot region: US mid-Atlantic / Virginia.*

> **STATUS: ACTIVE — reference catalog.** Still the working source catalog. The recommended Phase-0 stack below has shipped (corpus pipeline Epic 012, live adapters + Valhalla Epic 013, commons fork Epic 010). **Read when** you need a source's format/auth/license/authority tier.

> **What this is.** The whole system is *verified synthesis over open data*, so before we design the graph schema (Stage 2), the corpus pipeline (Stage 3), or the confidence model, we need to know what raw material actually exists — its shape, quality, license, and rate of change. This catalogs every evaluated source, classifies each **corpus** (slow/structural, bulk-ingested) vs. **live** (fast/ephemeral, fetched JIT), ranks authority, summarizes license obligations, identifies East-Coast coverage gaps, and assesses **conflation feasibility** (the meatiest unknown). It closes with a recommended Phase-0 source stack.

> **Confidence legend.** ✅ independently verified (primary source or this author cross-checked) · 🟢 high (multiply-sourced) · 🟡 medium (single-source / search-snippet — verify before coding) · 🔴 flagged risk / changing.

> **Methodology note.** Research was fanned out across six parallel agents (OSM; USFS+USGS; NPS+PAD-US+RIDB; live conditions; state/local + proprietary-ToS; conflation). Many `.gov`/ArcGIS pages block automated fetchers (HTTP 403), so several details rest on search-result extracts of the authoritative pages; the OSM Merge constants were recovered by cloning the repo and reading source. The three most build-shaping claims (USGS API sunset, ODbL share-alike, GNIS trail-class removal) were independently re-verified by the author. **Before writing ingestion code, re-confirm every 🟡 item against the live endpoint.**

---

## 0. TL;DR — the recommended source stack

**For a Virginia/mid-Atlantic Phase-0 pilot, the open-data stack is:**

| Role | Source(s) | Why |
|---|---|---|
| **Geometry spine** | **OpenStreetMap** (Geofabrik VA extract) | Best breadth incl. local/regional/private trails federal data omits; richest names + route relations |
| **Authoritative overlay (federal)** | **USFS NFS Trails** (GWJ NF) · **NPS Public Trails** (Shenandoah) | Official existence, names/numbers, *legal allowed-use* OSM can't be trusted for |
| **Authoritative overlay (state)** | **VA Open Data / Fairfax County** | Official status for state/county trails; clean license (state portal) vs. encumbered DCR DB |
| **Land manager / "is it public"** | **PAD-US 4.1** | One standardized ownership + public-access schema across all jurisdictions |
| **Permits / campsites (corpus)** | **Recreation.gov RIDB API** | Canonical federal permit/facility inventory (incl. Shenandoah backcountry) |
| **Elevation / grade** | **USGS 3DEP** (1/3 arc-sec baseline, 1 m where available) | Public-domain DEMs; compute gain/grade per trail |
| **Live weather + alerts** | **NWS api.weather.gov** | Authoritative, keyless, GeoJSON; flash-flood/red-flag alerts are the safety layer |
| **Live water** | **USGS Water OGC API** (`api.waterdata.usgs.gov/ogcapi`) | Streamflow/gage for crossings — **build on the new API, not legacy** |
| **Live fire / smoke** | **NASA FIRMS** + **EPA AirNow** | Hotspots (source) + AQI/PM2.5 (downwind impact); VA is in FIRMS' lowest-latency zone |
| **Drive-time routing** | **Valhalla** (self-hosted) | Native time-based **isochrones** for "hikes within N min of me"; OSM-based, MIT |

**Five findings that change the plan:**
1. **Conflation is tractable, not research-grade.** A purpose-built tool — **OSM Merge**, from the OSM-US Trails Stewardship Initiative — already conflates OSM + USFS + NPS + USGS trail data as a *human-in-the-loop* workflow. For a few dozen named trails in one region, "good enough" conflation is hours of review, not a research project. *(§7)*
2. **There is no shared cross-source trail ID.** GNIS dropped its "trail" class in 2021. Matching must be **name + ref + geometry**, with human review. This shapes the Stage-2 schema directly. *(§7)*
3. **The ODbL escape hatch is architectural.** Share-alike attaches to the *database* layer, not app output. A public commons that blends OSM with other data likely forces the whole derivative to ODbL — *unless* layers are kept separate ("Collective Database") or we expose only rendered "Produced Works." *(§5)*
4. **A live-source sunset to design around now.** The legacy USGS streamflow API decommissions ~Q1 2027 — build on the new OGC API from day one. *(§3, §5)*
5. **Every proprietary app is legally off-limits** (Strava, AllTrails, Hiking Project/onX, Gaia, Komoot). The open-data path isn't just preferred — it's the only lawful one for an AI product. *(§5, Appendix B)*

---

## 1. Master source catalog

> C = Corpus (bulk, slow, refresh on a cadence) · L = Live (JIT, never persisted as graph nodes) · C/L = both, split by use.

| Source | Data | C/L | Format | Access / auth | License | Freshness | Authority |
|---|---|---|---|---|---|---|---|
| **OpenStreetMap** | Trail geometry, names, surface, access, dog tags | **C** | `.osm.pbf` (Geofabrik), Overpass | Bulk extract (no key); Overpass (rate-limited) | **ODbL 1.0** (attribution + share-alike) | Geofabrik daily; live DB continuous | Geometry: med-high · Attrs: low-med · Rules: **low** |
| **USFS NFS Trails (EDW)** | Official NFS trails, allowed-use, MVUM | **C** | Shapefile, FGDB, GeoJSON via ArcGIS | REST/download (no key) | Public domain (US Gov) | Rolling, per-forest | **Tier 1** for existence + legal use; mid for geometry |
| **USGS Nat'l Digital Trails (NTD)** | Aggregated national trails + source provenance | **C** | Shapefile, FGDB, GeoPackage; REST/WMS/WFS | TNM download / REST (no key) | Public domain | Refresh-by-source (~April 2026 noted) | Mid — a re-host/crosswalk, not canonical |
| **USGS 3DEP** | Elevation DEMs (gain/grade) | **C** | COG GeoTIFF | AWS `prd-tnm` (no key), TNM, OpenTopo, EPQS | Public domain | Static; S1M 1 m in progress | **Tier 1** for elevation |
| **NPS Data API** | Park metadata, **alerts**, things-to-do | **C/L** | JSON | `developer.nps.gov`, **key** (`X-Api-Key`), 1000/hr | Public domain | Re-ingest ~2 h | **Tier 1** for park content |
| **NPS GIS (Public Trails / Boundary)** | Park trail centerlines, boundaries | **C** | Shapefile, FGDB, GeoJSON; REST/WMS/WFS | ArcGIS hub / `mapservices.nps.gov` (no key) | Public domain | "Frequently updated" | **Tier 1** for NPS-unit geometry |
| **PAD-US 4.1** | Protected lands, manager, public-access | **C** | FGDB, GeoPackage, Shapefile, GeoJSON | USGS GAP download / ScienceBase / REST (no key) | Public domain | ~Annual (4.1 = Mar 2025) | **Tier 1** for ownership/access |
| **Recreation.gov RIDB** | Permit/campsite **requirements**, facilities | **C** | JSON (+ bulk CSV/JSON) | `ridb.recreation.gov/api`, **key**, ~50/min | **Access Agreement** (attribution-style, *not* pure PD) | Frequent | **Tier 1** corpus (federal only) |
| **Recreation.gov availability** | Real-time permit/campsite availability | **L** | JSON (undocumented) | Website backend, reverse-engineered | Website ToS (no scraping blessing) | Real-time | 🔴 unofficial / unstable |
| **NWS api.weather.gov** | Forecast, hourly, **alerts/warnings** | **L** | GeoJSON, CAP XML | Keyless (**User-Agent required**), fair-use | Public domain | Hourly-ish; alerts real-time | **Tier 1** weather |
| **USGS Water (OGC API)** | Streamflow (00060), gage height (00065) | **L** | JSON/GeoJSON | `api.waterdata.usgs.gov/ogcapi` (token recommended) | Public domain | ~15 min | **Tier 1** water |
| **NASA FIRMS** | Active-fire / thermal hotspots | **L** | CSV/JSON | Area API, **MAP_KEY** (free), 5000/10 min | CC0 / no restriction | URT <60 s (VA in URT zone) | **Tier 1** fire detection |
| **EPA AirNow** | AQI incl. wildfire PM2.5 | **L** | JSON/XML/CSV | `airnowapi.org`, **key**, 500/hr/service | EPA terms (**label "preliminary"**) | Hourly obs / daily forecast | **Tier 1** AQI (sparse backcountry) |
| **VA Open Data / VGIN** | State/local trails, parcels, conservation lands | **C** | Shapefile/GeoJSON; ArcGIS REST | Portal + REST (no key) | **Per-dataset** (ODC-BY for some) | Varies; parcels quarterly | Tier 2 (state authoritative where present) |
| **VA DCR Conservation Lands** | Protected-lands boundaries | **C** | Shapefile, ArcGIS service | Download / VGIN | 🔴 **Restrictive** — signed agreement, **no redistribution / no for-profit** | Quarterly | Tier 1 for VA conservation lands (but encumbered) |
| **Fairfax County Open Data** | County park trails | **C** | Shapefile/GeoJSON/CSV/KML; REST | ArcGIS Hub (no key) | County copyright + permission (not a named open license) | Varies | Tier 1 for county trails |
| **A.T. Centerline (NPS/APPA)** | Appalachian Trail centerline + features | **C** | Shapefile, FGDB | ScienceBase / PASDA / data.gov | Public domain | GPS-surveyed, static | **Tier 1** for the A.T. |
| **PATC** | DC/VA backcountry trail data | — | Avenza / print | Commercial | 🔴 Closed — reference only | Curated | Authoritative but not ingestible |
| **Valhalla / OSRM** | Drive-time routing / isochrones | **C** (self-host) | Engine over OSM | Self-host (MIT/BSD) | Engine permissive; data ODbL | Rebuild w/ OSM | n/a (compute) |
| *Aux:* NOAA CDO, CO-OPS, USGS Earthquake, CDC/JHU Lyme, sunrise/sunset, avalanche.org | Climate, tides, quakes, Lyme, daylight, avalanche | mixed | JSON/GeoJSON | mostly keyless/light | mostly PD; avalanche.org **unspecified** | varies | situational — see Appendix A |

---

## 2. Corpus vs. Live split

The crawl-vs-fetch decision resolves cleanly by rate of change (Decision Log §4).

**CORPUS (bulk-ingest, index ahead, refresh on a cadence; lives in the graph):**
OSM geometry · USFS NFS Trails · USGS NTD · USGS 3DEP · NPS GIS (trails/boundaries) · NPS *static* content (parks, campgrounds, things-to-do) · PAD-US · RIDB permit/campsite **requirements** · VA/VGIN/Fairfax state-local trails · A.T. centerline.

**LIVE (fetch JIT for the shortlist only; never persisted as nodes to expire — CLAUDE.md rule #3):**
NWS forecast + **alerts** · USGS streamflow/gage · NASA FIRMS hotspots · EPA AirNow AQI · RIDB **availability** · NPS **alerts/road-events**.

**Design rule that falls out:** store *identity + lat/lon* (and a resolved grid/gauge/site/permit id) in the graph; fetch the live overlay at decision time. For live sources with sparse coverage (AirNow monitors, USGS gauges thin in backcountry), **store the nearest-site id + distance** so the UI can disclose how representative a reading is. *(This is the confidence model's "freshness" axis in action.)*

---

## 3. Per-source detail

### 3.1 Corpus — geometry & structural

**OpenStreetMap** 🟢 — *the geometry spine.*
- **Access:** Geofabrik publishes per-**state** `.osm.pbf` extracts (Virginia, West Virginia, Maryland… — no "mid-Atlantic" cut; assemble from states), regenerated **daily** with daily `.osc` diffs for incremental sync. Use the **`.osm.pbf`** (full tags + route relations), *not* the free shapefiles (limited attribute subset). Overpass API is read-only and slot-rate-limited (180 s default timeout) — for small ad-hoc queries, not bulk. ([Geofabrik VA](https://download.geofabrik.de/north-america/us/virginia.html), [Overpass wiki](https://wiki.openstreetmap.org/wiki/Overpass_API))
- **Filter to hiking:** ways `highway=path|footway|track|bridleway|steps`; difficulty `sac_scale`, `trail_visibility`; route relations `type=route` + `route=hiking` (+ `superroute` for long trails). ([highway=path](https://wiki.openstreetmap.org/wiki/Tag:highway%3Dpath))
- **Quality:** strong in popular areas (the A.T. through Shenandoah/GWJ is well-mapped as relations); patchy elsewhere; US trail tagging is *inconsistent* (the OSM-US Trails Stewardship Initiative exists to fix exactly this). **`sac_scale`/`surface` are sparse in the US; `dog=*`/leash tags are unreliable — do NOT use OSM as the source of truth for dog rules.** Defer to the land manager. 🔴
- **License:** **ODbL 1.0** — see §5.
- **Authority:** geometry med-high (often *more* complete/current than agencies, but includes unofficial "social" trails — filter on `informal=yes`/`access`); attributes low-med; regulatory low.

**USFS NFS Trails (Enterprise Data Warehouse)** 🟢 — *authoritative federal allowed-use.*
- **Access:** `apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublish_01/MapServer/0`; bulk Shapefile/FGDB via FSGeodata Clearinghouse + GeoJSON via ArcGIS Hub. No key. Companion `EDW_MVUM_01` (motor-vehicle use) and `EDW_RecreationOpportunities_01` (rec sites). 🟡 confirm field roster via `?f=json`.
- **Attributes (3 escalating tiers, per-forest):** Centerline (`TRAIL_NO`, `TRAIL_NAME`, geometry) → Basic (type/class/surface/length) → Mgmt (managed-use + seasonal allowed/prohibited). Keys: **`TRAIL_CN`** (34-char control number = stable PK), `GLOBALID`, `GIS_MILES`.
- **VA coverage:** George Washington & Jefferson NF (one admin unit) — western VA, A.T. corridor, Mt. Rogers NRA. **NFS land only** (not Shenandoah, not state/local).
- **Authority:** Tier 1 for existence + legal allowed-use + official name/number; *mid* for geometry (OSM community documents agency lines mislocated up to ⅓ mile). Use to enrich, not necessarily override, OSM centerlines. ([USFS NFS Trails](https://data-usfs.hub.arcgis.com/datasets/usfs::national-forest-system-trails-feature-layer/about))

**USGS National Digital Trails (NTD)** 🟢 — *a pre-merged crosswalk, not canonical geometry.*
- **Access:** TNM Downloader + dedicated REST `partnerships.nationalmap.gov/arcgis/rest/services/USGSTrails/MapServer/0` (`TrailsSegment`); Shapefile/FGDB/**GeoPackage**. No key.
- **Key value:** carries **source-provenance fields** — `permanentidentifier`, plus `sourceoriginator` / `sourcedatasetid` / **`sourcefeatureid`** — i.e. USGS already did one multi-agency merge and recorded join keys. 🟡 *Verify which USFS field populates `sourcefeatureid` (likely `TRAIL_CN`) on GWJ-NF records before relying on the NTD↔EDW join.*
- **Caveat:** USGS **aggregates, it does not deeply conflate** — it dedupes + prunes road-coincident trails and re-hosts NPS/USFS/BLM/state geometry. So treating NTD + USFS as independent sources surfaces the **same records** (good for cross-check, not independent confirmation). Completeness verified only to 2022 (277k mi, ~36 states); **partial — check Virginia in the Trails Explorer.** 🔴
- **Standard:** follows Federal Trail Data Standards (FGDC-STD-017-2011) — common vocabulary, *not* a cross-agency GUID.

**USGS 3DEP elevation** 🟢 — *elevation/grade.*
- **Resolutions:** 1/3 arc-sec (~10 m) nationwide baseline ✅; 1 m where lidar exists (good but incomplete in VA — check tile-by-tile); seamless 1 m (S1M) in production since mid-2025.
- **Access:** AWS public bucket `prd-tnm` as **COG** (range-readable, no key); TNM/OpenTopography; **EPQS** point API (`epqs.nationalmap.gov`) for one-offs (interpolated, "not official", ~0.53 m RMSE). Public domain.
- **Pipeline:** densify trail line (~5–10 m) → sample DEM (bilinear) → smooth (3–5 m threshold to suppress noise) → sum positive deltas for gain. Record which resolution was used per trail (reproducibility = a confidence input).

**NPS — two channels, do not conflate** 🟢
- **Content API** (`developer.nps.gov/api/v1`): keyed (`X-Api-Key`, free), **1000 req/hr** (HTTP 429 over), JSON. Parks/alerts/campgrounds/thingstodo/places. **Returns a representative lat/lon, NOT polygons.** Alerts re-ingest ~2 h. ✅ key+limit
- **GIS** (separate): boundaries + `NPS Public Trails` centerlines (`TRLNAME`, `TRLSTATUS`, `TRLSURFACE`, `TRLUSE`, `PUBLICDISPLAY`, `UNITCODE`) via ArcGIS hub / `mapservices.nps.gov` REST/WMS/WFS. **No length/difficulty/elevation** (derive); some segments withheld (`PUBLICDISPLAY=No`); completeness varies by park (the weakest-quality federal trail layer). 🟡
- **VA units:** `shen` (Shenandoah, ~500 mi incl. ~101 mi A.T.), `blri` (Blue Ridge Pkwy), `appa` (cross-check vs ATC centerline), `prwi`, `gwmp`, `cho h`, `hafe`, `asis`. Query multiple `stateCode`s (VA/DC/MD/WV/PA) to catch border units.

**PAD-US 4.1** 🟢 — *the "whose land / is it public" base layer.*
- **Latest 4.1 (March 2025)** ✅; public domain; FGDB/GeoPackage/Shapefile/GeoJSON; download/ScienceBase/REST, no key.
- **Key attributes:** `Mang_Name`/`Mang_Type` (manager), `Own_Name`/`Own_Type`, `Des_Tp` (designation), `Unit_Nm`, **`Pub_Access`** (Open/Restricted/Closed/Unknown — *policy, not live status*), `GAP_Sts`, `Agg_Src`.
- **VA:** well-stewarded (PAD-US ingests VA DCR data) — federal + state lands complete; **local/county + private easements incomplete (~50% nationally).** Use as the base public-land filter; overlay agency-direct sources where currency matters.

**Recreation.gov RIDB (corpus side)** 🟢
- **`ridb.recreation.gov/api/v1`**, free key (header `apikey`), **~50 req/min** 🟡. Hierarchy `Organization → RecArea → Facility → (Campsite | PermitEntrance | Tour)`. **Both campgrounds and permits are Facilities;** permit *requirement* is inferred from a permit-type Facility (no tidy flag). Fees are **free-text, not numeric.** No structured "trail" object — pair with NPS/USFS/OSM geometry. Bulk CSV/JSON at `/download`.
- **License:** RIDB **Access Agreement** — attribution-style (encouraged, not mandated), commercial OK, **mandatory no-endorsement clause** — *not pure public domain.* Distinct from the more restrictive recreation.gov **website ToS** (which does not bless scraping availability). 🟡
- **VA:** Shenandoah backcountry permits **moved to recreation.gov Jan 11, 2024** (~$6 + $9/person); GWJ NF campgrounds in RIDB.

**State / local (VA)** 🟡 — *fills the federal gap.*
- **VA Open Data Portal** (`data.virginia.gov`, CKAN): per-dataset license (ODC-BY on part of the catalog). Note scope traps — "Recreation Park Trails" is **Alexandria-only**; the statewide "Trails" layer is a **base-map planimetric** layer (foot/bike paths + driveways), not recreation-grade.
- **VGIN** (`vgin.vdem.virginia.gov`): statewide **parcels** (quarterly) for ownership; serves DCR Conservation Lands; "Paths to the Future" multimodal FeatureServer.
- **VA DCR Conservation Lands DB:** authoritative for VA conservation lands **but 🔴 license-encumbered** — signed agreement, **no third-party redistribution, no for-profit.** Usable for personal/reference; **cannot be baked into a distributed product.**
- **Fairfax County Open Data:** clean local-trail source (Shapefile/GeoJSON/REST) for the NoVA core; county copyright + permission-to-reproduce (verify for redistribution).
- **A.T. centerline:** authoritative line = **NPS/APPA**, public-domain federal data via ScienceBase/PASDA/data.gov (prefer over ATC's "simple agreement" data).
- **PATC:** 🔴 closed (Avenza/print) — reference only.

### 3.2 Live — conditions

**NWS `api.weather.gov`** 🟢 — keyless (**`User-Agent` with contact required**), GeoJSON. Flow: `/points/{lat},{lon}` (≤4 decimals) → `forecast` / `forecastHourly`. **Alerts** (the safety layer): `/alerts/active?point={lat},{lon}` (flash-flood, red-flag, winter-storm, heat). Honor `Cache-Control`/`Last-Modified`. Public domain. VA offices: LWX (N. VA/DC), RNK, AKQ.

**USGS Water — build on the NEW API** 🔴→✅ — params `00060` (discharge), `00065` (gage height). **Legacy `waterservices.usgs.gov` decommissions ~Q1 2027** (degradation possibly from Aug 2026) — ✅ verified. **Build on `api.waterdata.usgs.gov/ogcapi`** (OGC API-Features, JSON/GeoJSON; keyless but free token recommended for rate). Resolve the nearest gauge by bbox/state + `siteType=ST`. ~15-min cadence. Public domain. ([USGS decom notice](https://waterdata.usgs.gov/blog/api-waterservices-decom/), [migration guide](https://api.waterdata.usgs.gov/docs/ogcapi/migration/))

**NASA FIRMS** 🟢 — Area API `…/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{DAYS}`. Free MAP_KEY (instant, email). **5000 transactions / 10 min.** MODIS + VIIRS. **VA is in the Ultra-Real-Time (<60 s) zone** (Hampton, VA antenna). CC0. *Caveat: detects thermal anomalies, not fires/smoke — false positives; cross-check AirNow + InciWeb.*

**EPA AirNow** 🟢 — `airnowapi.org/aq/observation/latLong/current/` etc.; free key; **500 req/hr/service**; JSON/XML/CSV. Hourly obs / daily forecast — **cache within the hour.** 🔴 Data is **preliminary** (must be labeled); coverage thins in backcountry. Fire & Smoke Map has no clean JSON API (use main API for PM2.5).

---

## 4. Authority-tier ranking (feeds the confidence "authority" axis)

Authority is **per-data-kind**, not per-source — a source can be Tier 1 for one attribute and Tier 3 for another. This *is* the confidence model's authority axis (Decision Log §7).

| Data kind | Tier 1 (authoritative) | Tier 2 | Tier 3 |
|---|---|---|---|
| **Trail existence (official)** | USFS / NPS / state agency | USGS NTD (re-host) | OSM |
| **Trail geometry (precision/currency)** | OSM (where surveyed) · A.T. = NPS/APPA | USFS / NPS GIS | USGS NTD |
| **Legal allowed-use (bikes/horses/motor)** | USFS Mgmt tier · NPS | PAD-US (`Pub_Access`, policy-level) | OSM `access`/`dog` 🔴 |
| **Land manager / public access** | PAD-US · agency-direct | state conservation DBs | — |
| **Elevation / grade** | USGS 3DEP (1 m > 1/3 arc-sec) | — | — |
| **Permits / campsites** | Recreation.gov RIDB | agency pages | — |
| **Weather / alerts** | NWS | — | — |
| **Streamflow** | USGS Water | — | — |
| **Fire / AQI** | FIRMS · AirNow | — | PurpleAir (non-EPA) |

**Rule of thumb for the engine:** *OSM for "what physically exists and connects," government for "what's official, legal, and who manages it," 3DEP for elevation, live APIs for conditions.* Never trust OSM for dog/leash/closure facts.

---

## 5. License & legal obligations

### 5.1 OSM / ODbL — the load-bearing one ✅
ODbL 1.0 distinguishes (verified against the OSMF Legal FAQ):
- **Produced Work** (a rendered map, an app screen, a route suggestion) — owes **attribution only**, may be licensed however we like. *"Using the Database… to create a Produced Work does not create a Derivative Database for purposes of Section 4.4."*
- **Derivative Database** (we adapt/extend/conflate OSM into a new database) — if **publicly conveyed**, must be released under **ODbL** (share-alike), machine-readable, with alterations documented.

**Implications by phase (Decision Log §18 confirmed):**
- **Phase 0–1 (personal/household, unpublished):** share-alike is triggered by *public conveyance*. Private use → effectively no obligations. We can ingest, conflate, and transform OSM freely. Attribution is good practice if we ever show maps to others.
- **Phase 3 (public commons):** publishing an aggregated trail database substantially built on OSM = a **Derivative Database** → forces the whole thing to ODbL **unless** we use one of two escape hatches:
  1. **Collective Database** — keep OSM-derived layers and other layers *separate and non-cross-referencing* per feature-type/region (the "Horizontal Map Layers" guideline). The moment we *merge/conflate* OSM geometry with USFS attributes into one interlinked record, that record is a Derivative Database.
  2. **Produced Works only** — expose rendered output / recommendations, not the database.
- 🔴 **This is a Stage-2 schema decision.** The commons is exactly a conflation of OSM + government data, which lands it squarely in "Derivative Database." If we ever want the commons public *without* ODbL share-alike on the whole thing, the schema must keep the OSM-derived layer cleanly separable — or accept ODbL on the published commons (which may be fine).

### 5.2 The rest
- **Public domain (clean):** NWS, USGS (all), USFS, NPS, PAD-US, A.T. centerline (NPS/APPA), USGS Earthquake, NOAA. Attribution is courtesy, not required.
- **Attribution-style / terms apply:** **Recreation.gov RIDB** (Access Agreement, no-endorsement clause — *not* pure PD); **NASA FIRMS** (CC0, citation encouraged); **EPA AirNow** (must label data "preliminary").
- **🔴 Encumbered — do not redistribute:** **VA DCR Conservation Lands** (signed agreement, no third-party/for-profit redistribution). **Fairfax County** (county copyright + permission — fine personal, verify for redistribution).
- **🔴 Off-limits (no lawful programmatic/AI path):** Strava (explicit AI ban incl. RAG/embeddings/context-window; single-user-display; competing-app; 7-day cache), AllTrails (no API; anti-scrape ToS actively enforced + DataDome), Hiking Project/onX (API deprecated 2020), Gaia/onX Backcountry (no public API), Komoot (partner-only). **See Appendix B.** This validates Decision Log §10's "never Strava" and §25's open-data stance — it's the *only* legal path for an AI product.
- **Routing engines:** OSRM (BSD), Valhalla (MIT) — permissive; the underlying OSM data still carries ODbL attribution.

### 5.3 Garmin (forward-looking, Phase 1)
Out of Stage-1 scope (not a trail source) but noted: the community `python-garminconnect` library is unofficial / arguably against Garmin ToS — fine personal, a risk if multi-user. Keep swappable (Decision Log §18). Coros's official MCP is the clean contrast.

---

## 6. East-Coast / mid-Atlantic coverage gaps

**Structural gap: federal data only covers federal land.** In the mid-Atlantic, the big federal blocks (Shenandoah NP, GWJ NF, Blue Ridge Pkwy) are real but a *minority* of total trail mileage. The day-hikes that matter most for a personal planner — NoVA/DC regional, county, urban-edge, rail-trail, and land-trust preserves — are largely **absent from federal sources.**

| Category | Federal data | State portals | OSM |
|---|---|---|---|
| National Forest / Park trails | ✅ authoritative | partial | ✅ good |
| State park/forest trails | ❌ (only if USGS ingested the state) | ✅ where present | ✅ |
| County / regional / municipal | ❌ **biggest gap** | sometimes | ✅ **best** |
| Urban greenways / rail-trails | patchy | sometimes | ✅ |
| Private / land-trust / HOA | ❌ never | inconsistent | ✅ only option |

**Net:** **OSM for breadth + state/county open data for authority + federal for the federal blocks.** USGS NTD is partial (~36 states; verify VA). The gap is exactly where OSM is strongest — which is *why* OSM is the spine, not an afterthought.

---

## 7. Conflation feasibility (the meatiest unknown) — VERDICT: tractable

**Bottom line:** merging the *same physical trail* across OSM/USFS/USGS/NPS is the hardest unknown, but for a small pilot it is **not research-grade.** A purpose-built, human-in-the-loop tool already targets *exactly* this scope, the matching math is off-the-shelf, and published methods hit ~95–99% precision when name is combined with geometry. **The dominant difficulty is bad source data, not the matching algorithm.**

### 7.1 No shared cross-source ID ✅
GNIS was the one candidate cross-walk — but USGS **archived the entire "trail" feature class on Aug 25, 2021** (verified), and GNIS stored linear features as just two points anyway. So `gnis:feature_id` is dead for trails. The remaining keys are **stable *within* a source, not across** them:

| Source | Stable internal PK | Human join keys | Segmentation model |
|---|---|---|---|
| OSM | element id (*unstable across edits/splits*) | `name`, `ref`, `ref:usfs`, `operator`, `wikidata` | ways grouped into `route`/`superroute` relations |
| USFS | **`TRAIL_CN`**, `GLOBALID` | `TRAIL_NO`, `TRAIL_NAME`, admin unit | BMP/EMP linear-referenced rows |
| USGS NTD | `permanentidentifier` | crosswalked name/number; **`sourcefeatureid`** | aggregated NTD segments |
| NPS | `OBJECTID`/`GLOBALID` (*row id, not permanent*) | `TRLNAME`, `UNITCODE`, `MAINTAINER` | per-unit centerline segments |

→ **Matching is name + ref + geometry, with mandatory human review.** Internal PKs are for *re-syncing the same source over time*, not cross-source joins. The one usable cross-source bridge is **USFS `TRAIL_CN` ↔ USGS `sourcefeatureid`** (🟡 verify).

### 7.2 The segmentation problem → directly shapes the Stage-2 schema
The same trail exists at three granularities, and splits **don't align across sources**: a **named route** (OSM relation / USFS shared TRAIL_NO / NPS TRLNAME) vs. **segments** (OSM ways / USFS BMP-EMP rows / NPS centerline pieces) vs. **junctions/trailheads**. This validates the project's graph plan:

```
(:CanonicalTrail {name, region, length})         // the named route we present
  -[:SAME_AS {source, source_id, confidence,     // provenance edge per source record
              match_method, matched_on, reviewed_by}]->
  (:SourceRecord {source:"USFS", trail_cn, raw_name, geom})
  (:SourceRecord {source:"OSM",  osm_id, ref, name, geom})
  (:SourceRecord {source:"NPS",  objectid, trlname, geom})
(:CanonicalTrail)-[:HAS_SEGMENT]->(:Segment {geom, source_seg_ids[]})
(:Segment)-[:STARTS_AT|ENDS_AT]->(:Junction)
(:Trailhead)-[:ACCESSES]->(:CanonicalTrail)
```
Design choices the research supports: **conflate at the *route* level first** (name+ref), geometry confirms; **`SAME_AS` carries full provenance** (source + its own PK + match method + confidence + review flag) — satisfying "which source said what" and enabling independent re-sync; **keep segments a separate layer** storing each source's segment ids; **never auto-merge conflicting attributes** (esp. access/usage — USFS↔OSM access definitions differ) — surface them per source so the UI can say "USFS says bikes discouraged; OSM says no restriction."

### 7.3 Technique & tooling
- **Math:** buffer-overlap (workhorse) + **Hausdorff** (line similarity) + **Fréchet** (respects shape/order — better for loops) + **string distance** on names; combine into a weighted score, threshold, triage. Network/node-arc (junction-aware) is the "right" model for trail networks; KRAFT (GNN+MILP) is the research frontier — **overkill for v0.**
- **Accuracy benchmark (directional, from a road-network study):** ~94.7% precision / >81% recall on geometry alone → **99.4% precision when name strings are added.** Lesson: **geometry + name beats either alone**, and a residual error band always needs review.
- **The tool to adopt: OSM Merge** ✅ (cloned + source-read) — GPLv3, an OSM-US project, purpose-built to conflate **USFS/MVUM, USGS topo `Trans_TrailSegment`, NPS, BLM** trail data onto OSM. Matches on `name`/`ref`/`ref:usfs` with **fuzzy threshold 80** (`thefuzz`), **7–10 m** distance buffer (GPS is 4–9 m off), and **17° angle / 4.0 slope** guards to reject side-trails touching at junctions. Propagates matched tags to *all* member segments (one-to-many), writes `fixme=`/`overlapping=yes` for ambiguities, and **emits review-ready GeoJSON/OSM XML — "must be manually validated by a human (not AI)."** Supporting cast: **PostGIS** (`ST_HausdorffDistance`, `ST_FrechetDistance`, buffers), **GeoPandas/Shapely**, **GDAL/ogr2ogr**; Hootenanny (powerful, hard to install) and `osm_conflate` (POI-oriented) as references.

### 7.4 Known lessons (de-risking the de-risk)
- The **OSM-US Trails Stewardship Initiative** (NPS, USFS, USGS, AllTrails, Gaia are members) does this at scale and explicitly treats it as **"review and validate," not automated import** — the Utah pilot did ~1,100 of a 60,000-mi target. The human-review loop is a *permanent feature*, not a v0 shortcut.
- **Source data is genuinely bad:** documented trails mislocated up to ⅓ mile; trails in data that don't exist on the ground; real signed trails missing; signage disagreeing with the database; topology breaks; data >10 years stale. Expect to find these; budget review time.
- USGS NTD **re-hosts** agency data → NTD + USFS aren't independent confirmations.

### 7.5 Recommended Phase-0 conflation approach
1. **OSM = canonical spine** for the pilot region; conflate **USFS** (GWJ NF) and **NPS** (Shenandoah) *onto* it for authoritative `ref`/operator/allowed-use. (Clean two-agency test.) Pull USGS NTD only as a cross-check.
2. **Block on name + ref first** (normalize names), then **confirm geometrically** (10–25 m buffer + Hausdorff; Fréchet for loops; bearing guard at junctions).
3. **Score → auto-accept high-confidence → queue the rest for human review** (OSM Merge's `fixme=` pattern or a MapRoulette-style list). At a few dozen trails, review is *hours*.
4. **Persist provenance, don't flatten** (the schema in §7.2). Keep conflicting access/usage per-source.
5. **Evaluate OSM Merge directly** before building anything custom; fall back to a thin PostGIS/GeoPandas script for control. Skip Hootenanny/KRAFT for v0.
6. **Expect ~100% hand-verification of the pilot** and real source errors — that's the finding, not a failure.

---

## 8. Recommended Phase-0 pilot source stack (decision-ready)

For **Shenandoah NP + GWJ NF** (a clean NPS + USFS two-agency test in VA):

- **Corpus geometry:** OSM (Geofabrik VA extract) as spine + USFS NFS Trails + NPS Public Trails conflated on via OSM Merge.
- **Elevation:** USGS 3DEP 1/3 arc-sec (1 m where available) from AWS COGs.
- **Land context:** PAD-US 4.1 (public-land filter + manager).
- **Permits:** RIDB API (Shenandoah backcountry + GWJ campgrounds) — requirements only in Phase 0; availability is a risk to defer.
- **Live overlay (Verifier):** NWS (forecast + alerts), USGS Water **OGC API**, FIRMS, AirNow — JIT on the shortlist, source-stamped.
- **Drive-time:** self-hosted Valhalla (isochrones) for origin/radius. *(BUILT — Epic 013.)*
- **Commons fork (BUILT — Epic 010):** de-identified, endpoint-trimmed observation write — schema-aware from day one (§5.1 keeps the OSM layer separable).

Everything here is free and either public-domain or ODbL-personal-safe. The only spend is a small VPS for self-hosted Valhalla (and later the always-on poller).

---

## 9. Open questions & verify-before-coding checklist

**Resolved by this research (propose → Decision Log):**
- Routing provider → **Valhalla self-hosted** (native isochrones). *(was §24 "routing provider")*
- USGS streamflow → **build on `api.waterdata.usgs.gov/ogcapi`**, not legacy. *(new)*
- Conflation approach → **OSM-spine + OSM Merge + human review**; canonical-route + `SAME_AS` provenance schema. *(de-risks §23/§24 "conflation")*
- Dog/leash facts → **never from OSM**; land-manager only. *(sharpens source-or-silence)*
- ODbL → **personal use is unencumbered; public commons needs the Collective-Database split** designed in at Stage 2. *(resolves part of §18)*

**Still open / verify against live endpoints before coding (🟡):**
- Exact USFS field roster + whether `USGSTrails.sourcefeatureid` = `TRAIL_CN` (pull GWJ-NF records, diff).
- RIDB exact rate limit (cited ~50/min) + precise license name in the live Access Agreement.
- NPS API: whether limit raises above 1000/hr; live field schema (no authenticated call was made).
- PAD-US 4.1 version-distinct DOI (the reused `10.5066/P96WBCHS` may be a snippet error).
- VA "Recreation Park Trails" scope (likely Alexandria-only); whether a true open VA State Parks centerline layer exists behind the DCR web map.
- 1 m / S1M 3DEP coverage per pilot trail.
- AirNow rate-limit partitioning (per-service vs global).

**Genuinely undecided (later stages):** the conflation match-score thresholds for *this* data (tune empirically); whether the commons goes ODbL-public or stays Collective; backcountry live-coverage disclosure UX.

---

## 10. How this updates the plan

- **Workplan Stage 1 → substantially complete.** The source catalog, corpus/live split, authority tiering, license summary, coverage-gap map, and the **conflation reality-check spike** (the explicit Stage-1 spike) are all delivered. Remaining Stage-1 work is empirical field-level verification (the 🟡 list), best done as the first step of the Stage-3 pipeline rather than more desk research.
- **De-risks Stage 2 (schema):** the canonical-route + `SAME_AS`-provenance + separate-segment-layer model is validated; the ODbL Collective-Database constraint is now a known schema input.
- **De-risks Stage 3 (pipeline):** OSM Merge is a concrete starting point; the ingest order (OSM spine → conflate USFS/NPS → enrich 3DEP/PAD-US/RIDB) is clear.
- **Feeds Stage 4 (engine):** the live adapters and their auth/limits/freshness are catalogued; the new USGS Water API is the right target.
- **Honors threads:** T6 (legal) — ODbL + the encumbered/off-limits sources are mapped before any public release; T1 (secrets) — the keyed sources (NPS, AirNow, FIRMS, RIDB, Anthropic) define what the secrets store must hold.

---

### Appendix A — Auxiliary sources (situational)
- **Sunrise/sunset (daylight):** compute locally from the NOAA/Meeus algorithm (no network/attribution); SunriseSunset.io as a hosted fallback (commercial-OK, attribute).
- **NOAA CDO** (historical climate, token, 5/s · 10k/day) — seasonal context. **NOAA CO-OPS tides** (keyless) — coastal/tidal-marsh trails only.
- **USGS Earthquake** (GeoJSON, keyless) — low relevance mid-Atlantic.
- **CDC/JHU Lyme** (aggregated, lagged, county-level) — static seasonal-advisory layer, not a live call; mid-Atlantic is a hotspot.
- **avalanche.org / National Avalanche Center** (GeoJSON, keyless) — winter, overwhelmingly western US; **out of scope for mid-Atlantic**, recorded for completeness; 🔴 license unspecified.

### Appendix B — Proprietary platforms (all OFF-LIMITS)
| Platform | API? | Verdict | Reason |
|---|---|---|---|
| Strava | gated/fee | OFF-LIMITS | Explicit AI ban (incl. RAG/embeddings/context-window); single-user-display; competing-app; 7-day cache cap ([api](https://www.strava.com/legal/api)) |
| AllTrails | none | OFF-LIMITS | No API; anti-scrape ToS actively enforced (MCP takedown Jan 2026) + DataDome |
| Hiking Project (onX) | deprecated 2020 | OFF-LIMITS | onX declines all new access ([data](https://hikingproject.com/data)) |
| Gaia GPS (Outside) | none | OFF-LIMITS | No public API; restrictive Outside ToS |
| onX Backcountry | none | OFF-LIMITS | No developer program; data = closed Hiking/Mountain Project |
| Komoot (Bending Spoons) | partner-only | OFF-LIMITS | No public API; partner-only; post-acquisition instability |

*(All observed 2026-06-19; ToS change often — re-check before any decision. The takeaway is stable: none offers a lawful AI/open-data path.)*

---

*Primary sources are linked inline. Key references: [Geofabrik](https://download.geofabrik.de/north-america/us/virginia.html) · [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) · [OSMF Legal FAQ](https://osmfoundation.org/wiki/Licence/Licence_and_Legal_FAQ) · [USFS NFS Trails](https://data-usfs.hub.arcgis.com/datasets/usfs::national-forest-system-trails-feature-layer/about) · [USGS National Digital Trails](https://www.usgs.gov/national-digital-trails/data) · [USGS Water API migration](https://api.waterdata.usgs.gov/docs/ogcapi/migration/) · [PAD-US](https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-overview) · [RIDB](https://ridb.recreation.gov/) · [NWS API](https://www.weather.gov/documentation/services-web-api) · [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/) · [AirNow API](https://docs.airnowapi.org/) · [OSM Merge](https://github.com/osm-merge/osm-merge) · [OSM-US Trails Stewardship](https://openstreetmap.us/our-work/trails/) · [Valhalla](https://valhalla.github.io/valhalla/).*
