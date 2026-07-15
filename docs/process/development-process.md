# Development Process

*How we write and verify work on Adventure Planner.*

---

## The three-layer structure

### Epic
A meaningful capability deliverable — something a user or the system can do after this work that it couldn't before. Epics live in `docs/epics/epic-NNN-name.md`.

**Contains:**
- One-sentence capability statement
- Architectural context (what it builds on, what builds on it)
- Stories (3–8)
- Definition of Done

### Story
A single behavioral requirement. Format: **Given** [context] **When** [action] **Then** [outcome]. Each story has 1–4 acceptance criteria.

### Acceptance Criterion (AC)
A concrete, testable, pass/fail statement. Every AC gets at least one unit test before code is written. ACs are numbered (AC-1, AC-2…) and referenced in test names.

---

## Workflow per epic

```
1. Define epic (stories + ACs) → review with user
2. Write tests for every AC (they fail — that's correct)
3. Write the minimum code to pass all tests
4. Run targeted self-review agent (see below)
5. Fix any CRITICAL findings, document MODERATE+
6. `make check` green → commit → push
7. Close epic in the doc
```

### The review cycle (replaces ultrareview for routine work)

After coding an epic, spawn a **targeted self-review agent** with a narrow prompt:
- Only the files changed in this epic
- Specific rules to check (e.g., "verify source-or-silence holds", "check owner_id on all new nodes")
- Maximum 5-minute agent, not a 10-minute cloud review
- A literal-grep microcopy pass never sees a COMPUTED string (an age stamp, a
  pluralized count, a hedge phrase assembled at render time) — checking those
  needs a rendered-DOM pass over the generator inventory instead
  (`generated-string-integrity-sweep-2026-07.md` §5)

Reserve `/code-review ultra` — it is expensive, slow, and prone to crashing — for:
- Major architectural changes spanning many files
- Before a Phase boundary (e.g., before shipping Phase 0 → Phase 1)
- When the targeted review finds a CRITICAL it can't resolve alone

**The goal:** catch issues in the same session they're introduced, not after 20 commits.

---

## Test standards

- **One test per AC minimum.** Name tests `test_<story_id>_<ac_id>_<what>`.
- **Tests are written before code** (failing first — TDD rhythm).
- **Network-free** by default. Injectable clients and sessions.
- **No fabricated assertions.** If you can't write a clear failing test for an AC, the AC is too vague — refine it.

---

## Epic status

| Status | Meaning |
|---|---|
| `DEFINED` | Stories + ACs written, not yet coded |
| `IN_PROGRESS` | Code being written |
| `REVIEW` | Code done, targeted review running |
| `DONE` | All ACs pass, committed, pushed |
| `BLOCKED` | Waiting on dependency |

---

## Naming

Epics: `epic-NNN-kebab-case-name.md` (NNN = 001, 002…)  
Stories: `S{epic-number}.{story-number}` (e.g., S1.2)  
ACs: `AC-{story}.{criterion}` (e.g., AC-1.2)  
Test names: `test_s{story}_{ac}_{description}` (e.g., `test_s2_ac1_ewma_first_episode`)

---

## Git & commit hygiene

*Canonical home for commit/PR discipline — `CLAUDE.md` and `AGENTS.md` point here.*

- **One logical change = one commit.** Never bundle an epic's work, a bug fix, and a refactor in one commit.
- **Typical atomic split for an epic:** schema additions · new module + core logic · API wiring · tests · epic doc update — each its own commit.
- **Commit message format:**
  ```
  <imperative verb> <what, ≤60 chars>

  <WHY this change exists — one or two sentences: what problem it solves,
  what invariant it upholds, what spec section it implements.>

  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```
- **Subject line:** imperative mood ("Add", "Fix", "Enforce" — not "Added", "Fixes"); ≤72 chars; no trailing period.
- **Never commit:** `.env`, `data/`, commented-out code, debug `print()`, unresolved merge markers, half-finished work that breaks tests.
- **`make check` must pass** (`ruff format --check` + ruff + mypy + pytest) before every commit, no exceptions.
- **PRs:** one logical change; small/reviewable/reversible; use `.github/PULL_REQUEST_TEMPLATE.md`; link the epic/story/AC/design doc; call out any merge-sensitive seam touched; never merge with failing CI or unresolved review comments. Branch from `main`; PR into `main` (see `github-repo-hygiene.md`).

## Code standards

- **No commented-out code.** If code is removed, remove it — history is in git.
- **No debug artifacts.** No stray `print()`, no debug logging, no `# TODO:` / `# FIXME:` in committed code — use the epic/issue tracker.
- **No hardcoded secrets or config values.** Everything environment-dependent lives in `Settings.from_env()`; secrets in the store, never the repo (Rule #10).
- **Fail loudly at boundaries, degrade gracefully at the surface.** Invalid input → `ValueError`; live-adapter failure → `None` (source-or-silence); never swallow an exception silently.
- **New modules get tests before callers.** Write the test file alongside (or before) the module — never after.

## Epic & story tracking

- All epics live in `docs/epics/`; check `docs/epics/README.md` for status before starting work.
- Flip the epic's `**Status:**` field (`BACKLOG → DEFINED → IN_PROGRESS → REVIEW → DONE ✅`) at the top of its file when you start, finish, or block it.
- Stories use `[ ]` / `[x]` checkboxes within the epic doc — check them off as each AC passes.
- Update the `docs/epics/README.md` status column when an epic closes (kept in sync by `scripts/gen_epic_index.py`).
