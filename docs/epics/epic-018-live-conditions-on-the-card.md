# Epic 018 — Live conditions on the card (JIT overlay wiring)

**Status:** IN_PROGRESS
**Phase:** 1 (the thin-cards → live-conditions build; reconciled 2026-07-12 against what actually shipped)
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
- **S6 (latency half) — fan-out cost/latency (PARTIAL, Epic 039 Wave 1).** Returning-visitor paint 0.385s; anon plan cache means cache-hit calls spend zero LLM tokens; per-source TTLs set to CDP-08 volatility windows with stale horizons at 2×TTL. **The cost *read* (R5) is still open** — see below.
- **Substrate from other epics:** NPS closures adapter (Epic 034) and OSM water overlay (Epic 035) are built and cassette-tested; closures participates in the six-state wire today (honestly `not_fetched` until enabled on the deploy).

## What remains (the open scope)

### S4f — Render the six per-kind states in the frontend *(frontend lane — CDP-02's finish half)*
**Given** the API now returns a per-kind `conditions` payload the frontend ignores,
**When** a card (and Detail) renders,
**Then** every kind's disposition is visible through the design system's honesty primitives — and the interim `lines.length === 0 → "not checked"` heuristic in `httpPlanner.ts` (the #160 documented mislabel: an answered-clear card reads as couldn't-verify) is retired.

- **AC-4f.1** Each of the six states renders visibly distinct (glyph + copy, never colour-only): `present`/`stale_degraded` as sourced lines (stale wears its age), `no_hazard` as **calm sourced silence** (never a loud "0 detections"), `no_data` with the adapter's own coverage disclosure, `unavailable` as a legible couldn't-verify, `not_fetched` as a quiet not-checked that can never be mistaken for an outage.
- **AC-4f.2** A card with some kinds present and others absent shows both honestly (no implication the present set is exhaustive).
- **AC-4f.3** Storybook stories cover every state (the blocking a11y CI gate runs on them); vitest locks the wire→VM mapping and the heuristic's retirement.

### S2 — Provision + enable the keyed/remaining sources *(ops lane — needs owner accounts)*
**Given** AirNow/FIRMS/RIDB require API keys (NPS closures needs only enabling),
**When** keys are provisioned into Render config and `ADVENTURE_LIVE_ADAPTERS` is extended,
**Then** air, fire, closures, and permits flip from `not_fetched` to real dispositions where available.

- **AC-2.1** Obtain + store `AIRNOW_API_KEY`, `FIRMS_MAP_KEY`, `RIDB_API_KEY` in Render (secrets only, Rule #10); extend `ADVENTURE_LIVE_ADAPTERS` (incl. `nps_alerts`); `probes_available` reflects the new kinds.
- **AC-2.2** A missing key still self-drops that adapter cleanly (`from_config → None`); a partial key set never 500s; absent kinds stay honestly `not_fetched`.

### S6c — The cost read *(small ops task — the R5 tie-in)*
- **AC-6c.1** Read `feed_cache_hit` rates + `est_tokens` from PlanMetrics in Render logs for the live cost picture (feeds R5); confirm the `/plan` rate-limit covers the fan-out under real traffic.

## Definition of Done (reconciled)
- [x] On the live deploy, an anonymous `/plan` returns cards with real weather + streamflow lines, each naming source + age + confidence (verified 2026-07-11).
- [x] Every kind's absence is a distinct, sourced disposition **on the wire** (PR #160) — never a blank or a false-clear.
- [ ] …and **on the surface**: the frontend renders all six states through the honesty primitives; the `lines.length === 0` mislabel is retired (S4f).
- [x] A verified hazard shows on its card; an unverifiable required condition sets aside with a sourced reason (S5, §41).
- [x] Every adapter is regression-gated by cassette tests + the eval-replay gate in CI.
- [ ] Keyed sources enabled on the live deploy (S2 — ops, needs owner accounts).
- [ ] Live fan-out **cost** measured from Render logs (S6c / R5).

## Risks / notes
- **NWS requires a real `User-Agent`** — set on Render (S1); keep it out of the repo.
- **AirNow is an aggregator** — `present.py` labels it "single aggregated source" (CDP-01); never imply independent corroboration for air.
- **Failover semantics (documented in #160):** a sourced no-data answer terminates a kind's primary→fallback chain; no kind has a coverage-differing fallback today — revisit when one does.
- **Contract discipline:** the `conditions` wire shape is contract-locked (the three-way maps-contract test); any change gets a frozen contract test first.
