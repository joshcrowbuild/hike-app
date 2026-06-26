# Research Index

*The map for `docs/research/` — what each design/research doc is, its lifecycle status, and when to read it. Kills the "guess-and-sample 27 files" problem.*

> **This is a static index, not a status dashboard.** The `STATUS` column is a coarse **doc lifecycle** badge, not live build state. For live build status / what's next, the SSOT is **[`../process/roadmap.md`](../process/roadmap.md)**; per-epic status is **[`../epics/README.md`](../epics/README.md)**; decisions are **[`../decision-log.md`](../decision-log.md)**.

**STATUS legend**
- `ACTIVE` — live design/reference; still the working spec.
- `IMPLEMENTED (Epic NNN)` — the design shipped; kept as spec provenance (design narrative ≠ stale memory).
- `SUPERSEDED` — replaced by a newer version of the same doc.
- `CLOSED AUDIT` — a fully-actioned, point-in-time review; archived in `archive/` (read only for provenance).

---

## Stage design line (dependency-ordered)

| Doc | Status | Purpose · read when |
|---|---|---|
| [stage-1-data-sources.md](stage-1-data-sources.md) | `ACTIVE` | Open-data source catalog (corpus-vs-live, authority tiers, license, conflation). **Read when** wiring an ingestion/live adapter or checking a source's format/auth/license. |
| [stage-2-schema.md](stage-2-schema.md) | `IMPLEMENTED (Epics 010/011/015)` | Graph schema, `SourceRecord`/`SAME_AS` provenance, computed-on-read confidence, `scopedQuery` access seam. **Read when** touching the schema, provenance, or access wrapper. |
| [stage-3-corpus-pipeline.md](stage-3-corpus-pipeline.md) | `IMPLEMENTED (Epic 012)` | Corpus ingestion pipeline (fetch→transform→hygiene→conflate→load), refresh/idempotency. **Read when** working ingestion, conflation, or refresh. |
| [stage-4-engine-and-cost.md](stage-4-engine-and-cost.md) | `IMPLEMENTED (Epic 013)` | Scout→Verifier→Curator engine, provider/model seam, live-adapter pattern, truthfulness eval, cost model. **Read when** working the engine, provider seam, or live adapters. |
| [stage-5-personalization.md](stage-5-personalization.md) | `IMPLEMENTED (Epics 001–005, 010)` | Belief store, episode→semantic promotion, decay, query-time context assembly, watch discipline. **Read when** working beliefs, episodes, or context assembly. |
| [stage-6-watch-integration.md](stage-6-watch-integration.md) | `ACTIVE` (largely impl: Epics 004/010; readiness 007 + R7 remain) | Garmin/Coros ingestion, FIT extraction, belief updates, readiness filter. **Read when** working watch ingestion, FIT mapping, or readiness. |
| [stage-7-eval-methodology.md](stage-7-eval-methodology.md) | `ACTIVE` (Epic 009 defined, unbuilt) | Eval methodology for the stochastic flow: N-run pass rates, golden trips, scored LLM-judge. **Read when** building/extending the eval harness. |
| [stage-8-multiplayer-privacy.md](stage-8-multiplayer-privacy.md) | `ACTIVE` (Phase 2; §0 preconditions CLOSED by 011/014/015) | Household/auth model, grant/permission model, query-layer access, party composition. **Read** before building multiplayer/sharing. |
| [stage-9-commons.md](stage-9-commons.md) | `ACTIVE` (write half built — Epic 010; read/aggregation half future) | De-identified commons aggregation, k-floor, capability bands, DP posture. **Read when** building the commons read/aggregation half. |

## Cross-cutting seams & threads

