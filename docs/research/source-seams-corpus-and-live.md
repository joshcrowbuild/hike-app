# Source Seams — CorpusSource + LiveAdapter (design)

*Refines Stage 3 §9 (the never-built `ingestion/sources/*` adapter seam) and Stage 4 §5 (the per-source Verifier tools) into two formal, pluggable seams. Draft v0.1 — June 24, 2026. Remediates `architecture-gap-audit-2026-06.md` C5 + C6 (corrections tracked in `decision-log-additions-proposed §40`). Mirrors the proven shape of `device-integration-seam.md`.*

> **STATUS: IMPLEMENTED** by Epic 012 (CorpusSource seam) + Epic 013 (LiveAdapter seam + Valhalla drive-time); gap-audit C5/C6 closed. *(Design below kept as spec provenance.)* Specifies two config-driven seams so corpus and live-data sources become modular: a new source is **one adapter file + one config line, zero downstream change**. Both mirror the model-provider seam (`orchestration/providers/base.py` + `registry.py` — the *positive* reference the audit names as the bar at its C-section end) and the device seam. Honors rules #1 (source-or-silence), #2 (confidence ≠ rank penalty), #3 (live never persisted), #6 (degrade-and-disclose), #10 (secrets from the store).

> **Why now (the gap).** The audit found the model-provider seam done right — a real contract, a config-driven registry, two interchangeable adapters — and then found the *same shape missing twice*:
> - **C5:** `ingestion/pipeline.py::run_pipeline` is written against exactly three named sources (`osm_features`/`nps_features`/`usfs_features` vars, literal `if "osm" in active_sources` blocks, direct `fetch.osm/nps/usfs` imports, a CLI `--source choices=["osm","nps","usfs"]`). OSM is hardcoded as conflation feature-set `a` (the spine) in `match()` (`ingestion/conflate/match.py`), and the load loop special-cases OSM as canonical. `ingestion/fetch/` has **no base contract** — its three `fetch()` functions merely *happen* to return `list[Feature]`. The `ingestion/sources/*` directory Stage 3 §9 promised is **confirmed absent**.
> - **C6:** `orchestration/verifier.py::build_probes` hardcodes `from orchestration.adapters import airnow, firms, nws, ridb, usgs_water` and a per-source `if settings.<x>_key:` branch with inline `partial(...)` to reconcile mismatched signatures. `adapters/base.py` defines only `VerifiedFact` (a data shape), **no adapter interface**, no registry, no `ADVENTURE_LIVE_ADAPTERS`. "Weather" is permanently `== NWS`; an NWS outage = no weather, with no swap path.
>
> Both are the device-seam miss replicated — one on the corpus (slow/bulk) half, one on the live (JIT) half. This doc specifies both as **one design** because they are the same pattern at two layers; each ships as its own follow-on epic (§13).

Legend: ✅ decided · 🔶 recommend-confirm · ❓ open.

---

## 1. The principle — two more provider-agnostic seams

The project already has one swappable seam done right (models: `extract`/`normalize`/`judge` → a `ModelProvider` contract, a config-driven `registry.py` resolving by name, two interchangeable adapters; decision-log §29). Sources get the **same shape**, twice:

```
 OSM (Overpass) ──────┐                          NWS (api.weather.gov) ──┐
 NPS (ArcGIS) ────────┤→ CorpusSource contract   (weather fallback, TBD)─┤→ LiveAdapter contract
 USFS (bulk GeoJSON) ─┤  → list[Feature]         AirNow / FIRMS / USGS ──┤  → VerifiedFact | None
 USGS NTD / PAD-US ───┤  (registry, config)      RIDB / (regional) ──────┘  (registry, config,
 3DEP / RIDB / … ─────┘         │                                              keyed by kind)
                                ▼                                              │
        run_pipeline, loop-driven: fetch → conflate(spine,        verify(lat,lon), loop-driven:
        non-spine) → enrich → load (MERGE, idempotent)            iterate probes → keep only what returned
```

