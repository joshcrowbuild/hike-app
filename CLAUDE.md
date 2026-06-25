# CLAUDE.md — Adventure Planner

A personal, agentic, self-verifying hiking/backpacking trip planner. A calm, private **utility** — not social, not engagement-seeking. (Working title.)

> Keep this file lean. The full design lives in the two docs below — read the relevant sections when working a stage. Push stage-specific detail into `.claude/rules/*.md` as code grows. **Delete anything stale — wrong memory is worse than none.**

> Read `AGENTS.md` first for repo operating rules, merge-risk discipline, and Git/PR hygiene. Use this file for product invariants, architecture, and development process.

## Canonical design docs (read on demand)
- `docs/decision-log.md` — **state**: everything decided, with a ✅/🔶/❓ legend.
- `docs/workplan.md` — **process**: the dependency-ordered 11-stage agenda + cross-cutting threads.
- `docs/process/plan-analysis.md` — **readiness audit**: what's well-defined vs. underdefined, build order.
- `docs/process/development-process.md` — **how we work**: epics → stories → ACs → tests → code → targeted review.
- `docs/epics/` — **epic definitions** (Epic NNN = stories + ACs). Check here before coding any feature.
- `docs/research/` — **research outputs** per stage.
- **Current position:** Phase-0 complete + Phase-1 design complete + **Phase-1 build started** (Stages 5–6). Built: ingestion pipeline (OSM/NPS/USFS), engine (Scout→Verifier→Curator), live adapters, Neo4j schema v0.2.0 with personal overlay, FIT Episode CLI, **belief update pipeline (Epic 001 DONE)**. **Next in build order:** Epic 002 (Outcome card endpoint) → Epic 003 (context assembly in engine) → Garmin Connect poller → Valhalla drive time. Work dependency order per `docs/process/plan-analysis.md`.

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
- Build / test / eval: `make check` (`ruff format --check` + ruff + mypy + pytest) · `make db-up` / `make schema` · `make eval` (Stage 4+). `pip install -e ".[all]"`; see `Makefile` / README.
- Frontend: web/PWA first (server-side watch pull means minimal loss vs. native); native iOS (SwiftUI) later

## Phasing (see workplan for detail)
Phase 0 spine (Stages 1–4) → Phase 1 personal intelligence + watch (Stages 5–6) → deep eval (Stage 7) → Phase 2 multiplayer (Stage 8) → Phase 3 commons (Stage 9) → Phase 4 native + polish (Stages 10–11).

---

## Development standards (read before writing any code)

### Git hygiene — atomic commits
- **One logical change = one commit.** Never bundle an epic's work, a bug fix, and a refactor in a single commit.
- **Typical atomic split for an epic:** schema additions · new module + core logic · API wiring · tests · epic doc update. Each is its own commit.
- **Commit message format:**
  ```
  <imperative verb> <what, ≤60 chars>

  <WHY this change exists — one or two sentences. What problem does it solve,
  what invariant does it uphold, what spec section does it implement.>

  Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>
  ```
- **Subject line rules:** imperative mood ("Add", "Fix", "Enforce" — not "Added", "Fixes"); ≤72 chars; no period at end.
- **Never commit:** `.env`, `data/`, commented-out code, debug `print()`, unresolved merge markers, half-finished work that breaks tests.
- **`make check` must pass** (`ruff format --check` + ruff + mypy + pytest) before every commit, no exceptions.

### Code standards
- **No commented-out code.** If code is removed, remove it. History is in git.
- **No debug artifacts.** No `print()`, no `logging.WARNING("debug: ...")`, no `# TODO:` or `# FIXME:` in committed code. Use the epic/issue tracker instead.
- **No hardcoded secrets or values** that belong in config. Everything environment-dependent lives in `Settings.from_env()`.
- **Fail loudly at boundaries, degrade gracefully at the surface.** Invalid input to a function → `ValueError`. Live adapter failure → `None` (source-or-silence). Never swallow an exception silently.
- **New modules get tests before they get callers.** Write the test file alongside (or before) the module — never after.

### Review process (see `docs/process/development-process.md` for full detail)
- After each epic: **spawn a targeted review agent** with a narrow file list and specific rules to check. Do NOT run `/code-review ultra` for routine epics — it's expensive, slow, and crashes.
- Reserve `/code-review ultra` for Phase-boundary reviews (e.g., before shipping Phase 0 → Phase 1).
- Every CRITICAL finding from a targeted review must be fixed **before** the commit goes out. MODERATE findings must be fixed or explicitly documented in the epic's DoD.

### Epic / story tracking
- All epics live in `docs/epics/`. Check `docs/epics/README.md` for status before starting work.
- Status flow: `BACKLOG` → `DEFINED` → `IN_PROGRESS` → `REVIEW` → `DONE ✅`
- Change an epic's status field at the top of its file when you start, finish, or block it.
- Stories use `[ ]` / `[x]` checkboxes within the epic doc. Check them off as ACs pass.
- Update `docs/epics/README.md` status column when an epic closes.
