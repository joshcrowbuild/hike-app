# Epic 013 — LiveAdapter Seam

**Status:** DONE ✅ *(track-c, 2026-06-24)*
**Phase:** 1 (Personal Intelligence) → 2 (Multiplayer) — *cross-phase infra; build-order after Epic 003 (SHIPPED), parallel-able with Epic 012*
**Spec refs:** `docs/research/source-seams-corpus-and-live.md` §7–§13 (Half B; SS-5..SS-11) · `docs/research/architecture-gap-audit-2026-06.md` C6 (+ M5 Router, M3 TTL cache) · `docs/decision-log-additions-proposed.md` §40 (C6 — `probe(point, when)` signature, `health()`; lives in the *additions-proposed* file, as the committed `decision-log.md` ends at §31) · `docs/decision-log.md` §28 (live never persisted as nodes; access-invariant) · §29 (cost lever / TTL cache) · CLAUDE.md rules #1 (source-or-silence), #2 (confidence ≠ rank penalty), #3 (graph holds slow data only), #6 (degrade-and-disclose), #10 (secrets from store)

---

## Capability statement

Live-condition sources become a config-driven, pluggable seam: every live source
implements one `LiveAdapter` contract, and the Verifier resolves probes from a
registry **keyed by `ConditionKind` with ordered primary→fallback**. A condition
(e.g. weather) can be backed by redundant providers, `health()`-driven failover
swaps a `down`/`rate_limited` primary for its secondary, and per-region capability
gating excludes a source where it has no authority — all without touching
`verify()`'s invariant, the Curator's verdict logic, or confidence. Adding a live
source becomes **one adapter file + one config line, zero downstream change**.
Valhalla drive-time is folded in as a `drive_time` adapter behind this same contract
(absorbing Epic 005's M5 Router, so there is no standalone collision), and a
per-source TTL cache (M3) lives in the registry.

## Architectural context

**Builds on:**
- `orchestration/adapters/base.py` — today holds **only** `VerifiedFact` (the audit's
  exact C6 finding: "no adapter interface"). Reused **by name** as the probe return —
  it already carries `value`, `source`, `fetched_at`, `confidence_inputs`, `disclosures`,
  i.e. source-or-silence + degrade-and-disclose materialized (rules #1/#6).
- `orchestration/verifier.py` — `build_probes(settings)` (hardcodes
  `from orchestration.adapters import airnow, firms, nws, ridb, usgs_water`, a per-source
  `if settings.<x>_key:` ladder, inline `partial(...)` to reconcile mismatched signatures)
  and the `verify(lat, lon, probes)` loop over a flat `Mapping[str, Probe]` (works in `(lat,
  lon)` floats — there is **no `Point` type** in `orchestration/` today; see S1/S3).
- `orchestration/adapters/{nws,airnow,firms,usgs_water,ridb,valhalla}.py` — five
  point-probes (`usgs_water` keyless; the rest credential-gated) + the existing Valhalla
  free function `valhalla.fetch(origin, trailhead, base_url)` (Epic 005's M5 Router,
  currently unwired and behind no contract).
- The **proven seam shapes already in-tree**: `orchestration/providers/registry.py`
  (config-driven, `resolve(role, settings)` over `ROLE_TIER`, `ValueError` on unknown
  name — the audit's named positive reference) and `ingestion/watch/base.py::AdapterHealth`
  (`OK`/`NEEDS_REAUTH`/`RATE_LIMITED`/`DOWN`) + `ingestion/watch/registry.py` (Epic 004's
  `enabled_adapters`, `ADVENTURE_WATCH_ADAPTERS`, factory map, loud-on-unknown). This epic
  mirrors both — it is the device seam's miss replicated on the live half. (Note: `watch/base.py`
  already defines a *different* `Capabilities` dataclass — see S1's deliberate parallel-but-distinct
  naming.)

**Enables:**
- Redundant weather (the swap C6 says is impossible today: "weather is permanently == NWS").
- Per-region expansion (a non-US region drops US-only feeds via capability, no code edit).
- The Scout drive-time pre-filter that consumes `drive_time` (origin-relative reachability),
  introduced **new** in this epic behind the contract rather than via a direct `valhalla.fetch`
  import.
- Restores the per-source TTL cost lever (decision-log §29) that currently survives only as
  docstrings.

**Does NOT include:**
- The **CorpusSource** seam (Half A → **Epic 012**) — disjoint code (`ingestion/`), separately
  testable; may run in parallel.
- A **decided** weather-fallback *provider* (SS-11 is 🔶: Open-Meteo/Tomorrow.io are
  illustrative; the chosen provider must pass the §18 open-data/license screen before
  building). This epic ships the *seam* and proves the swap with an in-repo **echo adapter**,
  not a third-party weather fallback.
- The C4 overlay-routing fix (`engine.build_runtime` resolves the `curate`/judge tier with
  **no** `touches_private_overlay`, and Epic 003 feeds the assembled personal overlay into
  that call as `profile=` — so it egresses the instant `ADVENTURE_PROVIDER_CURATE=anthropic`).
  These probe paths touch only the **anonymous world + live layer** — no personal overlay reaches
  any `probe()` (§12) — so C4 is a separate egress hole (its own follow-up), out of scope and not
  foreclosed here.
- New `ConditionKind` members (`snow`/`avalanche` — SS-13 ❓, decided as those sources arrive).

---

## Stories

### S1 — The LiveAdapter contract + behavioral types

**Given** `orchestration/adapters/base.py` holds only `VerifiedFact` and no adapter interface,
and there is no shared `Point` value type in `orchestration/`
**When** the seam is added
**Then** `base.py` defines a `LiveAdapter` ABC plus the behavioral types `ConditionKind`,
`LiveCapabilities`, `AdapterHealth`, **and a `Point` value type** — and `VerifiedFact` is
unchanged and reused by name as the probe return.

*Why:* SS-5 fixes the audit's "no adapter interface" by codifying the four-method contract.
`VerifiedFact` is the proven normalization point (rules #1/#6); reshaping it would be a
gratuitous, downstream-breaking change. A new `LiveCapabilities` (not the existing
`watch/base.py::Capabilities`, which is differently shaped — `has_fit`/`has_readiness`) avoids a
same-named/differently-shaped house-style hazard while still mirroring the device seam. The
contract folds the per-source signature mismatch (NWS `user_agent`, AirNow/FIRMS/RIDB `api_key`,
keyless USGS) *inside* `from_config`, so the call site becomes uniform `adapter.probe(point)` and
the inline `partial(...)` in `build_probes` disappears. A named `Point` is introduced because
today's `(lat, lon)` floats are positional and untyped; the contract uniformizes them rather than
smuggling a type that the in-tree code lacks.

**AC-1.1:** `LiveAdapter(ABC)` declares `name: str`, `kind: ConditionKind`, and abstract
methods `capabilities() -> LiveCapabilities`, `probe(point: Point, when: datetime | None = None)
-> VerifiedFact | None`, `health() -> AdapterHealth`, and `classmethod from_config(settings) ->
LiveAdapter | None`.
**AC-1.2:** `Point` is a value type (frozen dataclass / named tuple) carrying `lat: float`,
`lon: float`; a test asserts `Point(lat, lon)` round-trips and that `scout`/`plan_from_origin`
call sites (the `_latlon` floats) construct it (see S3 AC-3.1).
**AC-1.3:** `ConditionKind` is an enum with exactly `{weather, air, fire, water, permits, drive_time}`.
**AC-1.4:** `AdapterHealth` is an enum with `{ok, needs_reauth, rate_limited, down}`; a test asserts
`{m.value for m in AdapterHealth} == {"ok", "needs_reauth", "rate_limited", "down"}` (value-equal to
`ingestion/watch/base.py::AdapterHealth` for cross-seam consistency).
**AC-1.5:** `LiveCapabilities` exposes booleans `needs_point`, `needs_site_id`, `is_keyless`, and
`supports_region: frozenset[str]`, and is **distinct** from `watch/base.py::Capabilities` (no shared
symbol).
**AC-1.6:** `VerifiedFact`'s fields and name are unchanged (a test imports it by name and
asserts its dataclass fields are exactly `{value, source, fetched_at, confidence_inputs, disclosures}`).
**AC-1.7:** `probe(point, when=None)` accepts a `Point` and an optional `datetime`; instantiating
a class that omits any abstract method raises `TypeError` (ABC enforcement).

### S2 — Kind-keyed probe registry with health-driven failover

**Given** multiple adapters can back one `ConditionKind`
**When** the registry resolves probes
**Then** it returns adapters grouped by kind, ordered primary→fallback (config order), and the
Verifier calls the first adapter whose `health()` permits, falling to the next on
`down`/`rate_limited`.

*Why:* SS-6 — keying by kind with ordered fallback is the structural answer to "weather ==
NWS, no swap path." `health()` is what makes failover real rather than a hope. Mirrors
`providers/registry.py` and `watch/registry.py` (loud on unknown name; silent self-drop on
absent credential).

**AC-2.1:** `orchestration/adapters/registry.py` reads `ADVENTURE_LIVE_ADAPTERS` (e.g.
`nws,airnow,firms,usgs_water,ridb`) and instantiates each via `from_config`, **dropping any
that return `None`** (credential absent).
**AC-2.2:** An unknown adapter name in `ADVENTURE_LIVE_ADAPTERS` raises `ValueError` naming the
offender and the known set (fail loudly at the boundary, mirroring `enabled_adapters`).
**AC-2.3:** `probes_for(region, settings) -> dict[ConditionKind, list[LiveAdapter]]` returns
adapters grouped by `kind`, **ordered by their position in `ADVENTURE_LIVE_ADAPTERS`** (position
sets primary vs. fallback within a kind).
**AC-2.4:** Given a kind with `[primary, secondary]` where `primary.health()` returns `DOWN`,
the Verifier (S3) invokes `secondary.probe` and not `primary.probe`.
**AC-2.5:** Given `primary.health()` returns `RATE_LIMITED`, failover behaves identically
(falls to `secondary`).
**AC-2.6:** Given `primary.health()` returns `OK` and `primary.probe` returns a `VerifiedFact`,
`secondary.probe` is **not** called (first success wins per kind).

### S3 — Reshape verify() to iterate the kind-keyed registry

**Given** `verify(lat, lon, probes)` today iterates a flat `Mapping[str, Probe]` over `(lat, lon)`
floats and keeps what returns
**When** the seam lands
**Then** `verify(point, probes_by_kind)` iterates `kind → [adapter…]` with health-driven
primary→fallback, `build_probes` is replaced by the registry, and **the curator/confidence
consumers are migrated to `ConditionKind` keys** — while the keep-only-what-returned invariant
(source-or-silence) is preserved byte-for-byte.

*Why:* SS-6/§9 are explicit that this is a **real loop-body change, not a no-op**: the body is
rewritten to kind-keyed iteration; what is preserved is the *invariant* (rule #1), not the loop.
Because the result re-keys from `str` to `ConditionKind` (AC-3.2), the downstream consumers that
index by literal kind must move with it — `evaluate_guardrails` does `facts.get("weather")` /
`.get("air")` / `.get("fire")` (in `orchestration/curator.py`), and `engine.py` builds
`{kind: for_fact(fact) …}` and `summarize_fact` lines keyed by kind. A `dict` keyed by
`ConditionKind.weather` does **not** answer `.get("weather")`, so leaving these "unchanged" would
silently break the guardrail path; this story migrates them.

**AC-3.1:** `build_probes` is removed; `engine.build_runtime` and `plan_from_origin` consume the
registry's `probes_for(...)` output instead, and pass a `Point` (no `from orchestration.adapters
import airnow, firms, nws, ridb, usgs_water` and no `partial(...)` remain in `verifier.py`; the
`Probe = Callable[[float, float], …]` alias is removed).
**AC-3.2:** `verify(point, probes_by_kind)` returns `dict[ConditionKind, VerifiedFact]` (keyed by
kind, matching the registry grouping) containing **only** facts that an adapter actually returned.
**AC-3.3:** For a kind whose every adapter returns `None` (or is health-blocked), that kind is
**absent** from the result — never present with a fabricated/empty value (rule #1).
**AC-3.4:** A fact's `source` and `fetched_at` are passed through unmodified from the returning
adapter (no Verifier-side stamping).
**AC-3.5:** `evaluate_guardrails` (in `curator.py`) and the `for_fact`/`summarize_fact` consumers
(in `engine.py`) are migrated to index by `ConditionKind`, and a regression test asserts an existing
guardrail-block path still fires on an NWS red-flag alert routed through the registry (verdict
behavior preserved; key type changed).

### S4 — Per-region probe selection via LiveCapabilities.supports_region

**Given** a US-only feed (e.g. FIRMS) and a non-US region
**When** the registry selects probes for that region
**Then** the US-only feed is **not selected** (capability-gated), rather than returning a
wrong-but-sourced reading.

*Why:* SS-7 — per-region selection is config + capability, never a code change. A source's
authority is geographic; gating on `supports_region` is degrade-and-disclose at selection time
(rule #6), and prevents the worse failure of a sourced-but-wrong reading.

**AC-4.1:** `probes_for(region, settings)` includes an adapter for a kind **only if** the region
is in `adapter.capabilities().supports_region` (an empty/`*` set means region-agnostic — e.g.
`drive_time`).
**AC-4.2:** Given region `"US"`, FIRMS (`supports_region={"US"}`) is selected; given a non-US
region it is excluded, and no `fire` kind appears unless another adapter supports that region.
**AC-4.3:** Region exclusion is **silent and lossless** for the run (rule #6): excluding a feed
never raises and never blocks other kinds.

### S5 — Fold in Valhalla drive-time (M5) and the per-source TTL cache (M3)

**Given** Valhalla is an Epic-005 free function `valhalla.fetch(origin, trailhead, base_url)`,
`scout()` returns pure nearest-k by geographic radius (no drive-time anywhere), and the TTL cost
lever survives only as docstrings
**When** the seam lands
**Then** Valhalla becomes a `ValhallaAdapter(kind=drive_time)` behind the contract, a **new**
origin-relative Scout pre-filter consumes `drive_time` through the registry (not a direct import),
and the registry wraps every `probe()` in a per-source TTL cache keyed by `(name, rounded-point |
site_id)`.

*Why:* SS-9 / audit M5+M3 are an explicit instruction to fold both here. Building Valhalla
behind the contract **from the start** is why this epic supersedes a standalone Epic 005 — there
is no second drive-time code path to collide. The pre-filter is genuinely *new* (today's `scout`
has none), so the reachability/origin plumbing is an explicit deliverable. An OSRM/GraphHopper/
hosted swap becomes one adapter file. The registry is the audit's named natural home for the TTL
cache (restoring the §29 cost lever).

**AC-5.1:** `ValhallaAdapter` implements `LiveAdapter` with `kind=drive_time`; because the
query **origin** is per-request (the `plan()` `origin` arg) and `Settings` has no origin,
`from_config(settings)` returns `None` when the base URL is unset and otherwise builds a
URL-bound adapter, while the **origin is supplied per run** (the adapter is bound to the run's
origin when `probes_for` is resolved, or the origin is passed in the per-probe context alongside
`when`); the Verifier point is the trailhead. `health()` transitions to `DOWN` on connection failure.
**AC-5.2:** A **new** origin-relative pre-filter, fed `drive_time` via the registry, rejects a
candidate whose drive-time exceeds the query's reachability bound (`reachability`/origin plumbed
through `plan`/`plan_from_origin` as part of this epic). No `from orchestration.adapters import
valhalla` appears anywhere outside `valhalla.py` and the registry factory. A candidate with no
`drive_time` fact (adapter absent/`None`) is **not** rejected — degrade-and-disclose; drive-time
is enrichment, not a hard dependency.
**AC-5.3:** `drive_time` is excluded from the per-point Verifier guardrail loop (it is
origin-relative, ranking/pre-filter-side per §9) — `evaluate_guardrails` never receives a
`drive_time` fact.
**AC-5.4:** The registry wraps `probe()` in a TTL cache: a second `probe` for the same
`(name, rounded-point | site_id)` within the adapter's TTL returns the cached `VerifiedFact`
without a second underlying call (asserted via a call-counting fake).
**AC-5.5:** TTL is **per-source** (NWS ~10m, USGS ~15m, AirNow ~60m, FIRMS ~10m — Stage 4 §4):
a cache entry past its source's TTL triggers a fresh `probe`.
**AC-5.6:** Cached facts are **never persisted as graph nodes** (rule #3) — the cache is
in-process/keyed-by-resolution-id only; a test asserts no Neo4j write occurs on a `probe`.

### S6 — Conformance suite + echo-adapter drop-in proof

**Given** a throwaway in-repo `EchoAdapter` added as **only** a new adapter file + a config-list
entry
**When** it is registered and the suite runs
**Then** it passes the shared conformance suite and is selected by the registry — the modularity
claim asserted empirically.

*Why:* §11/§13 — the modularity proof must be *empirical*, not asserted. The echo adapter is the
in-repo proof-of-swap standing in for the not-yet-decided weather fallback (SS-11), so the epic
ships the swap mechanism without prematurely committing to a third-party provider. (The "zero diff
to loop bodies" claim is a reviewer check, captured in the DoD — a pytest assertion cannot verify a
git diff at runtime.)

**AC-6.1:** A `conformance(adapter)` test helper asserts, for any `LiveAdapter`: `probe` returns a
`VerifiedFact` stamped with non-empty `source` + a `fetched_at`, **or** `None` — and **never
raises past the boundary** on an injected transport failure.
**AC-6.2:** The suite asserts `health()` transitions on injected `401` → `needs_reauth`, `429` →
`rate_limited`, `5xx`/connection-error → `down`.
**AC-6.3:** The suite asserts the adapter honors its TTL (a repeat probe within TTL makes no second
underlying call) — reusing the S5.4 call-counting harness.
**AC-6.4:** `EchoAdapter` (a new file `orchestration/adapters/echo.py`, declaring its own `kind`
and `LiveCapabilities`) added to `ADVENTURE_LIVE_ADAPTERS` is **selected by the registry and passes
`conformance`** (runtime-testable; the no-edit-to-`verifier.py`/`registry.py`-loop-bodies claim is a
DoD reviewer check, not an AC).
**AC-6.5:** All five existing adapters (`nws`, `airnow`, `firms`, `usgs_water`, `ridb`) plus
`valhalla` pass `conformance`.

---

## Definition of Done

- [x] All ACs covered by at least one passing test (named per `docs/process/development-process.md`):
      `test_live_base.py`, `test_live_registry.py`, `test_verifier.py`, `test_drive_time.py`,
      `test_live_conformance.py` (+ migrated `test_engine.py`, `test_curator.py`).
- [x] `make check` green (ruff + mypy + pytest) — no new mypy ignores on the contract.
- [x] `LiveAdapter` ABC + `ConditionKind` + `LiveCapabilities` + `AdapterHealth` + `Point` in
      `orchestration/adapters/base.py`; `VerifiedFact` unchanged and reused by name;
      `LiveCapabilities` deliberately distinct from `watch/base.py::Capabilities`.
- [x] `orchestration/adapters/registry.py` (kind-keyed, ordered primary→fallback,
      `supports_region`-gated, TTL-wrapped) mirrors `providers/registry.py` + `watch/registry.py`.
- [x] `build_probes` removed; `verify()` reshaped to kind-keyed iteration over `Point` with
      health-driven failover; keep-only-what-returned (rule #1) preserved and regression-tested.
- [x] Curator/confidence consumers migrated to `ConditionKind` keys: `evaluate_guardrails`
      (`curator.py`) and the `for_fact`/`summarize_fact` call sites (`engine.py`) no longer index by
      string literal; guardrail-block path regression-tested.
- [x] Five existing adapters + `ValhallaAdapter` refactored behind the contract; per-source auth
      moved into `from_config`; no per-source `import` / `partial` / `if settings.<x>_key` ladder
      remains in `verifier.py`.
- [x] Valhalla `drive_time` consumed by a **new** origin-relative Scout pre-filter via the registry
      (M5 folded in; no standalone Epic 005 drive-time path); origin/reachability plumbed through
      `plan`/`plan_from_origin`; `drive_time` excluded from the per-point guardrail loop.
- [x] Per-source TTL cache (M3) in the registry; no live reading persisted as a graph node (rule #3).
- [x] Conformance suite + `EchoAdapter` selected and passing; **reviewer-verified** zero diff to
      `verifier.py` / `registry.py` loop bodies when adding it (file + one factory-map line only).
- [x] `ADVENTURE_LIVE_ADAPTERS` documented in `.env.example`; secrets via `from_config` only (rule #10).
- [x] Targeted self-review agent run (4-lens adversarial workflow over `base.py`, `registry.py`,
      `verifier.py`, `valhalla.py`, `drive_time.py`, `curator.py`, `engine.py`, the conformance
      suite); CRITICALs fixed before commit, MODERATEs fixed or documented here.
- [x] Atomic commits per CLAUDE.md (contract+Point · adapter refactor+Valhalla · registry+TTL ·
      verify-reshape+consumer-migration+drive-prefilter · drive-time tests · conformance+Echo ·
      epic-doc update); `docs/epics/README.md` status column updated on close.
- [x] SS-11 noted as still-open: the weather **fallback provider** is deferred to a follow-up once
      it passes the §18 open-data/license screen; this epic proves the swap with `EchoAdapter` only.

---

## Review outcome (track-c, 2026-06-25)

5-lens adversarial review (Epic-014 preservation lens **clean** — `personalized_judge` privacy
routing survived the engine rewrite). **0 CRITICAL.** Seven findings (5 MODERATE + 2 LOW) all fixed,
each with a regression test where applicable:

1. **`prefilter` outage conflation** (correctness) — a legitimate full prune (all candidates over
   budget / outside the isochrone) was misread as a router outage, restoring pruned trails + a false
   disclosure. Now distinguished via `router_responded` (`test_s4_all_over_budget_prunes_without_false_outage`).
2. **`fetch_matrix`/`fetch_isochrone` raised on malformed-but-200** (MultiPolygon, null coords,
   dict-shaped matrix) → now degrade to None/all-None like `probe()` (`test_s4_*_degrades_on_*`).
3. **`verify()` health-before-every-probe** — `health()` is now consulted only for kinds with a real
   fallback candidate; a lone adapter probes directly (no wasted GET / quota / self-rate-limit).
4. **`TTLCache` unbounded growth** — expired entries evicted on read + a `MAX_CACHE_ENTRIES` FIFO cap.
5. **`verify(cache=…)` short-circuit untested** — added a test that a fresh cache hit skips both
   `health()` and `probe()` (`test_s5_ac4_cache_hit_short_circuits_health_and_probe`).
6. **`ValhallaAdapter.with_origin` dead code** — removed; docstring corrected to the per-call origin wiring.
7. **`enabled_adapters` ran twice per `build_runtime`** — the drive-time computer is now derived from
   the single `probes_for` result.