| Doc | Status | Purpose · read when |
|---|---|---|
| [t6-licensing-consent.md](t6-licensing-consent.md) | `ACTIVE` (commons write + source seams built; public-release gate future) | OSM/ODbL obligations, source-swappability discipline, commons consent, the Stage-9 public-release gate. **Read when** working licensing, consent, or source swappability. |
| [device-integration-seam.md](device-integration-seam.md) | `IMPLEMENTED (Epic 004)` | Config-driven device-provider seam (Garmin/Coros + future vendors). **Read when** adding a device-vendor adapter. |
| [source-seams-corpus-and-live.md](source-seams-corpus-and-live.md) | `IMPLEMENTED (Epics 012/013)` | CorpusSource + LiveAdapter contracts, registries, conformance suites. **Read when** adding a corpus source or live-condition adapter. |
| [novelty-filter-spec.md](novelty-filter-spec.md) | `ACTIVE` (basis for Epic 006, unbuilt) | Curator novelty filter — `been_on` surfacing, soft recency/repeat discount, explore/exploit dial. **Read when** implementing novelty ranking. |

## UX & design system

| Doc | Status | Purpose · read when |
|---|---|---|
| [design-system-v0.1.md](design-system-v0.1.md) | `ACTIVE` | Design-system contract: DTCG/Style-Dictionary tokens, honesty primitives (confidence/staleness/verify), owned-component stack, §14 done-bar. **Read when** building/refactoring frontend tokens or components. |
| [home-curation-prototype-spec-v0.3.md](home-curation-prototype-spec-v0.3.md) | `ACTIVE` | Home/Curation UI spec: peer card set, decidable-at-rest cards, calm tuning, cartographic-matte visual system. **Read when** building/reviewing the Home/Curation UX. |
| [home-curation-prototype-spec-v0.2.md](archive/home-curation-prototype-spec-v0.2.md) | `SUPERSEDED` by v0.3 (archived) | Older Home/Curation draft. **Read** the v0.3 successor instead; kept for design provenance. |
| [outcome-card-ux.md](outcome-card-ux.md) | `ACTIVE` (pre-Stage-10 exploration) | Outcome Card / Belief Store / Readiness Filter wireframes + durable invariants. **Read when** designing the personal-intelligence UI. |
| [ui-brief-v0.2.md](ui-brief-v0.2.md) | `IMPLEMENTED (PR #22)` | UX north-star brief: "quiet premium utility" posture, card model, trust + belief layers, visual language. **Read when** designing app UX or visual language. |
| [ux-assembly-plan-v1.md](ux-assembly-plan-v1.md) | `IMPLEMENTED (PR #22; PR-E/F deferred)` | Frontend UX assembly plan: VM/adapter seam, mock/http adapters, persona-review (R1–R12) binding constraints. **Read when** working the frontend screens or VM seam. |

## Archived (provenance only)

*Off the live surface in [`archive/`](archive/) (see [`archive/README.md`](archive/README.md)). Closed audits + folded/superseded drafts — read only to trace history.*

| Doc | Status | Purpose · read when |
|---|---|---|
| [decision-log-additions-proposed.md](archive/decision-log-additions-proposed.md) | `FOLDED` → archived | §32–§40 folded into [`../decision-log.md`](../decision-log.md) (Part VII); the archived copy keeps the full forensic detail. |
| [architecture-gap-audit-2026-06.md](archive/architecture-gap-audit-2026-06.md) | `CLOSED AUDIT` | The cross-lens gap audit that seeded Epics 010–015 (findings C1–C6). **Read** for historical provenance only. |
| [self-review-2026-06.md](archive/self-review-2026-06.md) | `CLOSED AUDIT` | 2026-06-23 rules-compliance + consistency self-review (2 CRITICALs fixed). **Read** for provenance only. |
| [integrated-remediation-review-2026-06.md](archive/integrated-remediation-review-2026-06.md) | `CLOSED AUDIT` | Merged-trunk integrated remediation review (1 CRITICAL + 4 MODERATE). **Read** for provenance only. |
| [conflation-review-2026-06.md](archive/conflation-review-2026-06.md) | `CLOSED AUDIT` | First-ingest OSM×NPS×USFS conflation diagnosis. **Read when** investigating conflation/dedup quality (historical). |
| [api-verification-2026-06.md](archive/api-verification-2026-06.md) | `CLOSED AUDIT` | Live-endpoint field verification (USGS/NWS/USFS/NPS). **Read when** debugging a live adapter's field mappings (historical). |
