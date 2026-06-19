# Adventure Planner *(working title)*

A personal, agentic, self-verifying hiking/backpacking trip planner. A calm, private **utility** — not social, not engagement-seeking.

> **Status: planning & discovery.** No application code yet. We are deliberately working the design to completeness — data-source landscape, schema, confidence/provenance model, access-control pattern — before building, because those foundations are expensive to retrofit. See the workplan for the dependency-ordered path.

## The one-line thesis
AllTrails has no trail-data moat (the map is open data). The differentiation is **temporal + personal, not volumetric** — *live, verified synthesis at decision time* ("right now, for me and my party"), which a static app structurally can't be.

## Architecture in one breath
Four layers — indexed **corpus** (slow, bulk-ingested: OSM/USGS/USFS/NPS) → background **ranking** → **JIT live verification** (NWS, USGS streamflow, FIRMS, AirNow, RIDB) → calm curated **feed**. Engine mirrors a multi-agent concierge: **Scout** (candidates) → **Verifier** (live calls, source-or-silence) → **Curator** (constraints + taste + novelty + party). Data model is a **Neo4j property graph**: world nodes shared, personal overlay private, commons derived-on-shared.

## Docs
- [`CLAUDE.md`](./CLAUDE.md) — lean working brief + the non-negotiable rules that must hold in all code.
- [`docs/decision-log.md`](./docs/decision-log.md) — **state**: everything decided (✅ decided · 🔶 confirm · ❓ open).
- [`docs/workplan.md`](./docs/workplan.md) — **process**: the dependency-ordered 11-stage agenda + cross-cutting threads.

## Current position
Stage 0 (project setup) → **Stage 1 (data-source landscape)**. Work proceeds in dependency order per the workplan.

## Repo layout (planned monorepo — created as stages need it)
`ingestion/` · `orchestration/` · `graph/` (schema + migrations) · `api/` · `frontend/` · `evals/`
