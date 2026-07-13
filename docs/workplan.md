# Adventure Planner — Design Workplan (Working Agenda)

*Companion to the Decision Log. Last updated July 13, 2026.*

**Roles of the two docs.** The **Decision Log** = system-of-record for *what we've decided* (state). This **Workplan** = system-of-record for *the ordered path through what's still open* (process). We work the stages below one at a time; each session's outputs get written back into the Log.

**How to read each topic.** *Depends on* (what must be settled first) · *Produces* (the decisions/artifacts it yields) · *Key questions* (what we resolve in it) · *Spike?* (better answered by a tiny experiment than discussion).

**Why this order.**
1. **Foundations before surface** — things costly to retrofit (data model, access-control pattern, provenance/confidence) before cheap-to-change things (UX, design system).
2. **Dependency-respecting** — never design X before the thing X assumes.
3. **De-risk early** — unknowns that could invalidate downstream design (conflation, token cost) come first.
4. **Vertical-slice checkpoint** — Stages 1–4 fully design the Phase-0 spine; we can build something real there before going wider.
5. **Cross-cutting threads pulled out of the line** — a few concerns (infra/secrets, access-control discipline, the commons write, eval, UX, legal) run *through* all stages rather than sitting at one point; listed separately so they're honored continuously.

---

## Cross-cutting threads (run through everything — not a single stage)

