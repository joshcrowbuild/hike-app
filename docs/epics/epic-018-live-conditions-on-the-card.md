# Epic 018 — Live conditions on the card (JIT overlay wiring)

**Status:** REVIEW
**Phase:** 1 (the thin-cards → live-conditions build; reconciled 2026-07-12 against what actually shipped; open scope closed 2026-07-12 — S4f/S2/S6c struck below)
**Spec refs:** Rules #1/#2/#3 (source-or-silence · confidence-as-one-property · slow-corpus + JIT overlays) · `docs/vision.md` Pillars 1+2 · `docs/research/cdp-01-corroboration-feasibility-spike.md` · CDP-02 (legible silence) · CDP-08 (per-data-type freshness)

> **Reconciled 2026-07-12.** This epic was written when `/plan` returned `lines: []`. Most of it has since shipped across other lanes (PRs #34/#35 substrate, #53/#54, the 2026-07-01/02 guardrail decisions, PR #160's per-kind condition wire) — this rewrite strikes the built stories, keeps only the genuinely-open scope, and records the evidence. The original silence vocabulary ("four states") is superseded by the shipped six-state wire.

---

## Capability statement
A trail card shows **real, sourced live conditions** — weather, streamflow, air, fire, closures, permits — each stamped with its source, its age, and an honest confidence; and when a condition is absent it shows *legible silence*, never a blank or a false-clear. This is the vision's central payoff: the honesty primitives stop being decoration and start carrying real JIT-verified facts.

## What has shipped (struck stories, with evidence)

- **S1 — keyless probes live (DONE).** `ADVENTURE_LIVE_ADAPTERS=nws,usgs_water` is set on Render; live `/plan` re-verified 2026-07-11 (roadmap v12/v14): real cards each carrying sourced+timestamped **NWS weather** + **USGS gauge** lines with honest single-source labels. `GET /health` exposes `probes_available`.
- **S3 — adapter hardening + regression gate (DONE).** Cassette record/replay tests run in CI for every adapter (`tests/test_adapter_cassettes.py`); the **source-or-silence eval-replay gate** (PR #157, Epic 009's regression half) replays golden trips through the real engine on every PR; adapter three-way contracts (answered / answered-empty / couldn't-verify) locked in PR #160, including the parse-failure-vs-answered-empty regressions. Timeouts + per-source TTL cache active (`adapters/registry.py`).
- **S4 (backend half) — per-kind condition dispositions (DONE, PR #160).** Every card carries a `conditions` array: one `ConditionStatus` per point kind — `present | stale_degraded | no_hazard | no_data | unavailable | not_fetched` — with source + `checked_at` set exactly when a source answered. Adapters split "couldn't verify" (`None`) from an *answered* empty (USGS no-gauge → sourced `gauge_available:false`; NPS no-unit-in-range → `in_range:false`; zero relevant alerts / hotspots → checked-clear). Wire: `ConditionStatusResponse` on `FeedCardResponse`, contract-locked; live prod probed 2026-07-11 — the payload serves (weather/water `present`; air/fire/closures/permits honestly `not_fetched`).
- **S5 — guardrail interplay (DONE, decisions of 2026-07-01/02 + decision-log §41).** A **verified** hazard stays a card wearing a prominent, source-stamped `warnings[]` entry — never hidden, never set aside. Set-aside is reserved for the unverifiable class and hard thresholds, disclosed with cause + source on the wire (`set_aside`); an unverifiable non-required condition is disclosed on the card (`unavailable`), never a reason to blank the feed (rule #6). Regression-gated by the `guardrail-trip-aqi` and `hazard-warning-flashflood` golden scenarios.
- **S6 — fan-out cost/latency (DONE: latency Epic 039 Wave 1; cost read closed v17).** Returning-visitor paint 0.385s; anon plan cache means cache-hit calls spend zero LLM tokens; per-source TTLs set to CDP-08 volatility windows with stale horizons at 2×TTL. The cost *read* (S6c/R5) closed 2026-07-12 — see the strike below.
- **Substrate from other epics:** NPS closures adapter (Epic 034) and OSM water overlay (Epic 035) are built and cassette-tested; closures is enabled on the deploy since the v17 key flip and serves real dispositions in the six-state wire.

## What remains (the open scope)

*Nothing — the last three stories closed 2026-07-12 (struck below with evidence).*

- **S4f — six per-kind states render in the frontend (DONE, PR #162 / roadmap v15).** Card + Detail render every disposition through the honesty primitives: checked-clear as calm sourced silence, outage through the flagged couldn't-verify treatment (never mistakable for quiet not-fetched); `stale_degraded` wears its age; mixed cards show present + absent kinds honestly. The `lines.length === 0 → "not checked"` heuristic is retired — it survives only for payload-less older backends (`conditions == null`, `frontend/src/data/http/httpPlanner.ts`). 17/17 Storybook stories under the blocking a11y gate; vitest locks the wire→VM mapping; the wave's self-review CRITICAL (stale-while-revalidate serving frozen `conditions`) fixed + regression-tested in the same PR.
- **S2 — keyed sources provisioned + enabled (DONE, roadmap v17 ops day + this lane).** *Ops half (AC-2.1):* all four agency keys (`AIRNOW_API_KEY`/`FIRMS_MAP_KEY`/`RIDB_API_KEY`/`NPS_API_KEY`) live in Render dashboard config (secrets only, Rule #10) with the full `ADVENTURE_LIVE_ADAPTERS` list — live cards verified serving 5–6 sourced+timestamped condition kinds; `probes_available` reflects the probed kinds. Air's first probe read `unavailable` (a 28s AirNow stall) — the honest couldn't-verify, exactly the S3 contract. *Code half (AC-2.2, this lane):* the partial-key behavior is now gate-defended — the full production adapter list with any key subset self-drops cleanly and never raises (`tests/test_live_registry.py` Epic-018-S2 block), a partial key set warms clean so it can never hold `/health` at 503 or 500 a boot, and `probes_available` honestly names only the probed kinds (`tests/test_api_warmup.py`); absent kinds staying `not_fetched` is pinned by `tests/test_condition_states.py` + the `answered-clear-vs-outage` golden scenario. `render.yaml` now declares the live-source env-var contract (`sync: false` — dashboard-owned values, never repo values) so a fresh blueprint provision can't silently drop the keyed sources.
- **S6c — the cost read (DONE, roadmap v17 → R5 CLOSED).** PlanMetrics ground truth read from live Render logs 2026-07-12: **est_cost ≈ $0.0016/cold plan** (Sonnet judge + Haiku intent; the estimator undercounts prompt tokens — order of magnitude stands); `feed_cache_hit` calls spend zero LLM tokens; warmer OFF ⇒ organic-only LLM ≈ $1–2/mo. The `/plan` rate-limit sits in front of the fan-out (regression: `tests/test_api_ratelimit.py`); no breach observed under the v17 ops-day probing (cold `/plan` 7.2s worst / 4.7s typical while probing six kinds) — organic-traffic behavior stays an ordinary ops watch item, not open epic scope.

## Definition of Done (reconciled)
- [x] On the live deploy, an anonymous `/plan` returns cards with real weather + streamflow lines, each naming source + age + confidence (verified 2026-07-11).
- [x] Every kind's absence is a distinct, sourced disposition **on the wire** (PR #160) — never a blank or a false-clear.
- [x] …and **on the surface**: the frontend renders all six states through the honesty primitives; the `lines.length === 0` mislabel is retired (S4f, PR #162).
- [x] A verified hazard shows on its card; an unverifiable required condition sets aside with a sourced reason (S5, §41).
- [x] Every adapter is regression-gated by cassette tests + the eval-replay gate in CI.
- [x] Keyed sources enabled on the live deploy (S2 — v17 ops day; partial-key behavior gate-defended in this lane).
- [x] Live fan-out **cost** measured from Render logs (S6c / R5 — CLOSED v17, est_cost ≈ $0.0016/cold plan).

## Risks / notes
- **NWS requires a real `User-Agent`** — set on Render (S1); keep it out of the repo.
- **AirNow is an aggregator** — `present.py` labels it "single aggregated source" (CDP-01); never imply independent corroboration for air.
- **Failover semantics (documented in #160):** a sourced no-data answer terminates a kind's primary→fallback chain; no kind has a coverage-differing fallback today — revisit when one does.
- **Contract discipline:** the `conditions` wire shape is contract-locked (the three-way maps-contract test); any change gets a frozen contract test first.
