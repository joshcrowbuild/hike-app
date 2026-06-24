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

Use `/code-review ultra` (or create a PR) only for:
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