- **T1 · Infra / secrets / repo / CI / storage / backup.** Minimal setup at the very start (✱ **secrets handling is critical from the first commit** — Garmin login + API keys), grows per phase.
- **T2 · Access-control-at-query-layer discipline.** Honored from the moment the graph exists (Stage 2) — never write a query that can't later be permission-scoped — even though the full grant system is *designed* in Stage 8.
- **T3 · The forked commons write.** Switched on cheaply early (Phase 0/1); aggregation designed late (Stage 9). Starting the accretion early is what makes the commons viable later.
- **T4 · Evaluation.** A thin **truthfulness** check rides with Phase 0 (Stage 4); the **deep stochastic-flow methodology** is its own Stage 7 once there's a real flow to evaluate.
- **T5 · UX.** Each phase needs *just enough* UX to be usable; the **deep experience + design system** work is Stage 10, once the system's real behavior exists to design against.
- **T6 · Legal / licensing / consent.** Source-ToS swappability honored from Stage 1; **OSM/ODbL + consent flows must be resolved before the commons goes public** (gates Stage 9's public release).
- **T7 · Naming / branding.** Anytime.

---

## Stage 0 — Project setup *(light, kicks off T1)*
- *Produces:* repo structure (monorepo: ingestion / orchestration / graph+migrations / API / frontend / evals), secrets store, minimal CI, env scaffolding.
- *Key questions:* repo layout; secrets mechanism; local dev environment (local Neo4j).
- *Note:* deliberately minimal — just enough to start committing safely.

## Stage 1 — Data source landscape  ◀ **START HERE**
*The whole system is verified synthesis over data; we can't design the schema, engine, or confidence model until we know what raw material actually exists, in what shape, at what quality.*
- *Depends on:* nothing.
- *Produces:* a **source catalog** — per source: coverage, format, access method, license, freshness, update cadence, and **corpus-vs-live classification**.
- *Sources to evaluate:* OSM (Overpass + extracts), **USFS** (Enterprise Data Warehouse — trails, recreation sites, MVUM), USGS (National Digital Trails/TRAILS, 3DEP elevation, Water Services streamflow), NPS (park + trail data), Recreation.gov RIDB (permits/campsites), NWS (api.weather.gov), NASA FIRMS (fire), EPA AirNow (AQI), PAD-US (protected-lands boundaries), state/local (e.g. Virginia DCR), avalanche.org (winter, later). + anything else reasonably tappable.
- *Key questions:* what each genuinely offers vs. duplicates; which feed the **corpus** (slow) vs. **live** (fast); coverage gaps on the East Coast; license obligations (feeds T6); the "authority" tiering that the confidence model will need.
- *Spike?* **Yes — conflation reality check:** pull the *same* few real trails from OSM/USGS/USFS and see how hard merging them actually is. This de-risks Stage 2's schema and Stage 3's pipeline more than any amount of discussion.

## Stage 2 — Data model & graph foundation *(costly to retrofit)*
- *Depends on:* Stage 1 (the data's real shape).
- *Produces:* the **graph schema** — canonical world nodes (trail / segment / trailhead / area), the **provenance model** (source attribution as edges, `SAME_AS` resolution), attachment points for the private overlay and the commons layer, the **confidence model's** storage/computation (the three axes → score), and a schema-versioning approach.
- *Key questions:* what *is* a "destination" vs. a trail vs. a segment; how provenance is structured so "which source said what" is queryable; how confidence is stored vs. computed-on-read; how the overlay/commons hang off shared nodes.
- *Note:* honors T2 from here on.

## Stage 3 — Corpus pipeline *(turns sources into the indexed graph)*
- *Depends on:* Stages 1–2 + the conflation spike.
- *Produces:* the ingestion architecture (bulk load → transform → validate/hygiene → conflate → dedup → load), refresh cadence + idempotency, geographic scoping + expansion strategy — and the **first real East-Coast regional corpus**.
- *Key questions:* transform/normalization rules; the data-hygiene ruleset; how monthly refresh reconciles changes; how the region boundary is defined and widened.

## Stage 4 — Engine + live data + cost *(the Phase-0 spine)*
- *Depends on:* Stage 3 (a corpus to run against).
- *Produces:* the **orchestration substrate choice**; **Scout** (candidate generation); **Verifier** (live-call logic + the per-source live adapters + source-or-silence enforcement); **Curator** (constraints-as-filters + ranking); a thin **truthfulness eval** (T4); and a **real cost number**.
- *Key questions:* Claude API + which framework? MCP-native or direct calls for which pieces? how agents pass control (= the design/runtime-separation question); caching/TTLs; model tiering.
- *Spike?* **Yes — token cost-per-session:** run the real flow against the real corpus and *measure*, don't estimate. Sets the cost model and the caching/tiering levers.

> **◆ Checkpoint:** Stages 1–4 fully design **Phase 0** — the end-to-end verified-synthesis slice is buildable here. Good place to build before going wider.

## Stage 5 — Memory & personalization
- *Depends on:* Stage 4 (what gets personalized) + Stage 2 (where beliefs live). Independent of multiplayer → comes before it.
- *Produces:* belief-store schema (provenance + confidence + timestamp + type); episode model; **episode→semantic promotion rules** (capability-vs-preference tagging); decay model; novelty/explore-exploit mechanism; memory retrieval / **context-assembly** (subgraph selection); memory evals (on vs. off).
- *Key questions:* the entry schema; when a behavior hardens into a belief; how the right subgraph is selected per query; how decay is parameterized.

## Stage 6 — Watch integration
- *Depends on:* Stage 5 (memory schema to feed).
- *Produces:* Garmin access (library/MCP + auth + fragility handling), Coros access (official MCP), FIT parsing, the **readiness filter** logic, polling/ingestion jobs + the **always-on** decision, final sync UX (mostly designed).
- *Key questions:* the FIT-to-episode extractor details; readiness-filter composition (solo + party); where the poller runs.

## Stage 7 — Evaluation deep-dive *(the hard, role-defining one)*
- *Depends on:* Stages 4–6 (a real stochastic, personalized flow to evaluate).
- *Produces:* the **eval methodology for stochastic multi-agent flows** (scenario definition, N-run pass rates, regression across versions, the LLM-judge for the soft half), the golden-trip ground-truth set, the full test strategy (unit / integration / eval-as-test / **security+privacy tests**), and metric definitions.
- *Key questions:* how to score a flow whose output changes every run; how to bootstrap the golden set; what "truthful" and "good recommendation" measure precisely.

## Stage 8 — Multiplayer & privacy *(big additive layer; needs always-on infra)*
- *Depends on:* Stages 5–6 solid; honors T2 throughout.
- *Produces:* identity/household + account model; auth mechanism + provider; the **grant/permission model** (schema + semantics); the **access-control-at-query-layer implementation**; the **party-composition algorithm** (constraint merge / readiness gate / taste merge — "minimize the bigger disappointment"); sharing UX (request-approve, tiers, revoke).
- *Key questions:* household↔member↔dependent (Ruby) modeling; auth provider; the grant tuple + provenance-stop semantics; the preference-merge algorithm.

## Stage 9 — Commons *(needs volume; gated by T6 for public release)*
- *Depends on:* Stage 6 (the episode pipeline); T3 (write already accreting).
- *Produces:* the de-identification pipeline (sever link / endpoint-trim), k-anonymity + aggregation design, capability-band computation, the **pace-calibration model** first, then other emergent attributes.
- *Key questions:* the k threshold (= the confidence floor); contributor-side band computation; the pace model itself; differential-privacy posture.
- *Gate:* OSM/ODbL + consent resolved (T6) before anything public.

## Stage 10 — Experience & design system *(deep UX; T5 culminates)*
- *Depends on:* real system behavior from earlier stages (design against actual outputs, not imagined ones).
- *Produces:* full UX flows (the 9 surfaces + 3 loops), feed/card design, **confidence/staleness rendering** as first-class UI states, onboarding incl. the **anonymous path**, cold-start calibration, the **design system** (token-first → Tailwind/web + SwiftUI/native), and the **calm-utility aesthetic stance**.
- *Key questions:* card anatomy; how honesty (confidence, "unverified," "verify before you go") renders without clutter; the onboarding-vs-anonymous split; the token model.

## Stage 11 — Native shell + polish
- *Depends on:* a proven web product.
- *Produces:* SwiftUI app, reliable push (APNs), background location/geofencing, on-trail offline, design-system maturation.

---

## Stage ↔ Phase map
- **Phase 0** (spine) ≈ Stages 1–4 · **Phase 1** (personal intelligence) ≈ Stages 5–6 (+ Stage 7 supports) · **Phase 2** (multiplayer) ≈ Stage 8 · **Phase 3** (commons) ≈ Stage 9 · **Phase 4** (native + polish) ≈ Stages 10–11.
- Threads T1–T7 run across all phases.

## Dependency spine (one line)
**Data reality → Schema/graph → Corpus pipeline → Engine + cost → Memory → Watch → (deep Eval) → Multiplayer → Commons → deep Experience → Native**, with infra/secrets, the access-control discipline, the commons write, eval, UX, and legal threaded throughout.
