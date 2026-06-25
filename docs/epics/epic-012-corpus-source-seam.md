# Epic 012 — CorpusSource Seam

**Status:** DEFINED  
**Phase:** 1 (Personal Intelligence) — a Stage-3 ingestion refactor; foundational, runs ahead of any new corpus source  
**Spec refs:** `docs/research/source-seams-corpus-and-live.md` Half A §1–6 + decisions SS-1, SS-2, SS-3, SS-4, SS-8, SS-10, SS-12 · gap-audit C5 · decision-log-additions-proposed §32 (Stage-3 ingestion: each fetcher returns a uniform `Feature`, degrades to `[]`), §33 (tuned thresholds `name_auto=85`/`overlap_auto=0.5`/`hausdorff_auto_m=80`; NPS = authority tier 1 for official names) · §34 (USFS EDW 403 → local GeoJSON; USGS `-999999` no-data) · decision-log §28 (best-view per attribute, authority-tier lookup) · §27 (OSM = geometry spine, USFS/NPS = authoritative federal overlay) · Rules #1, #3, #6, #10

---

## Capability statement

Adding a corpus source becomes **one new adapter file + one config-list line, with zero downstream change**: `ingestion/pipeline.py::run_pipeline` iterates a config-driven registry and **names no source literally** — the `if "osm" in active_sources` / `if "nps" in …` / `if "usfs" in …` ladder, the three direct `fetch.osm/nps/usfs` imports, the `--source choices=["osm","nps","usfs"]` literal, and OSM-hardcoded-as-conflation-feature-set-`a` are all replaced by a `CorpusSource` contract whose adapters *declare* `kind` / `role` / `authority_tier`, so spine selection, best-view weighting, and the enrichment join point fall out of the source's own declaration.

## Architectural context

