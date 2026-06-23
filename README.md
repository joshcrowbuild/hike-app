# Adventure Planner *(working title)*

A personal, agentic, self-verifying hiking/backpacking trip planner. A calm, private **utility** — not social, not engagement-seeking.

> **Status: design complete for Phase 0; scaffold in place; no app logic yet.** The Phase-0 design (Stages 1–4) is worked to completeness — data-source landscape, schema, corpus pipeline, engine + cost — because those foundations are expensive to retrofit. The repo skeleton (monorepo packages, provider seam, local Neo4j, CI) now exists as **stubs and contracts**; the engine/pipeline are implemented from Stage 4 onward. See the workplan for the dependency-ordered path.

## The one-line thesis
AllTrails has no trail-data moat (the map is open data). The differentiation is **temporal + personal, not volumetric** — *live, verified synthesis at decision time* ("right now, for me and my party"), which a static app structurally can't be.

## Architecture in one breath
Four layers — indexed **corpus** (slow, bulk-ingested: OSM/USGS/USFS/NPS) → background **ranking** → **JIT live verification** (NWS, USGS streamflow, FIRMS, AirNow, RIDB) → calm curated **feed**. Engine mirrors a multi-agent concierge: **Scout** (candidates) → **Verifier** (live calls, source-or-silence) → **Curator** (constraints + taste + novelty + party). Data model is a **Neo4j property graph**: world nodes shared, personal overlay private, commons derived-on-shared.

## Docs
- [`CLAUDE.md`](./CLAUDE.md) — lean working brief + the non-negotiable rules that must hold in all code.
- [`docs/decision-log.md`](./docs/decision-log.md) — **state**: everything decided (✅ decided · 🔶 confirm · ❓ open).
- [`docs/workplan.md`](./docs/workplan.md) — **process**: the dependency-ordered 11-stage agenda + cross-cutting threads.

## Current position
**Phase-0 design complete** (Stages 1–4, in [`docs/research/`](./docs/research/) + the decision log) and **Stage 0 scaffold in place**. Next: build the Phase-0 vertical slice against the Shenandoah + GW&Jefferson pilot region, plus the Stage-4 cost-measurement spike. Work proceeds in dependency order per the workplan.

## Repo layout (monorepo)
`ingestion/` (Stage-3 pipeline) · `orchestration/` (engine + provider seam + live adapters) · `graph/` (schema + access wrapper) · `api/` (TBD) · `frontend/` (TBD) · `evals/` · `regions/` (boundary polygons). Most modules are documented stubs until their stage is built.

## Local development
Prereqs: Python 3.11+, Docker (for Neo4j), and — for real runs — a local OpenAI-compatible model server (Ollama / vLLM / LM Studio). Then:

```sh
cp .env.example .env          # fill in NEO4J_PASSWORD + any source keys
make install-dev              # editable install + lint/type/test tooling
make check                    # ruff + mypy + pytest (the CI triplet)
make db-up && make schema     # start local Neo4j and apply graph/schema.cypher
```

Run `make help` for all targets. Secrets live only in `.env` (git-ignored) — never in the repo (CLAUDE.md rule #10).