**The win (both halves):** adding a source touches *one new file* and a config line. The pipeline's conflate/enrich/load and the Verifier's iterate-and-keep loop become source-agnostic — they no longer name a source literally (§6, §11). **The mechanism a source uses — Overpass HTTP vs. ArcGIS pagination vs. a local bulk file; keyless vs. API-key vs. User-Agent — is the adapter's private business; everything downstream sees one normalized output** (`Feature` for corpus, `VerifiedFact` for live).

Two seams, one doc, because the audit's C5 and C6 share a single root cause and a single fix-shape. They ship as two epics (§13) because the code they touch (ingestion vs. orchestration) is disjoint and each is independently testable.

---

# HALF A — the CorpusSource seam (remediates C5)

## 2. Canonical types (the normalized corpus contract)

Lives in `ingestion/sources/base.py` (the directory Stage 3 §9 named and never created; sibling-in-spirit to `orchestration/providers/base.py`). It reuses the existing `Feature(name, geom, source, ref)` from `ingestion/conflate/match.py` as the normalization point — **every adapter yields `Feature`s, exactly as the three fetchers already do** (decision-log-additions-proposed §32: each fetcher returns a uniform `Feature` and degrades to `[]`) — so this seam wraps proven output rather than reshaping it.

- **`ConflationRole`** — enum `{spine, conflate, enrich}`. **This is the type that turns OSM-as-spine from a hardcode into a property.** Today OSM is wired as feature-set `a` in `run_pipeline`'s `match()` calls (`match(a_features, b_features)` in `match.py`); here exactly one active source declares `role=spine` and the pipeline reads it (§3). A region where NPS or USFS is the authoritative geometry spine becomes config, not a `run_pipeline` rewrite.
- **`authority_tier`** — int `1`/`2`/`3`. **This is a *new* property introduced by this seam**, consistent with the authority reasoning in committed §27/§28 (OSM = geometry spine; USFS/NPS = authoritative federal overlay; best-view records the winning source per attribute) but **not** an existing numeric scheme being surfaced — §27/§28 reason in "authority" qualitatively without assigning numbers. Declared **on the source**, so best-view resolution and `SAME_AS` weighting read a per-source authority *floor* from the adapter instead of a literal in the load loop. The scalar is a floor only: **per-attribute overrides remain in the best-view layer** (§28 records the winning source *per attribute*; decision-log-additions-proposed §40 has NPS win *official names only*) — the scalar does not flatten that.
- **`SourceKind`** — `{geometry, enrichment}`. Geometry sources produce `Feature`s that enter conflation; enrichment sources (3DEP elevation, PAD-US manager, RIDB permits) **join onto already-conflated canonical nodes** (Stage 3 §7) and never enter the matcher. This is the plug-in point §7 calls for that has nowhere to plug in today (audit C5).

## 3. The CorpusSource contract

```
class CorpusSource(ABC):
    name: str                              # "osm" | "nps" | "usfs" | "usgs_ntd" | ...
    kind: SourceKind                       # geometry | enrichment
    role: ConflationRole                   # spine | conflate | enrich  (a geometry source declares one)
    authority_tier: int                    # 1 | 2 | 3  (new; see §2)
    def fetch(self, region: Region) -> list[Feature]: ...      # geometry sources; [] on any error (degrade)
    # enrichment sources implement instead:
    def enrich(self, canonical: CanonicalNode) -> list[EnrichmentFact]: ...
    @classmethod
    def from_config(cls, settings: Settings) -> CorpusSource: ...   # pulls its own paths/keys
```

