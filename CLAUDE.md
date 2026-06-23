# CLAUDE.md — Adventure Planner

A personal, agentic, self-verifying hiking/backpacking trip planner. A calm, private **utility** — not social, not engagement-seeking. (Working title.)

> Keep this file lean. The full design lives in the two docs below — read the relevant sections when working a stage. Push stage-specific detail into `.claude/rules/*.md` as code grows. **Delete anything stale — wrong memory is worse than none.**

## Canonical design docs (read on demand)
- `docs/decision-log.md` — **state**: everything decided, with a ✅/🔶/❓ legend.
- `docs/workplan.md` — **process**: the dependency-ordered 11-stage agenda + cross-cutting threads.
- `docs/research/` — **research outputs** per stage. `stage-1-data-sources.md` = the data-source landscape catalog (corpus/live split, authority tiers, license obligations, coverage gaps, conflation verdict).
- **Current position:** **Phase-0 design complete** (Stages 1–4: sources → schema → corpus pipeline → engine+cost) + **Stage 5 personalization design complete** (belief store, episode→semantic promotion, decay model, context assembly, watch-data discipline, privacy tiers — all in `docs/research/stage-5-personalization.md` + `decision-log.md` §30). Stage 0 scaffold in place (monorepo packages, provider seam, local Neo4j compose, CI — stubs/contracts, no app logic). **Next:** build the Phase-0 vertical slice against the Shenandoah+GWJ pilot region + the Stage-4 cost spike; then Stage 6 (watch integration) to complete Phase 1. Work in dependency order per the workplan.

## Non-negotiable rules (must hold in all code)
1. **Source-or-silence.** Every user-facing fact is backed by a live call with source + timestamp. Unverifiable → *flagged*, never fabricated.
2. **Confidence is one property** (freshness · authority · corroboration). It sets a *floor*, the *presentation* (hedged when low), and a *safety flag* — and it **never penalizes ranking**. Uncertainty ≠ low quality.
3. **Graph holds slow/structural data only.** Fast/ephemeral data (weather, streamflow, AQI, permit availability) is fetched JIT and overlaid — never persisted as nodes to expire.
4. **Access control at the query/data layer, never in the agent.** Every Cypher traversal is permission-scoped to the viewer; never emit a query that could return ungranted nodes. Honor this from the first schema, even before the grant system exists.
5. **Private-by-default personal overlay; shared-by-exception.** Share the *derived conclusion*, never the *raw substrate* (a grant is a stop-point on a provenance edge).
6. **Watch data is enrichment, never a dependency.** Every use degrades-and-discloses. Built watch-free first. Ingestion is async + idempotent; never blocks.
7. **Provenance + confidence + timestamp on every user-belief.** An inference never poses as a stated fact. **Capability ≠ preference** (the watch is a good capability sensor, a poor preference sensor).
8. **Commons: fork the FIT write early** (de-identified, endpoint-trimmed) so it accretes; aggregate only above the k-anonymity threshold (= the confidence floor).
9. **No model training.** Pure orchestration.
10. **Secrets never in the repo.** Garmin login + API keys live in a secrets store from the first commit.

## Architecture in one breath
- **Four layers:** indexed corpus (slow, bulk-ingested — OSM/USGS/USFS/NPS) → background ranking → JIT live verification (NWS, USGS streamflow, FIRMS, AirNow, RIDB) → calm curated feed.
- **Engine:** Scout (candidates) → Verifier (live calls, source-or-silence) → Curator (constraints-as-filters + taste + novelty + party).
- **Data model:** Neo4j property graph. World nodes shared; personal overlay private; commons derived-on-shared.
- **MCP only for agent-facing live tools** (Coros official MCP, Garmin); **batch ingestion = ordinary scheduled jobs**, not MCP. Polling needs an always-on host (later); not a Phase-0 concern.
- **Identity:** a household of individual members (each = own login + watch connections + private overlay + grants). Ruby = a dependent node, not an account. Auth boundary = the shared/private boundary; anonymous browsing of the world + live conditions is a real product.

## Stack & conventions — SET IN STAGE 0
- Language / runtime: Python 3.11+ (ingestion + orchestration); frontend TBD
- Orchestration: code-orchestrated Scout/Verifier/Curator workflow (no agent framework)
- Model providers: **provider-agnostic, local-first** — thin seam (`extract`/`normalize`/`judge`), local/self-hosted (OpenAI-compatible: Ollama/vLLM/LM Studio) default, **Anthropic SDK (Claude) hot-swappable as the yardstick**; route by data sensitivity (local for the private overlay). Provider+model+tier in config (`.env`).
- Repo layout: monorepo — `ingestion/` · `orchestration/` (engine + `providers/` seam + `adapters/`) · `graph/` (schema + access wrapper) · `api/` · `frontend/` · `evals/` · `regions/`
- Graph: Neo4j (local Community via `docker compose`)
- MCP config: `.mcp.json` at repo root (empty; MCP deferred to interactive moments — Stage 4 §1)
- Build / test / eval: `make check` (ruff + mypy + pytest) · `make db-up` / `make schema` · `make eval` (Stage 4+). `pip install -e ".[all]"`; see `Makefile` / README.
- Frontend: web/PWA first (server-side watch pull means minimal loss vs. native); native iOS (SwiftUI) later

## Phasing (see workplan for detail)
Phase 0 spine (Stages 1–4) → Phase 1 personal intelligence + watch (Stages 5–6) → deep eval (Stage 7) → Phase 2 multiplayer (Stage 8) → Phase 3 commons (Stage 9) → Phase 4 native + polish (Stages 10–11).
