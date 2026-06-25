# Epics Index

Status legend: `BACKLOG` · `DEFINED` · `IN_PROGRESS` · `REVIEW` · `DONE ✅` · `BLOCKED 🚫`

| # | Epic | Status | Phase | Depends on |
|---|---|---|---|---|
| [001](epic-001-belief-update-pipeline.md) | Belief update pipeline (EWMA pace, maxima, N=3 promotion) | DONE ✅ | 1 | Stage 5 schema |
| [002](epic-002-outcome-card-endpoint.md) | Outcome card endpoint (POST /episode/{id}/outcome) | IN_PROGRESS | 1 | Epic 001 |
| [003](epic-003-context-assembly.md) | Context assembly in engine.plan() | IN_PROGRESS | 1 | Epic 001 |
| [004](epic-004-device-integration-seam.md) | Device-integration seam (Garmin + Coros, pluggable) | DONE ✅ | 1 | Epic 001 |
| [005](epic-005-valhalla-drive-time.md) | Valhalla drive-time integration (post-Scout prune + ranking input) | DONE ✅ | 0 | — (via Epic 013) |
| 006 | Novelty filter in Curator | BACKLOG | 1 | Epic 003 |
| 007 | Readiness filter (Body Battery → Curator parameter) | BACKLOG | 1 | Epic 004 |
| 008 | API tests (FastAPI TestClient, /plan + /health) | BACKLOG | 0 | — |
| [013](epic-013-live-adapter-seam.md) | LiveAdapter seam (kind-keyed registry, failover, Valhalla drive-time, TTL) | DONE ✅ | 1 | Epic 003 |
| [014](epic-014-overlay-egress-and-viewer-auth.md) | Private-overlay egress + viewer-auth hardening (C3 + C4) | DONE ✅ | 1 | Epic 003 |

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