- `fetch(region)` takes the **region object** (bbox today; the same call admits a polygon when Stage 3 §2's polygon-clip lands), not the loose `bbox` tuple the three fetchers take now — so the spine/clip discipline is uniform.
- **Degrade-and-disclose holds, unchanged:** every existing fetcher already returns `[]` on non-200 (decision-log-additions-proposed §32: "degrades to `[]` so one source's outage never aborts the run"). The contract *codifies* that as the boundary rule — `fetch()` returns `[]`, never raises past the adapter. Fail loud *inside* (a malformed config → `ValueError` in `from_config`); degrade at the surface (a network/file failure → `[]` + a logged warning).
- Secrets/paths come only via `from_config(settings)` → the secrets store (rule #10); never the repo. USFS's bulk-file path (decision-log-additions-proposed §34: USFS EDW REST returns 403, so USFS ingests from a local GeoJSON) is just one adapter's private `from_config` detail.
- `from_config` here **always returns a source** (no `| None`): a corpus source is enabled by its presence in the config list (§4), so an absent path is a *misconfiguration* and fails loud, not a silent self-drop. This is deliberately asymmetric with the live side (§8), where a missing credential self-drops — see §10 (SS-10) for the rationale.

## 4. The registry (config-driven, like the model seam)

`ingestion/sources/registry.py`, mirroring `orchestration/providers/registry.py`:

- `ADVENTURE_CORPUS_SOURCES=osm,nps,usfs` in `.env` → the registry instantiates the enabled sources via `from_config`. Unknown name → `ValueError` (fail loudly at the boundary, exactly as `providers/registry` raises on an unknown provider).
- `enabled_sources(settings) -> list[CorpusSource]` — the **single place** that knows which sources exist; `run_pipeline` iterates the list and never names a source literally again. This deletes the `if "osm" in active_sources` / `if "nps" in …` / `if "usfs" in …` ladder.
- **Spine resolution:** the registry exposes `spine(sources)` → the one source with `role=spine` (raise if zero or more than one geometry source claims it). `run_pipeline` calls `match(spine_features, other_features)` generically for each non-spine geometry source — **OSM-as-`a` stops being a hardcode and becomes "whichever source declared `role=spine`."** A non-OSM-spine region is a config change (a per-region `spine:` selection), not a `run_pipeline` rewrite.
- The CLI `--source` choices stop being a literal `["osm","nps","usfs"]` list and derive from the registry.

## 5. Per-source adapters (mechanism hidden behind the contract)

The three existing fetchers wrap **as-is** — their bodies move into adapter classes; their guts are untouched (this is a refactor behind a contract, not a rewrite):

| Adapter | Kind | Role | Tier | Mechanism (private to the adapter) |
|---|---|---|---|---|
| **`OsmSource`** | geometry | **spine** | 2 | Overpass HTTP, mirror-failover; `consolidate_osm_segments` (the existing `pipeline.py:94` step) stays in the pipeline post-fetch — it operates on `Feature`s, source-agnostic. Spine is now a *declared role*, not feature-set `a`. |
| **`NpsSource`** | geometry | conflate | 1 | NPS public ArcGIS FeatureServer, paginated; authoritative for existence + geometry on NPS land (§27). |
| **`UsfsSource`** | geometry | conflate | 1 | Local bulk GeoJSON, bbox-clipped (EDW REST is 403 — decision-log-additions-proposed §34); authoritative for allowed_use. |

(Tier values above are the *new* `authority_tier` introduced in §2, not existing constants.)

New sources named in C5 / Stage 3 §1 become a closed checklist (§6):

| Adapter (new) | Kind | Role | Tier | Note |
|---|---|---|---|---|
| **`UsgsNtdSource`** | geometry | conflate | 2 | NTD re-hosts agency data — loads as **corroboration / `SAME_AS` evidence, not an independent source** (§27 "cross-check, don't double-count"); the adapter declares this so corroboration counts aren't inflated. |
| **`PadUsSource`** | enrichment | — | 1 | Manager / `pub_access` spatial-join onto canonical `:Area`/trail (Stage 3 §7). |
| **`ThreeDepSource`** | enrichment | — | 1 | 3DEP COG sampling → `gain_m`, `grade_max`; records DEM resolution (a confidence/freshness input). |
| **`RidbCorpusSource`** | enrichment | — | 1 | RecArea/Facility → `permit_required`, `ridb_facility_id` (the corpus *requirement* side; live availability is Half B). |
| **`<Regional>Source`** | geometry | conflate | 2–3 | e.g. a state/county trail dataset; one file, declares its own tier. |

Each implements the identical contract; the wildly different transport (Overpass vs. ArcGIS pagination vs. a local file vs. a COG raster sample) lives entirely inside the adapter.

## 6. Downstream is unchanged (the modularity proof)

`run_pipeline` reduces to:
1. `sources = enabled_sources(settings)` — **no literal source names anywhere.**
2. `spine = registry.spine(sources)`; `spine_features = spine.fetch(region)` (then the existing `consolidate_osm_segments`, which is source-agnostic).
3. `for s in sources where kind=geometry and role!=spine: match(spine_features, s.fetch(region), thresholds)` — the conflate step, generic over the spine.
4. The **existing** load loop (`load_canonical_trail` / `load_source_record` / `merge_same_as`, all `MERGE`, idempotent per decision-log-additions-proposed §32) consumes matches; it reads `authority_tier` from the source instead of special-casing OSM.
5. `for s in sources where kind=enrichment: enrich(canonical)` — the §7 join step, finally with a home.

Conflation scoring (`match.py`'s `name_similarity` / `geometry_agreement` / `classify`) is **already source-agnostic** — it scores any `(Feature, Feature)` pair. The only C5 coupling is *which* set is passed as `a`; making that the declared spine removes it. The tuned thresholds (decision-log-additions-proposed §33: `name_auto=85`, `overlap_auto=0.5`, `hausdorff_auto_m=80`) are unchanged.

**Adding a new corpus source = a closed checklist:**
1. Implement `CorpusSource` (`fetch` or `enrich`) in `ingestion/sources/<name>.py`.
2. Declare `kind`, `role`, `authority_tier` (best-view + spine selection fall out automatically).
3. Register it; add `<name>` to `ADVENTURE_CORPUS_SOURCES`.
4. Put any path/key in the secrets store via `from_config`.
5. Run it through the shared **source conformance test suite** (returns `Feature`s with non-empty provenance; degrades to `[]` on injected failure; idempotent under the load `MERGE`).
→ Zero edits to conflation scoring, the load loop, enrichment, or the run manifest.

---

# HALF B — the LiveAdapter seam (remediates C6)

## 7. Canonical types (the normalized live contract)

Extends `orchestration/adapters/base.py`, which today holds **only** `VerifiedFact` (the audit's exact finding: "no adapter interface"). `VerifiedFact` is kept **unchanged and by name** — it already carries `value`, `source`, `fetched_at`, `confidence_inputs`, and `disclosures`, which is precisely source-or-silence + degrade-and-disclose materialized (rules #1/#6). (Note: `decision-log-additions-proposed §40 (C6)` names the return type `Observation`; this doc keeps the concrete name `VerifiedFact` and uses "observation" only as the role-noun for what a probe returns — there is no second type.) The seam adds the missing *behavioral* types:

- **`ConditionKind`** — `{weather, air, fire, water, permits, drive_time}`. The registry is **keyed by kind** so multiple providers back one kind (primary + fallback) — the swap path C6's *Why* says is impossible today ("'weather' is permanently == NWS").
- **`Capabilities`** — booleans (`needs_point`, `needs_site_id`, `is_keyless`, `supports_region:set[str]`). Drives **per-region probe selection** (§9) and degrade-and-disclose: a US-only fire feed (FIRMS) simply *isn't selected* for a non-US region rather than returning a wrong-but-sourced reading.
- **`AdapterHealth`** — `ok` | `needs_reauth` | `rate_limited` | `down` (mirrors the device seam's `AdapterHealth` exactly). Uniform signaling so backoff and fallback-to-secondary are handled the same way for every adapter — the structural answer to "an NWS outage = no weather, no swap path."

## 8. The LiveAdapter contract

```
class LiveAdapter(ABC):
    name: str                          # "nws" | "airnow" | ...
    kind: ConditionKind                # weather | air | fire | water | permits | drive_time
    def capabilities(self) -> Capabilities: ...
    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None: ...
    def health(self) -> AdapterHealth: ...
    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None: ...   # None if its key is absent
```

- `probe(point, when)` is the signature named in `decision-log-additions-proposed §40 (C6)`. (The audit's own C6 *Action* names the simpler `fetch(lat,lon)->VerifiedFact|None`; the proposed correction renamed it `probe(point, when)` and added `health()` — this doc follows the correction.) It **subsumes** the per-source signature mismatch that forces today's inline `partial(...)`: `user_agent` (NWS), `api_key` (AirNow/FIRMS/RIDB), and keyless (USGS) all move *inside* `from_config`, so the call site is uniform: `adapter.probe(point)`. The `when` parameter admits forecast-time / historical probes (e.g. a planned departure window) the current `fetch(lat, lon)`-only shape can't express.
- **Source-or-silence is structural and unchanged (rule #1):** `probe()` returns a `VerifiedFact` stamped with `source` + `fetched_at`, or `None`. The Verifier keeps only what returned. A failed adapter contributes nothing — the engine can never surface an unsourced fact, exactly as today.
- **`from_config` returns `None` when the adapter's credential is absent** — preserving the current behavior (a missing key = that probe is simply absent, not a fabricated reading) while moving the `if settings.<x>_key:` decision *into the adapter*, out of `build_probes`. This `| None` self-drop is the deliberate asymmetry with the corpus side (§3): a live adapter is gated on a *credential* it may not have, so it drops itself silently; a corpus source is gated on the *config list* and a missing path is a loud misconfiguration (rationale in SS-10).
- `health()` is the new capability that makes **fallback** real: a primary returning `down`/`rate_limited` lets the registry fall through to the secondary for that kind (§9) — the redundancy rule #1 "makes especially valuable" (C6 *Why*) but the absent seam blocked.

## 9. The probe registry (config-driven, keyed by kind, per-region)

`orchestration/adapters/registry.py`, mirroring `providers/registry.py`:

- `ADVENTURE_LIVE_ADAPTERS=nws,airnow,firms,usgs_water,ridb` in `.env` → instantiate via `from_config`, dropping any that return `None` (credential absent). Unknown name → `ValueError`.
- `probes_for(region, settings) -> dict[ConditionKind, list[LiveAdapter]]` — grouped by `kind`, **ordered primary→fallback** within each kind, and **filtered by `Capabilities.supports_region`** so per-region selection (C6 *Why*: "per-region probe selection") is config + capability, never a code change. This replaces `build_probes`'s hand-written dict entirely.
- **The `verify()` loop changes (this is a real change, not a no-op).** Today `verify(lat, lon, probes)` (`verifier.py:39`) iterates a flat `Mapping[str, Probe]` and keeps what returns. The seam reshapes it to iterate `kind → [adapter…]`, calling the first adapter whose `health()` permits and falling to the next on `down`/`rate_limited`. **What is preserved is the invariant, not the loop body:** *keep only what returned* (source-or-silence) is identical; the iteration gains kind-keyed primary→fallback. Do not read this as "unchanged" — the loop body is rewritten; the guarantee it upholds is not.
- **Fold M5/M3 in here (audit's explicit instruction):**
  - **M5 Router/drive-time:** the Router becomes a `LiveAdapter` with `kind=drive_time` (origin-relative `probe`), behind config, not a direct `valhalla.fetch` import — so an OSRM/GraphHopper/hosted swap is one adapter. (Drive-time stays out of the per-point Verifier loop and is called in ranking, but through *this* contract — audit M5 *Action*.)
  - **M3 TTL cache:** the registry is the natural home for the per-source TTL cache (NWS ~10m, USGS ~15m, AirNow ~60m, FIRMS ~10m — Stage 4 §4) keyed by `(name, rounded point | site_id)`, wrapping `probe()`. Co-locating it here (audit M3 *Action*: "naturally co-located with the live-adapter registry") restores the cost lever (decision-log §29) that currently survives only as docstrings.

## 10. Per-kind adapters (mechanism hidden behind the contract)

| Adapter | Kind | Credential (via `from_config`) | Region | Note |
|---|---|---|---|---|
| **`NwsAdapter`** | weather | User-Agent (keyless) | US | Existing two-hop `/points`→forecast + `/alerts/active`; the hard-guardrail feed. |
| **`<weather fallback>`** *(new, TBD)* | weather | TBD | global | **Fallback** when NWS is `down` — the swap C6 says is impossible today. Candidates (Open-Meteo / Tomorrow.io) are *illustrative only* in the audit; **license must be screened per §18 (open-data-only) before building** — not yet a decided provider. Discloses non-authoritative status. |
| **`AirNowAdapter`** | air | API key | US | AQI/PM2.5, labelled preliminary (disclosure). |
| **`FirmsAdapter`** | fire | MAP_KEY | US (capability-gated) | Thermal-anomaly ≠ confirmed-fire disclosure. |
| **`UsgsWaterAdapter`** | water | keyless | US | Nearest-gauge distance disclosed; carries the decision-log-additions-proposed §34 `-999999` no-data guard. |
| **`RidbAdapter`** | permits | API key | US | Live availability (unofficial; risk-flagged). |
| **`ValhallaAdapter`** *(M5)* | drive_time | self-hosted URL | — | Origin-relative; ranking-time, behind the contract. |

Each implements the identical contract; the per-source auth/transport is the adapter's private business.

## 11. Downstream is unchanged (the modularity proof)

`verifier.verify(lat, lon, registry)`:
1. `probes = registry.probes_for(region, settings)` — **no literal adapter imports, no `partial`, no `if settings.<x>_key` ladder.**
2. For each `kind`, call the first adapter whose `health()` permits; on `down`/`rate_limited` fall to the next (fallback now possible — the body change noted in §9).
3. Keep only `VerifiedFact`s that returned — source-or-silence, the same invariant as today.

Nothing in the Curator, the confidence computation, or the hedged-phrasing call is adapter-aware. Confidence still **never penalizes ranking** (rule #2): a fallback provider's lower authority lands in `confidence_inputs`/`disclosures` and shapes *presentation*, not rank position.

**Adding a new live source = a closed checklist:**
1. Implement `LiveAdapter` (`probe`, `health`, `capabilities`, `from_config`) in `orchestration/adapters/<name>.py`.
2. Declare its `kind` + `Capabilities` (per-region selection + degrade-and-disclose fall out automatically).
3. Register it; add `<name>` to `ADVENTURE_LIVE_ADAPTERS` (position sets primary vs. fallback for its kind).
4. Put its key in the secrets store via `from_config`.
5. Run it through the shared **adapter conformance suite** (returns a stamped `VerifiedFact` or `None`, never raises past the boundary; honors its TTL; `health()` transitions on injected 401/429/5xx).
→ Zero edits to the Curator, confidence, or the engine; the only Verifier change is the one-time kind-keyed loop reshape (§9), not a per-source edit.

## 12. Privacy / sensitivity (unchanged, now uniform)

Both seams operate on the **anonymous world + live-conditions layer** — no personal overlay reaches any `fetch`/`probe`. The overlay-routing concern (C4) is therefore out of scope for these seams (it governs egress of the *private* overlay, which these paths never carry); the seams do not foreclose it elsewhere. Live readings are **never persisted as graph nodes** (rule #3) — held in the §9 TTL cache keyed by resolution ids, exactly as Stage 4 §4 and decision-log §28 require. Corpus writes remain slow/structural-only.

---

## 13. Build — each half is its own follow-on epic

This doc is a **design spec, not an epic.** Each half ships as one targeted epic; the epics are written separately (do **not** author them here). Numbering: 008–011 are already taken (`docs/epics/README.md`: 008 = API tests, 009 = eval-harness expansion, 010 = Commons Fork write, 011 = scoped-write seam — 010/011 just defined alongside this spec); the next genuinely-free slots are **012** and **013**.

- **Half A → Epic 012 — CorpusSource seam.** Suggested title: *"CorpusSource contract + registry; OSM-as-spine becomes a declared role."* Remediates C5. Scope: `ingestion/sources/base.py` + `registry.py`, refactor the three fetchers into adapters behind the contract, rewire `run_pipeline` to iterate the registry, land the source-conformance suite. Folds in the enrichment-source kind so Stage 3 §7 has a plug-in point. 🔶 confirm number with the build session.
- **Half B → Epic 013 — LiveAdapter seam.** Suggested title: *"LiveAdapter contract + kind-keyed probe registry; primary/fallback per condition."* Remediates C6. Scope: extend `adapters/base.py` with the contract, `adapters/registry.py`, refactor the five adapters + the Router (M5) behind it, reshape `verify()`/replace `build_probes`, add the M3 TTL cache and a (license-screened) weather fallback as the proof-of-swap. 🔶 confirm number; **sequence after 012** only if convenient — the two are independent (disjoint code) and may run in parallel.

A **suggested conformance-test AC for each follow-on epic** (to be authored there in full Given/When/Then form, not here): a throwaway "echo" adapter added as *only* a new file + a config line, with no diff to `run_pipeline` / `verify`'s per-source wiring, passes the conformance suite — the modularity proof, asserted empirically.

---

## 14. Decisions

| # | Decision | Status |
|---|---|---|
| SS-1 | Corpus + live sources each get a **config-driven seam** mirroring the model-provider seam (contract + registry + `from_config`); new source = one adapter file + one config line, zero downstream change. Remediates C5 + C6. | ✅ |
| SS-2 | **CorpusSource** normalizes to the existing `Feature`; `run_pipeline` iterates `enabled_sources(settings)` and names no source literally. | ✅ |
| SS-3 | **OSM-as-spine becomes a declared `ConflationRole=spine` property of the source**, read by the registry's `spine()` — not feature-set `a` hardcoded in `match()`. A non-OSM-spine region is config, not a rewrite. | ✅ |
| SS-4 | Each corpus source declares a **new `authority_tier` and `kind` (geometry/enrichment)**; the scalar tier is a per-source *floor* read by best-view/`SAME_AS` weighting, with per-attribute overrides remaining in the best-view layer (§28); enrichment sources (3DEP/PAD-US/RIDB) join post-conflation — the home Stage 3 §7 lacked. | ✅ |
| SS-5 | **LiveAdapter** = `probe(point, when) -> VerifiedFact | None`, `health()`, `capabilities()`, `from_config()`; the existing `VerifiedFact` is reused **by name** as the probe return (it already carries source/timestamp/disclosures — rules #1/#6); "observation" is a role-noun, not a new type. Signature per decision-log-additions-proposed §40 (C6). | ✅ |
| SS-6 | The probe registry is **keyed by `ConditionKind` with ordered primary→fallback**, so a kind can have redundant providers and `health()` drives failover — closing C6's "weather == NWS, no swap path." The `verify()` loop body is reshaped to kind-keyed iteration (a real change); the keep-only-what-returned invariant is preserved. | ✅ |
| SS-7 | **Per-region probe selection** via `Capabilities.supports_region` (a US-only feed isn't selected outside the US) — config + capability, never a code change. | ✅ |
| SS-8 | Source-or-silence and degrade-and-disclose stay **structural** in both seams: corpus `fetch()` → `[]` on failure (never raises past the adapter); live `probe()` → `None`; failed source contributes nothing (rules #1/#6). | ✅ |
| SS-9 | **Fold M5 (Router/drive-time as a `drive_time` LiveAdapter) and M3 (per-source TTL cache) into the live registry**, per the audit's explicit instruction. | ✅ |
| SS-10 | All source secrets/paths come via `from_config` → the secrets store (rule #10); live readings never persist as graph nodes (rule #3); these seams touch only the anonymous layer, so no private overlay reaches a `fetch`/`probe` (C4 out of scope here). `from_config` is asymmetric by design: corpus always-returns (list-gated, loud on misconfig), live `| None` (credential-gated, silent self-drop). | ✅ |
| SS-11 | A specific **weather fallback provider is NOT yet decided** — Open-Meteo/Tomorrow.io are illustrative; the chosen provider must pass the §18 open-data/license screen before building. The *seam* for a fallback is decided; the *provider* is open. | 🔶 |
| SS-12 | Half A ships as a **CorpusSource-seam epic (suggested 012)**, Half B as a **LiveAdapter-seam epic (suggested 013)** — written separately, not in this doc. 008–011 are taken; numbers confirmed with the build session. | 🔶 |
| SS-13 | `ConditionKind` / `SourceKind` enum membership (e.g. add `snow`/`avalanche` kinds; per-park-unit vs. per-state corpus-region granularity, Stage 3 §2) — left **open**, decided as those sources arrive. | ❓ |
