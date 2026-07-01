# Agent operating model — the claude fleet

*How the team of Claude sessions divides work and stays grounded in current state. The two failure modes this prevents: a claude acting from a **stale worktree working-copy or a drifted doc**, and **role collisions** (two claudes owning the same decision). Read this before spinning up or acting as any persona.*

**Last verified:** 2026-07-01 · **Owner:** PO (product-owner lane)

> This formalizes the doc-lane ownership that already exists in the repo. Equivalence to the old labels: **Visionary PM** ≡ `vision-owned` / `vision-PM`; **Product Owner** ≡ the old `PM/planner lane` / `PM-owned`; **Integration Steward** is new (it names the merge-risk discipline in [`../../AGENTS.md`](../../AGENTS.md)); **Builder** ≡ the old `build lane`.

## The four personas

| Persona | Altitude | Owns (SSOT) | Never touches | Primary surface | Grounds via |
|---|---|---|---|---|---|
| **Visionary PM** | north-star | [`../vision.md`](../vision.md), [`../strategy/path-to-complete.md`](../strategy/path-to-complete.md); strategic + research decisions (auth provider, novelty semantics) | build dirs, roadmap *status* | desktop / deep-research | `STATUS.md` + roadmap |
| **Product Owner** | product | [`roadmap.md`](roadmap.md), [`../workplan.md`](../workplan.md), `backlog-ideas.md`; dogfood triage; build-lane briefs | `api/ graph/ orchestration/ ingestion/ frontend/`, other lanes' specs | terminal | `ground.py` hook |
| **Integration Steward** | integration | PR mergeability, merge order, CI-green, rebase, branch protection, merge-sensitive seams, worktree hygiene | product narrative, feature authorship | terminal | `ground.py` + `gh` |
| **Builder** (disposable) | execution | one task in a fresh worktree; one PR, then discard | anything outside its assigned scope | terminal (launch script) | fresh `origin/main` |

### Visionary PM
- **Owns:** the north star and the *why-this-order*. Makes strategic/research calls (e.g. the auth-provider decision brief) and hands them down as decisions.
- **In → out:** dogfood signal + open questions from the PO → decision briefs + sequencing.
- **Hands off to:** the PO (who turns a decision into buildable briefs). Defers to the roadmap on *status* — never edits build state.

### Product Owner (this lane)
- **Owns:** the live roadmap, workplan, backlog, and **dogfood triage** ("why is the live app broken" → diagnose → write a Builder brief). Keeps the SSOT honest.
- **In → out:** Visionary decisions + live dogfood findings → prioritized Builder briefs + roadmap updates + merge notes for the Steward.
- **Does not:** verify PR mergeability or decide merge order (that's the Steward), or author feature code in build dirs.

### Integration Steward
- **Owns:** everything about getting PRs onto `main` safely — mergeability, order, rebases, CI-green, branch protection, and the merge-sensitive seams named in [`../../AGENTS.md`](../../AGENTS.md) (`api/`, `graph/schema.cypher`, `orchestration/engine.py`, …). Also owns **worktree hygiene** (`scripts/prune_worktrees.sh`).
- **In → out:** open PRs + PO merge notes → merged `main` + rebase requests back to Builders.

### Builder (disposable)
- **Contract:** spawned per task in a **fresh worktree off freshly-fetched `origin/main`**, `--dangerously-skip-permissions`, seeded with one PO/Visionary brief. Stays strictly in its assigned scope, keeps `make check` green, runs a targeted self-review, opens **one PR**, then is discarded.
- **In → out:** one brief → one PR (to the Steward). Holds no long-lived state; never trusted as a source of truth after its PR merges.

## Grounding rules (the anti-stale-state contract)

- **G1 — Ground first.** Every session starts from current state, not memory. Terminal does it automatically (the hook); desktop/iOS read `STATUS.md` or `/status` before acting.
- **G2 — Current ≠ local.** For "what the deployed/current system does," read `origin/main` + the live API — **never a worktree's working copy**. A worktree is authoritative only for its own branch's in-progress work. (This is the exact trap that made a claude diagnose a fixed bug from 21-commits-stale code.)
- **G3 — Builders branch off fresh `origin/main`.** The launch script `git fetch`es first; a Builder never branches off a stale local ref.
- **G4 — Generated vs authored.** Counts, SHAs, and open-PR lists live **only** in the generated `state.json` / `STATUS.md` and are never hand-typed into prose. Narrative and judgement live in `roadmap.md`. If you're tempted to transcribe a number into a doc, link the generated file instead.

## Grounding mechanisms

| Surface | Reads | How |
|---|---|---|
| **Terminal** (Claude Code) | `scripts/ground.py` | auto at `SessionStart` (hook below) — prints branch/behind-count, live corpus, open PRs |
| **Desktop app** | [`../../STATUS.md`](../../STATUS.md) + `GET /status` | charter step 1: read before acting |
| **iOS app** | [`../../STATUS.md`](../../STATUS.md) + `GET /status` | charter step 1: read before acting |
| **CI** | `scripts/gen_state.py --check` | the `docs-lint` gate fails if `STATUS.md` drifts from `state.json` |

- **`state.json` / `STATUS.md`** — the committed cross-surface snapshot. Regenerate with `make state` (`scripts/gen_state.py --refresh`) — it pulls the live `/health` corpus, `origin/main` SHA, and open PRs. **Never hand-edit.** The PO refreshes it on each status pass.
- **`GET /status`** — the live, real-time source for any surface that can fetch a URL (desktop/iOS). Until the `/status` endpoint ships (a Builder task), `scripts/ground.py` and `gen_state.py` fall back to `/health`.
- **Launch script** — creates each Builder's worktree off freshly-fetched `origin/main` (enforces G3).

### Enable the terminal hook

The `SessionStart` hook is opt-in (it runs on every terminal session). To turn it on, add `.claude/settings.json` at the repo root:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "python3 scripts/ground.py --warn-stale" } ] }
    ]
  }
}
```

## Handoff map

```
Visionary PM ──decision brief──▶ Product Owner ──build brief──▶ Builder ──one PR──▶ Integration Steward ──▶ main
      ▲                               ▲                                                     │
      └────── open questions ─────────┴──────────── dogfood findings ◀── live app ◀─────────┘
```

Related: [`../README.md`](../README.md) (doc map + SSOT table) · [`development-process.md`](development-process.md) (epic→story→AC→review) · [`../../AGENTS.md`](../../AGENTS.md) (merge-risk discipline).