**Builds on:**
- `ingestion/fetch/{osm,nps,usfs}.py` — the three contract-less `fetch(bbox, *, client=None, …) -> list[Feature]` functions (their `__init__.py` docstring already *describes* a uniform contract — "Each sub-module exposes `fetch(bbox, *, client) -> list[Feature]` … On any error, return `[]`" — that this epic *formalizes* as an ABC rather than a convention). `run_pipeline` calls them positionally as `osm_fetch.fetch(bbox)` (no `client`), so the `client` kwarg is incidental, not part of the live contract.
- `ingestion/conflate/match.py` — `Feature(name, geom, source, ref)` (the normalization point — reused **by name**, never reshaped), `match(a_features, b_features, *, thresholds=_DEFAULT)` (`thresholds` is **keyword-only**), and the source-agnostic scorer `normalize_name` / agreement / verdict classification. Conflation scoring **already** scores any `(Feature, Feature)` pair; the only C5 coupling is *which* set is passed as `a`.
- `ingestion/pipeline.py` — `run_pipeline` (the C5 site: `active_sources = set(sources or ["osm","nps","usfs"])`, the three `if "<name>" in active_sources` fetch blocks, the hardcoded `match(osm_features, nps_features, thresholds=…)` / `match(osm_features, usfs_features, thresholds=…)` calls with OSM forced as `a`, the load loop that special-cases OSM as canonical, the `_build_canonical_id`/`_sr_uid` helpers, and the CLI `--source` choices). **`consolidate_osm_segments` lives here** (`ingestion/pipeline.py`, not `match.py`) and is source-agnostic over `Feature`s.
- `graph/load.py` — `load_canonical_trail` / `load_source_record` / `merge_same_as` / `make_runner` (all `MERGE`, idempotent; writes public world nodes, no scope needed). **Untouched in body** — the load loop's *call sites* lose their OSM special-casing but the loader functions do not change.
- `orchestration/config.py` — `Settings.from_env()` (already carries `region` + the `ADVENTURE_WATCH_ADAPTERS` comma-split idiom AC-2.4 reuses); gains `corpus_sources` + a USFS-file path the adapter reads from `Settings`.
- `orchestration/providers/registry.py` (`_build` → `ValueError` on unknown provider) and `ingestion/watch/registry.py` (`enabled_adapters` → list of instances via a `name -> factory(Settings)` dict, `ValueError` on unknown name) — the **two positive references** the gap-audit names as the bar: a real contract + a config-driven registry resolving by name, adapters hiding source-specifics. This seam follows their **spirit**; `enabled_sources` mirrors `watch/registry.enabled_adapters` most closely (both return a list of instances). It introduces a **new** `from_config` classmethod (the source-seams design doc's chosen shape) — a deliberate departure from the existing registries' factory-function indirection (SS-1).

**Enables:** any new geometry source (USGS NTD, a regional/state trail dataset) and — via the new `enrichment` kind — the **post-conflation join point Stage 3 §7 promised and C5 found had nowhere to plug in** (3DEP elevation, PAD-US manager/access, RIDB permit-requirement). A non-OSM-spine region (NPS or USFS authoritative geometry) becomes a per-region config selection, not a `run_pipeline` rewrite. Sibling Epic 013 (LiveAdapter seam, Half B) is **independent** (disjoint code — orchestration vs. ingestion) and may run in parallel.

**Does NOT include:**
- **Any new actual source.** USGS NTD, PAD-US, 3DEP, RIDB-corpus, regional datasets are **out of scope** — this epic ships the *seam* and refactors the **existing three** (OSM/NPS/USFS) behind it, plus a throwaway `echo` stub that proves drop-in (S6). The new-source rows in §5 of the design doc are a forward checklist, not deliverables here.
- The **enrichment execution** itself — S5 lands the *join point* (the `enrich(canonical)` contract slot + the `for s where kind=enrichment` pipeline step + an `EnrichmentFact` type), but with **no real enrichment adapter** wired and **no graph write** for enrichment facts beyond a tested stub. PAD-US/3DEP/RIDB-corpus building is a follow-on. (A real enrichment loader against `:CanonicalTrail` is deferred to whichever epic ships the first enrichment source.)
- Per-region spine *configuration* (a `spine:` key in `regions/*.geojson`). S4 makes spine a **declared `role` on the source**; selecting a *non-OSM* spine per region is a config surface left for the epic that needs it. This epic only proves OSM's spine-ness is now read from a declaration, not hardcoded.
- Polygon-clip. `fetch(region)` takes the **region object** (so the signature *admits* a polygon when Stage 3 §2's clip lands), but the adapters still bbox-clip exactly as the fetchers do today — no clip behavior change.
- Any change to conflation **scoring** or the tuned thresholds (§33: `name_auto=85`, `overlap_auto=0.5`, `hausdorff_auto_m=80`) — they are unchanged and source-agnostic already.
- The Half-B live seam (Epic 013), the M3 TTL cache, drive-time (Epic 005). Those are live-side / orchestration concerns; this epic touches only `ingestion/`.

---

## Stories

### S1 — `CorpusSource` ABC + normalized corpus types

**Given** the `ingestion/sources/` package does not exist (Stage 3 §9 named it, C5 confirmed it absent)  
**When** this story lands a **new** `ingestion/sources/base.py`  
**Then** it defines the `CorpusSource` ABC and its supporting enums, reusing `ingestion.conflate.match.Feature` **by name** as the normalized output (the seam wraps proven output, never reshapes it — SS-2)

The contract (in the spirit of `orchestration/providers/base.py` + `ingestion/watch/base.py`, with a **new** `from_config` classmethod):

```
class SourceKind(Enum):        # geometry | enrichment
class ConflationRole(Enum):    # spine | conflate | enrich

class CorpusSource(ABC):
    name: str                  # "osm" | "nps" | "usfs" | ...
    kind: SourceKind
    role: ConflationRole       # a geometry source declares one
    authority_tier: int        # 1 | 2 | 3  (new property — see AC-1.4)
    def fetch(self, region: Region) -> list[Feature]: ...   # geometry; [] on any error
    def enrich(self, canonical: CanonicalNode) -> list[EnrichmentFact]: ...  # enrichment only
    @classmethod
    def from_config(cls, settings: Settings) -> "CorpusSource": ...  # always returns (no | None)
```

**Why:** the three fetchers today *merely happen* to return `list[Feature]`; there is no enforced contract. A declared ABC turns convention into a boundary the conformance suite (S6) can assert against, and makes `kind`/`role`/`authority_tier` first-class declarations the registry and load loop read instead of literals.

**AC-1.1:** `ingestion/sources/base.py` exists and exports `CorpusSource`, `SourceKind`, `ConflationRole`, and an `EnrichmentFact` dataclass; `CorpusSource` is an `abc.ABC` with `fetch` (or `enrich`) declared `@abstractmethod`.  
**AC-1.2:** `SourceKind` has exactly members `{geometry, enrichment}`; `ConflationRole` has exactly `{spine, conflate, enrich}` (SS-4 / SS-3).  
**AC-1.3:** `CorpusSource.fetch` takes a **region object** parameter (not a loose `bbox` tuple, and no `client`) and is annotated `-> list[Feature]`, where `Feature` is imported from `ingestion.conflate.match` (not redefined) — verified by `Feature is match.Feature` identity.  
**AC-1.4:** `authority_tier` is a declared class attribute typed `int`, constrained to `{1, 2, 3}`; instantiating/declaring a source with a tier outside that set raises `ValueError` (fail loud at the boundary — Rule #1 discipline). This is a **new** property (committed §27/§28 reason about authority qualitatively, assign no numbers), so no existing constant is being surfaced.  
**AC-1.5:** A geometry source whose `kind == geometry` must declare a `role ∈ {spine, conflate}`; an enrichment source must declare `kind == enrichment` and implement `enrich` (not `fetch`). A mismatch (e.g. `kind=enrichment` with a `role=spine`, or a geometry source implementing only `enrich`) raises `ValueError` at construction.  
**AC-1.6:** `from_config(cls, settings)` is declared and, for corpus sources, **always returns a `CorpusSource`** (never `None`) — a missing path/key is a *misconfiguration* that raises `ValueError` inside `from_config`, deliberately asymmetric with the live side's `| None` self-drop (SS-10; the *why*: a corpus source is gated on the config list, so absence there is loud, not silent).

### S2 — Config-driven registry: `enabled_sources` + `spine`

**Given** `run_pipeline` today reads `set(sources or ["osm","nps","usfs"])` and branches on literal names  
**When** this story lands `ingestion/sources/registry.py` (mirroring `ingestion/watch/registry.py::enabled_adapters` — the list-returning analog)  
**Then** `ADVENTURE_CORPUS_SOURCES=osm,nps,usfs` in config resolves, via each source's `from_config`, to a list of `CorpusSource` instances — and the registry is the **single place** that knows which sources exist

**Why:** the registry localizes the "which sources" decision exactly as `watch/registry.enabled_adapters` localizes "which vendors" and `providers/registry` localizes "which provider per tier." `run_pipeline` then iterates a list and never names a source again (the modularity guarantee — §6).

**AC-2.1:** `enabled_sources(settings) -> list[CorpusSource]` reads `settings.corpus_sources` (parsed from `ADVENTURE_CORPUS_SOURCES`) and returns one instance per name; order follows config order. Resolution is via each source's `from_config` (the new classmethod) — a deliberate departure from the existing registries' `name -> factory(Settings)` dicts, which this registry's name map points *at* `from_config` rather than at standalone factory functions.  
**AC-2.2:** An unknown source name in the config list raises `ValueError` at the registry boundary, naming the offending source — exactly as `watch/registry.enabled_adapters` raises in its loop on an unknown adapter name (and as `providers/registry._build` raises on an unknown provider).  
**AC-2.3:** `spine(sources) -> CorpusSource` returns the **one** source whose `role == spine`; it raises `ValueError` if **zero** or **more than one** geometry source claims `spine` (a region must have exactly one geometry spine — SS-3).  
**AC-2.4:** `Settings.from_env()` parses `ADVENTURE_CORPUS_SOURCES` (comma-separated) into `corpus_sources: list[str]`, defaulting to `["osm","nps","usfs"]` when the env var is absent (preserves today's default), reusing the existing `ADVENTURE_WATCH_ADAPTERS` comma-split idiom. Any USFS-file path the `UsfsSource` adapter needs is read from `Settings` (e.g. `ADVENTURE_USFS_GEOJSON`), via `from_config` → the config store (Rule #10), never hardcoded in the adapter body.  
**AC-2.5:** A grep over `ingestion/pipeline.py` finds **no string literal** `"osm"`, `"nps"`, or `"usfs"` in `run_pipeline`'s body or the CLI `--source` choices (the choices derive from the registry's known names). *This AC is the empirical C5-closure check.*

### S3 — Refactor the three fetchers into adapters behind the contract

**Given** `ingestion/fetch/{osm,nps,usfs}.py` hold the three `fetch()` functions and `run_pipeline` imports them directly  
**When** this story moves each fetcher's body into an adapter class implementing `CorpusSource`  
**Then** `OsmSource` / `NpsSource` / `UsfsSource` exist in `ingestion/sources/`, each wrapping its existing transport **as-is**, with **zero change** to `ingestion/transform`, the hygiene step, `consolidate_osm_segments`, or `graph/load.py`

**Why:** this is a refactor *behind a contract*, not a rewrite. The wildly different transport (Overpass HTTP + mirror-failover; NPS ArcGIS pagination; USFS local-GeoJSON bbox-clip) is the adapter's private business; everything downstream sees one `list[Feature]`. The existing degrade-to-`[]`-on-error behavior (§32) is **codified** by the contract, not altered.

**AC-3.1:** `OsmSource` (`kind=geometry`, `role=spine`, `authority_tier=2`), `NpsSource` (`kind=geometry`, `role=conflate`, `authority_tier=1`), `UsfsSource` (`kind=geometry`, `role=conflate`, `authority_tier=1`) each implement `CorpusSource`; their `fetch` produces the **identical `Feature` lists** the old `fetch.osm/nps/usfs` functions produced for the same geographic input. The regression harness derives the region's `bbox` for the old function (`fetch(bbox)`) and passes the **region object** to the new adapter (`adapter.fetch(region)`) — the adapter derives the bbox from the region internally — then asserts the two `Feature` lists are equal (the input *shape* changes from bbox to region; the input *area* is the same), feeding a recorded/mocked HTTP or file fixture through both paths.  
**AC-3.2:** `from_config` for `OsmSource`/`NpsSource` constructs with no credential (keyless); `UsfsSource.from_config` reads its GeoJSON path from `Settings` and raises `ValueError` if the configured path is **misconfigured/absent at config-resolution time** — but `fetch` still returns `[]` (not raise) on a *runtime* read/parse failure (the §32 degrade boundary). The EDW-403 → local-file detail (§34) lives entirely inside `UsfsSource`.  
**AC-3.3:** Each adapter's `fetch` returns `[]` (never raises past the adapter) on injected transport failure (non-200 for OSM/NPS, missing/corrupt file for USFS) — degrade-and-disclose, Rule #6, asserted by the conformance suite (S6).  
**AC-3.4:** `consolidate_osm_segments` **remains in `ingestion/pipeline.py`** as a post-fetch step applied to the spine's `Feature`s; it is **not** moved into `OsmSource` (it is source-agnostic over `Feature`s, and keeping it in the pipeline preserves the "spine is whichever source declared the role" generality — an NPS-spine region would consolidate the spine identically). Its body is unchanged.  
**AC-3.5:** No import of `ingestion.fetch.{osm,nps,usfs}` remains in `run_pipeline` (the three direct fetcher imports are deleted). The `ingestion/fetch/` modules may remain as transport helpers the adapters call internally, or be folded into the adapter files — either is acceptable so long as `run_pipeline` imports only the registry.

### S4 — OSM-as-spine becomes a declared `ConflationRole`, read by the registry

**Given** `run_pipeline` calls `match(osm_features, nps_features, thresholds=…)` and `match(osm_features, usfs_features, thresholds=…)` — OSM hardcoded as feature-set `a` — and the load loop special-cases OSM as canonical  
**When** this story rewires the conflate + load steps to read the spine from `registry.spine(sources)`  
**Then** the spine is resolved generically: `spine = registry.spine(sources); spine_features = consolidate_osm_segments(spine.fetch(region))`, and conflation runs `for s in geometry sources where role != spine: match(spine_features, s.fetch(region), thresholds=thresholds)` — **OSM-as-`a` stops being a hardcode**

**Why:** SS-3 — a non-OSM-spine region must become config, not a `run_pipeline` rewrite. The `match.py` scorer is already source-agnostic; the *only* C5 coupling was which set was passed as `a`. Making `a` the declared spine removes it.

**AC-4.1:** `run_pipeline`'s conflation step contains **no** literal `osm_features`-as-first-argument call; it iterates non-spine geometry sources and passes `spine_features` as the first `match()` argument generically, with `thresholds` passed as the keyword-only argument (`match(spine_features, s.fetch(region), thresholds=thresholds)` — `match`'s signature is `match(a, b, *, thresholds=_DEFAULT)`, so the third arg must be keyword). Swapping which source declares `role=spine` (in a test fixture) re-points conflation onto that source's features **with no `run_pipeline` edit**.  
**AC-4.2:** `match.py` is **unchanged** (no diff) — confirming the coupling lived in `run_pipeline`, not the scorer. The tuned thresholds (§33) flow through unchanged.  
**AC-4.3:** The load loop reads `authority_tier` **from the source object** when recording the winning source / weighting `SAME_AS`, instead of literally special-casing `"OSM"` as canonical. The `authority_tier` is a per-source **floor** only — **per-attribute best-view overrides remain in the best-view layer** (committed §28 records the winning source *per attribute*; §33 has NPS win official-names-only); this scalar must not flatten that. (If best-view-per-attribute is not yet implemented, this AC requires only that the load loop's source-precedence read the tier from the source object rather than a `== "OSM"` literal — it must not *introduce* a per-attribute override it can't yet honor.)  
**AC-4.4:** A test asserting "exactly one geometry source has `role=spine`" passes for the default `osm,nps,usfs` config (OSM), and a fixture declaring two spines raises via `registry.spine` (AC-2.3) — proving spine-ness is a validated declaration, not an assumption.

### S5 — Enrichment-kind sources get a post-conflation join point

**Given** Stage 3 §7 promised a post-conflation enrichment join (3DEP/PAD-US/RIDB onto canonical nodes) and C5 found it had **nowhere to plug in**  
**When** this story adds the `enrichment` kind's pipeline step  
**Then** `run_pipeline` ends with `for s in sources where kind == enrichment: s.enrich(canonical)` over the just-conflated canonical nodes — the join point exists, with the contract slot (`enrich`) and an `EnrichmentFact` type, but **no real enrichment source** and **no graph write** beyond a tested stub

**Why:** the seam must *create the home* §7 lacked, even before a real enrichment source is built — otherwise adding 3DEP/PAD-US later would re-touch `run_pipeline` (the exact coupling this epic removes). Enrichment sources **never enter the matcher** (they join onto already-canonical nodes), so they need a distinct, declared step — SS-4.

**AC-5.1:** `CorpusSource` declares `enrich(self, canonical) -> list[EnrichmentFact]`; geometry sources may leave it `NotImplementedError`/abstract-unimplemented, enrichment sources must implement it (enforced by AC-1.5).  
**AC-5.2:** `run_pipeline` includes a step that iterates `sources where kind == enrichment` **after** conflation/load and calls `enrich` per canonical node; with **zero** enrichment sources enabled (the default config) this step is a no-op that adds no behavior change (asserted: default-config counts identical to pre-epic).  
**AC-5.3:** A test enrichment stub (`kind=enrichment`, implementing `enrich` to return a fixed `EnrichmentFact`) registered + enabled is invoked by the pipeline's enrichment step over canonical nodes and is **never** passed to `match()` (asserted: the stub's `fetch` is never called; it never appears as a conflation argument) — proving enrichment joins post-conflation, never enters the matcher.  
**AC-5.4:** `EnrichmentFact` carries provenance fields (at minimum `source`, `value`/`attribute`, and a confidence/freshness input slot e.g. `recorded_resolution`) consistent with §28's per-attribute best-view and the freshness inputs the design names (3DEP DEM resolution) — so when a real enrichment source lands, its facts already carry the substrate best-view needs. No real write target is required in this epic.

### S6 — Source-conformance suite + an `echo` drop-in proof

**Given** the modularity claim ("one file + one config line, zero downstream change") must be asserted *empirically*, not just designed  
**When** this story lands a shared `CorpusSource` conformance test suite and a throwaway `echo` source  
**Then** any `CorpusSource` passing the suite is provably drop-in compatible, and the `echo` source is added as **only** one new file (`ingestion/sources/echo.py`) + one config-list entry, **with no diff to `run_pipeline`**

**Why:** SS-12 / design §13 — the conformance-test AC is the empirical proof of the seam. If adding `echo` required touching `run_pipeline`, the seam would have leaked and C5 would not be closed.

**AC-6.1:** A parametrized conformance suite (`tests/test_corpus_source_conformance.py`) runs every registered geometry source through: (a) `fetch(region)` returns `list[Feature]` with **non-empty provenance** (`source` set, and `name` or `ref` present) for a valid fixture; (b) `fetch` returns `[]` (never raises) on injected failure; (c) the produced `Feature`s are **idempotent under the load `MERGE`** (running the load twice yields the same canonical/`SAME_AS` set — re-uses the existing list-appender `Runner` test pattern from `graph/load.py`).  
**AC-6.2:** An `EchoSource` (`kind=geometry`, `role=conflate`, `authority_tier=3`) in a **single new file** returns a small fixed `Feature` list from `fetch` and passes the AC-6.1 conformance suite unmodified.  
**AC-6.3:** Enabling `echo` is **exactly** one new file + appending `echo` to `ADVENTURE_CORPUS_SOURCES` — asserted by a test that, with `echo` enabled, `run_pipeline` fetches + conflates the echo features with **zero source-naming code in `run_pipeline`** (the same body that ran for `osm,nps,usfs`). *The git diff for "add echo" touches `ingestion/sources/echo.py`, the registry's name map, and `.env`/test config only — never `run_pipeline`.*  
**AC-6.4:** An enrichment conformance variant asserts an enrichment source's `enrich` returns `list[EnrichmentFact]` and is invoked only in the post-conflation step (AC-5.3), never the matcher.

---

## Definition of Done

- [ ] All ACs covered by at least one passing test (named per `docs/process/development-process.md`).
- [ ] `make check` green (ruff + mypy + pytest) — no regression in the existing ingestion test count.
- [ ] `ingestion/sources/base.py` + `registry.py` exist; `OsmSource`/`NpsSource`/`UsfsSource` refactored behind the contract; `EchoSource` stub present.
- [ ] **C5-closure asserted (AC-2.5):** no `"osm"`/`"nps"`/`"usfs"` string literal in `run_pipeline`'s body or the CLI `--source` choices.
- [ ] **Modularity proof asserted (AC-6.3):** the `echo` drop-in's diff touches no `run_pipeline` line.
- [ ] `match.py` confirmed **unchanged** (AC-4.2); `graph/load.py` loader bodies, `ingestion/transform`, hygiene, and `consolidate_osm_segments` confirmed unchanged in behavior.
- [ ] Default config (`osm,nps,usfs`, no enrichment) produces **identical** counts to the pre-epic pipeline on the pilot region fixture (AC-5.2) — refactor is behavior-preserving.
- [ ] Targeted self-review agent run with a narrow file list (`ingestion/sources/*`, `ingestion/pipeline.py` diff, `orchestration/config.py` diff) checking: Rule #1 (degrade-not-fabricate boundary), Rule #6 (`fetch`→`[]` never raises past adapter), Rule #10 (secrets only via `from_config`), and the asymmetry rationale (SS-10: corpus `from_config` always-returns, no `| None`). Every CRITICAL fixed before commit.
- [ ] Atomic commit split: (1) `ingestion/sources/base.py` contract + types; (2) registry + `Settings.from_env` config parsing; (3) three fetchers refactored into adapters + their tests; (4) `run_pipeline` rewired to iterate the registry (spine + conflate + enrichment steps) + CLI derived choices; (5) conformance suite + `echo` stub; (6) epic doc + `docs/epics/README.md` row update.
- [ ] `docs/epics/README.md` updated: add the Epic 012 row (Phase 1, depends on Stage 3 ingestion); set status `DONE ✅` on close.
