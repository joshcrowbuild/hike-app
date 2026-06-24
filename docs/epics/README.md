# Epics Index

Status legend: `BACKLOG` · `DEFINED` · `IN_PROGRESS` · `REVIEW` · `DONE ✅` · `BLOCKED 🚫`

| # | Epic | Status | Phase | Depends on |
|---|---|---|---|---|
| [001](epic-001-belief-update-pipeline.md) | Belief update pipeline (EWMA pace, maxima, N=3 promotion) | DONE ✅ | 1 | Stage 5 schema |
| [002](epic-002-outcome-card-endpoint.md) | Outcome card endpoint (POST /episode/{id}/outcome) | DEFINED | 1 | Epic 001 |
| [003](epic-003-context-assembly.md) | Context assembly in engine.plan() | DEFINED | 1 | Epic 001 |
| [004](epic-004-garmin-connect-poller.md) | Garmin Connect activity poller (watch_sync.py) | BACKLOG | 1 | Epic 001 |
| [005](epic-005-valhalla-drive-time.md) | Valhalla drive-time pre-Scout filter | BACKLOG | 1 | — |
| [006](epic-006-novelty-filter.md) | Novelty filter in Curator | DEFINED | 1 | Epic 003 |
| 007 | Readiness filter (Body Battery → Curator parameter) | BACKLOG | 1 | Epic 004 |
| 008 | API tests (FastAPI TestClient, /plan + /health) | BACKLOG | 0 | — |
| [009](epic-009-eval-harness-expansion.md) | Stage-7 eval-harness expansion (fixtures, golden trips, judge, N-run regression, security/privacy) | DEFINED | 1→2 | Stage 7 methodology |
| [010](epic-010-commons-fork-write.md) | Commons fork write (de-identified `:CommonsObservation` in the episode txn) — remediates gap-audit C1 | DEFINED | 1 | Epic 001 |
| [011](epic-011-scoped-write-seam.md) | Scoped-write seam (extend the access choke point to owned-node writes) — remediates gap-audit C2 | DEFINED | 1 | Epic 001 |

---

## How to use this index

1. Pick the next `DEFINED` epic at the top of the dependency chain.
2. Change its status to `IN_PROGRESS` and add your name/date.
3. Work through stories in order; check off ACs as you verify each one.
4. When all ACs pass + targeted review is clean → `REVIEW`.
5. After review findings fixed → `DONE ✅`, push, update this table.

## Adding a new epic

1. Create `docs/epics/epic-NNN-name.md` from the template below.
2. Add a row here with status `BACKLOG`.
3. When you sit down to define it fully (stories + ACs), change to `DEFINED`.

## Epic template

```markdown
# Epic NNN — Name

**Status:** DEFINED
**Phase:** N
**Spec refs:** Stage N §X · decision-log §N

---

## Capability statement
One sentence: what the system/user can do after this that they couldn't before.

## Architectural context
Builds on: ...
Enables: ...
Does NOT include: ...

---

## Stories

### S1 — Story name

**Given** [context]
**When** [action]
**Then** [outcome]

**AC-1.1:** ...
**AC-1.2:** ...

[repeat for S2, S3…]

---

## Definition of Done
- [ ] All ACs covered by at least one passing test
- [ ] `make check` green
- [ ] Targeted review agent run; CRITICALs fixed
- [ ] Committed and pushed
```
