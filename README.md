# Adventure Planner *(working title)*

A personal, agentic, self-verifying hiking/backpacking trip planner. A calm, private **utility** — not social, not engagement-seeking.

**Last verified:** 2026-06-26 · **Owner:** project

> **Status: Phase-1 build complete.** The engine (Scout→Verifier→Curator), the ingestion/corpus pipeline, backend personalization (Epics 001–005, 010–015), and the personal-intelligence **app UX** (Home/Detail/Tuning/Outcome) are all shipped on `main`. **Live status, open risks & next work live in [`docs/process/roadmap.md`](./docs/process/roadmap.md)** — the single source of truth for status.

## The one-line thesis
AllTrails has no trail-data moat (the map is open data). The differentiation is **temporal + personal, not volumetric** — *live, verified synthesis at decision time* ("right now, for me and my party"), which a static app structurally can't be.

## Architecture in one breath
Four layers — indexed **corpus** → background **ranking** → **JIT live verification** → calm curated **feed** — driven by a Scout → Verifier → Curator engine over a Neo4j property graph (world shared, personal overlay private, commons derived-on-shared). Full version + the non-negotiable rules: [`CLAUDE.md`](./CLAUDE.md).

## Docs
- [`CLAUDE.md`](./CLAUDE.md) — lean working brief + the non-negotiable rules that must hold in all code.
- [`docs/decision-log.md`](./docs/decision-log.md) — **state**: everything decided (✅ decided · 🔶 confirm · ❓ open).
- [`docs/workplan.md`](./docs/workplan.md) — **process**: the dependency-ordered 11-stage agenda + cross-cutting threads.

## Current position
**Phase-1 build complete** — the end-to-end verified-synthesis slice plus personal intelligence (belief pipeline, outcome loop, context assembly, device seam, commons fork) and the app UX are on `main`. For live status, open risks, and what's next, see **[`docs/process/roadmap.md`](./docs/process/roadmap.md)** — the single source of truth for status.

## Repo layout (monorepo)
`ingestion/` (Stage-3 pipeline) · `orchestration/` (engine + provider seam + live adapters) · `graph/` (schema + access wrapper) · `api/` (FastAPI app) · `frontend/` (React/Vite web app) · `evals/` · `regions/` (boundary polygons).

## Local development
Prereqs: Python 3.11+, Docker (for Neo4j), and — for real runs — a local OpenAI-compatible model server (Ollama / vLLM / LM Studio). Then:

```sh
cp .env.example .env          # fill in NEO4J_PASSWORD + any source keys
make install-dev              # editable install + lint/type/test tooling
make check                    # format + lint + mypy + pytest
make db-up && make schema     # start local Neo4j and apply graph/schema.cypher
```

Run `make help` for all targets. Secrets live only in `.env` (git-ignored) — never in the repo (CLAUDE.md rule #10).

## Deploy (API)
The FastAPI backend ships as a Docker web service via `render.yaml` (Render free tier). The frontend deploys separately on Vercel. Click-path + env contract: [`docs/runbooks/deploy-api-render.md`](./docs/runbooks/deploy-api-render.md).
