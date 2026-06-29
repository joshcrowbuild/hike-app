# CLAUDE.md — Adventure Planner

A personal, agentic, self-verifying hiking/backpacking trip planner. A calm, private **utility** — not social, not engagement-seeking. (Working title.)

**Last verified:** 2026-06-26 · **Owner:** project (product invariants + architecture)

> Keep this file lean. The full design lives in the two docs below — read the relevant sections when working a stage. Push stage-specific detail into `.claude/rules/*.md` as code grows. **Delete anything stale — wrong memory is worse than none.**

> Read `AGENTS.md` first for repo operating rules, merge-risk discipline, and Git/PR hygiene. Use this file for product invariants, architecture, and development process.

## Canonical design docs (read on demand)
- **`docs/README.md`** — **the doc map**: read-this-for-that router + always-load/on-demand split + the SSOT table. **Start here.**
- `docs/vision.md` — **north star** (evergreen): the bet, the five pillars, the refusals. *(Vision-owned — ages slowly; sits one altitude above the roadmap.)*
- `docs/strategy/path-to-complete.md` — **the sequenced path** from today's prototype to a complete app: phases A–G, the CDP adopt-queue coverage map, open strategic decisions. *(Vision-PM-owned — the why-this-order; defers to the roadmap on status.)*
- `docs/process/roadmap.md` — **live status** (the dashboard SSOT): current build state, next work, open risks. *(PM-owned — link to it, don't restate it.)*
- `docs/decision-log.md` — **state**: everything decided, with a ✅/🔶/❓ legend.
- `docs/workplan.md` — **process**: the dependency-ordered 11-stage agenda + cross-cutting threads.
- `docs/process/plan-analysis.md` — **readiness audit**: what's well-defined vs. underdefined, build order.
- `docs/process/development-process.md` — **how we work**: epics → stories → ACs → tests → code → targeted review.
- `docs/epics/` (index: `docs/epics/README.md`) — **epic definitions** (Epic NNN = stories + ACs). Check here before coding any feature.
- `docs/research/` (index: `docs/research/README.md`) — **research/design outputs** per stage, indexed with status badges.
- **Current position:** Phase-1 build complete — backend personalization (Epics 001–005, 010–015) plus the personal-intelligence app UX are shipped on `main`. **Live status, baseline & next work → `docs/process/roadmap.md`** (the status SSOT, so this line can't rot).

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

## Stack & conventions *(settled in Stage 0; current)*
- Language / runtime: Python 3.11+ (ingestion + orchestration); TypeScript + React (frontend)
- Orchestration: code-orchestrated Scout/Verifier/Curator workflow (no agent framework)
- Model providers: **provider-agnostic, local-first** — thin seam (`extract`/`normalize`/`judge`), local/self-hosted (OpenAI-compatible: Ollama/vLLM/LM Studio) default, **Anthropic SDK (Claude) hot-swappable as the yardstick**; route by data sensitivity (local for the private overlay). Provider+model+tier in config (`.env`).
- Repo layout: monorepo — `ingestion/` · `orchestration/` (engine + `providers/` seam + `adapters/`) · `graph/` (schema + access wrapper) · `api/` · `frontend/` · `evals/` · `regions/`
- Graph: Neo4j (local Community via `docker compose`)
- MCP config: `.mcp.json` at repo root (empty; MCP deferred to interactive moments — Stage 4 §1)
- Build / test / eval: `make check` (`ruff format --check` + ruff + mypy + pytest) · `make db-up` / `make schema` · `make eval` (Stage 4+). `pip install -e ".[all]"`; see `Makefile` / README.
- Frontend: web/PWA **shipped** — React + React-Aria + vanilla-extract, token-first via Style Dictionary (W3C DTCG), built with Vite + Storybook; Home/Detail/Tuning/Outcome screens. Native iOS (SwiftUI) later. See `docs/research/design-system-v0.1.md`.

## Phasing (see workplan for detail)
Phase 0 spine (Stages 1–4) → Phase 1 personal intelligence + watch (Stages 5–6) → deep eval (Stage 7) → Phase 2 multiplayer (Stage 8) → Phase 3 commons (Stage 9) → Phase 4 native + polish (Stages 10–11).

---

## Development standards (read before writing any code)

The full standards — **Git & commit hygiene, code standards, the review cycle, test standards, and epic/story tracking** — are canonical in **`docs/process/development-process.md`**. The essentials that must always hold:
- **One logical change = one commit**; imperative ≤72-char subject + a *why* body; trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **`make check` green** (`ruff format --check` + ruff + mypy + pytest) before every commit. **Never commit** `.env`, `data/`, commented-out code, debug `print()`, or `# TODO`/`# FIXME`.
- **Fail loudly at boundaries, degrade gracefully at the surface.** New modules get tests before callers.
- **After each epic:** a targeted self-review agent (not `/code-review ultra` for routine work); fix every CRITICAL before the commit goes out, document MODERATE+.
- **Epic tracking:** check `docs/epics/README.md` before starting; flip the epic's status field (`BACKLOG → DEFINED → IN_PROGRESS → REVIEW → DONE ✅`) on start/finish/block.
