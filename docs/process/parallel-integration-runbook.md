# Parallel Integration Runbook — gap-audit remediation tracks

*Created 2026-06-25. How to merge the three parallel remediation tracks back into the build branch safely. The risky part of this work is the integration, not the builds — this is the mechanical sequence so nothing composes wrong.*

## The tracks (all branched from `origin/claude/vigilant-bohr-yzdcyh`, post-Epic-004)

| Track | Branch | Epics (build order is load-bearing) | Remediates |
|---|---|---|---|
| A | `claude/track-a-write-path` | **011 → 010** | C2 (scoped writes), C1 (commons fork) |
| B | `claude/track-b-corpus` | **012** | C5 (corpus source seam) |
| C | `claude/track-c-live-engine` | **014 → 013** (absorbs 005) | C3/C4 (overlay egress + auth), C6 (live seam) |

## Pre-merge: verify the within-track ordering held

Each pair shares one function and only composes in one order. Confirm from each branch's history before trusting it:
- **Track A:** Epic 011's scoped-write commits must precede Epic 010's commons-fork commits. 010 wraps `create_episode()` in one transaction *on top of* 011's write-builders. If 010 landed first, the fork won't route through the seam.
- **Track C:** Epic 014's `touches_private_overlay` commit must precede Epic 013's `build_runtime` rewrite. If 013 landed first, it silently re-opens the C4 egress hole 014 closed.

## Merge order: **B → A → C**

Smallest/most-isolated first; largest surface last (rebases the residual textual hunks).

1. **Merge B (`track-b-corpus`) → `vigilant-bohr`.** Zero cross-track source overlap (new `ingestion/sources/` package + `run_pipeline` only). Lowest risk; de-risks the train.
2. **Merge A (`track-a-write-path`) → `vigilant-bohr`.** Foundational owned-write seam. **GUARDRAIL before merging:** re-run Epic 010's non-vacuity privacy-suite test — confirm the commons fork still *fires* after 011's seam routing (it must not have become a no-op).
3. **Merge C (`track-c-live-engine`) → `vigilant-bohr`.** Largest surface. **GUARDRAIL before merging:** re-run Epic 014's overlay-egress regression test — it is the canary that 013's `build_runtime` rewrite preserved `touches_private_overlay=True`. If it fails, 013 re-introduced C4 — fix before merging.

## Expected conflicts — all mild/textual, none semantic

- **`orchestration/config.py`** — B adds `corpus_sources`/`ADVENTURE_CORPUS_SOURCES`; C adds `ADVENTURE_LIVE_ADAPTERS` + Valhalla fields + `ADVENTURE_DEV_VIEWER_SECRET`. Different fields, adjacent lines in the same dataclass + `from_env`. Accept both; keep alphabetical/grouped.
- **`docs/epics/README.md`** — every track flips/append its own status row. Distinct rows → take all changes.
- **`graph/schema.cypher`** — Track A only (010's `:CommonsObservation` constraint). No cross-track collision.

## Post-integration verification (on merged `vigilant-bohr`)

- `make check` green end-to-end (ruff + mypy + pytest) across all tracks combined.
- Re-run the three CRITICAL regression guards together: commons structural-severance (no `:Person` path from `:CommonsObservation`), overlay-egress (no private context reaches a cloud provider), scoped-write fuzz (no writer crosses owner boundaries).
- Confirm the doc-lint guard (Epic 010 S1) is green: no `✅` on the commons-fork lines in committed `decision-log.md` §30/§31 or `stage-6` S6-10.

## Final docs reconciliation: `web-design-parallel → vigilant-bohr`

The audit, source-seams spec, decision-log §40 corrections, and Epics 006/009 live only on `web-design-parallel` (the design branch). After the three tracks land, merge the design branch into `vigilant-bohr` to unify docs + code. The branches diverged at `59fb715`; the **only real conflict is `README.md`** (design branch has rows 006–014; build branch has the 002/003/004 closures + the 004→device-seam link fix). Resolve by keeping the union: the build branch's closed-epic statuses + the design branch's new rows, with row 004 pointing at `epic-004-device-integration-seam.md` (not the stale garmin-poller filename) and row 005 marked SUPERSEDED (folded into 013).
