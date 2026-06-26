# Docs Map — Adventure Planner

*Start here. This is the router for everything under `docs/` — which doc answers which question, what's always loaded vs. read-on-demand, and the single source of truth (SSOT) for each kind of fact.*

**Last verified:** 2026-06-26 · **Owner:** docs

> Project root: [`../CLAUDE.md`](../CLAUDE.md) (product invariants + architecture) · [`../AGENTS.md`](../AGENTS.md) (repo operating contract).

## Read this → for that

| If you're trying to… | Read |
|---|---|
| Check current build status / what's next / open risks | [`process/roadmap.md`](process/roadmap.md) — the live status **SSOT** |
| Add, work, or close a feature | [`epics/README.md`](epics/README.md) → then the specific `epics/epic-NNN-*.md` |
| Understand or change a design decision | [`decision-log.md`](decision-log.md) (✅/🔶/❓ legend) |
| See the dependency-ordered plan / cross-cutting threads | [`workplan.md`](workplan.md) |
| Touch the graph schema / provenance / access control | `../graph/` (schema + access wrapper) + [`decision-log.md`](decision-log.md) §28 + [`research/stage-2-schema.md`](research/stage-2-schema.md) |
| Know how to commit / review / run CI | [`process/development-process.md`](process/development-process.md) + [`process/github-repo-hygiene.md`](process/github-repo-hygiene.md) |
| Understand a stage's design (sources, engine, watch, commons…) | [`research/README.md`](research/README.md) → the stage's doc |
| Build/refactor frontend UI | [`research/design-system-v0.1.md`](research/design-system-v0.1.md) + [`research/home-curation-prototype-spec-v0.3.md`](research/home-curation-prototype-spec-v0.3.md) |

## Always-load vs. load-on-demand

**Always in context (keep lean):**
- [`../CLAUDE.md`](../CLAUDE.md) — product invariants, the 10 non-negotiable rules, architecture, stack.
- [`../AGENTS.md`](../AGENTS.md) — session startup, merge-risk discipline, Git/PR hygiene.

**Load on demand (read only what the task needs):**
- [`process/roadmap.md`](process/roadmap.md) — live status dashboard (check at session start).
- [`epics/README.md`](epics/README.md) + the relevant `epics/epic-NNN-*.md` — before coding a feature.
- [`decision-log.md`](decision-log.md) — when a decision is in question.
- [`workplan.md`](workplan.md) — for stage order / threads.
- [`research/README.md`](research/README.md) → a stage/seam/UX doc — for design detail.
- [`process/development-process.md`](process/development-process.md) — epic→story→AC→test→review workflow.

## Single sources of truth (don't restate — link)

| Fact | SSOT |
|---|---|
| Live build status, next work, open risks | [`process/roadmap.md`](process/roadmap.md) (PM-owned) |
| Per-epic status (BACKLOG→DONE) | [`epics/README.md`](epics/README.md) |
| Decisions (what & why) | [`decision-log.md`](decision-log.md) |
| The dependency-ordered plan + threads T1–T7 | [`workplan.md`](workplan.md) (PM-owned) |
| Product invariants + architecture | [`../CLAUDE.md`](../CLAUDE.md) |
| Repo/Git/PR hygiene + review workflow | [`../AGENTS.md`](../AGENTS.md) + [`process/development-process.md`](process/development-process.md) |
| Research/design doc map | [`research/README.md`](research/README.md) |

> Anything not listed here is design provenance under [`research/`](research/) (and closed audits under `research/archive/`).
