# Roadmap — Adventure Planner

*Living status doc. Owned by the PM/planner lane. Terse by design — delete stale entries, wrong memory is worse than none (CLAUDE.md).*

**Last updated:** 2026-06-25 · **Trunk:** `claude/vigilant-bohr-yzdcyh` @ `549e6f3` (PR #1 → `main`, open) · **Version:** v1

> Companion to `docs/workplan.md` (the 11-stage agenda + threads T1–T7) and `docs/epics/README.md` (epic index). This doc aggregates *live* state across lanes; the workplan is the plan, the index is the per-epic source of truth, this is the dashboard.

---

## TL;DR — where we are

At the **Phase-0 → Phase-1 boundary.** The Phase-0 spine is built (ingestion → engine → JIT verify → feed) and the **6 gap-audit CRITICALs (C1–C6) are remediated and merged** to trunk via three track PRs (#5/#6/#7). Phase-1 personal-intelligence epics are partly landed (001/004/005/010/011/012/013/014 done; 002/003 built-but-unclosed). A post-merge **integrated-remediation review found 1 new CRITICAL + 4 MODERATE**; the fix is **in flight** (not yet pushed). The UI lane is starting **design-system Phase 2**. A body of design docs (Stages 7–9, T6, design-system, Epics 006/009) lives only on the design branch and needs **reconciling into trunk**.

---

## 11-stage position

| Stage | Phase | Design | Build | Status |
|---|---|---|---|---|
| 0 Setup | 0 | ✅ | ✅ | Done |
| 1 Data sources | 0 | ✅ | ✅ | Done |
| 2 Schema/graph | 0 | ✅ | ✅ v0.2.0 | Done |
| 3 Corpus pipeline | 0 | ✅ | ✅ | Done — CorpusSource seam landed (Epic 012) |
| 4 Engine + cost | 0 | ✅ | ✅ | Built — **cost spike (real measurement) still pending**; TTL cache now wired (Epic 013) |
| 5 Personalization | 1 | ✅ | 🔶 | Belief pipeline (001), commons fork (010) done; outcome (002) + context-assembly (003) **built, not closed** |
| 6 Watch integration | 1 | ✅ | 🔶 | Device seam (004) done; **Garmin poller (`watch_sync` consumer) + readiness filter (007) unbuilt** |
| 7 Eval deep-dive | 1 | ✅ (design-branch) | ❌ | Methodology designed (not on trunk); Epic 009 defined; harness unbuilt |
| 8 Multiplayer | 2 | ✅ (design-branch) | ❌ | Designed (not on trunk); gated by always-on infra + auth provider |
| 9 Commons | 3 | ✅ (design-branch) | 🔶 | Write half accreting (010 on trunk); read/aggregation dormant; **gated by T6** |
| 10 Experience/design-system | 4 | 🔶 in progress | 🔶 | design-system token spine + Home/Curation prototype v0.3 on design-branch; **Phase 2 starting** |
| 11 Native shell | 4 | ❌ | ❌ | Not started |

---

## Per-epic status (aggregated from index + live PRs/code)

| # | Epic | Status | Evidence / note |
|---|---|---|---|
| 001 | Belief update pipeline | **DONE ✅** | merged |
| 002 | Outcome card endpoint | **REVIEW 🔶** | `orchestration/outcome.py` + `POST /episode/{id}/outcome` on trunk; index still says IN_PROGRESS. **Blocked by remediation CRITICAL #1** (write-seam bypass on this endpoint) — fix in flight |
| 003 | Context assembly in `engine.plan()` | **REVIEW 🔶** | `orchestration/context_assembly.py` on trunk; C3/C4 risks remediated by Epic 014; needs DoD close + **M1 `Episode.date` fix** (else date-filtered retrieval returns zero) |
| 004 | Device-integration seam | **DONE ✅** | merged (supersedes Garmin-only 004) |
| 005 | Valhalla drive-time | **DONE ✅** | absorbed into Epic 013 / PR #7 |
| 006 | Novelty filter in Curator | **DEFINED** (design-branch only) | depends on Epic 003 closed + `been_on` beliefs; spec `novelty-filter-spec.md` not on trunk |
| 007 | Readiness filter (Body Battery → Curator) | **NOT WRITTEN** | gap-audit M11: epic-007 doesn't exist; depends on Epic 004 (done); solo-vs-party composition unspecified |
| 008 | API tests (`/plan` + `/health`) | **BACKLOG** | no deps; parallel fill |
| 009 | Eval harness expansion | **DEFINED** (design-branch only) | needs 002/003/006 to evaluate; epic doc not on trunk |
| 010 | Commons fork write | **DONE ✅** | PR #6 (remediates C1) |
| 011 | Scoped-write seam | **DONE ✅** | PR #6 (remediates C2) |
| 012 | CorpusSource seam | **DONE ✅** | PR #5 (remediates C5) |
| 013 | LiveAdapter seam | **DONE ✅** | PR #7 (remediates C6; +TTL cache, drive-time) |
| 014 | Overlay-egress + viewer-auth hardening (C3 + C4) | **DONE ✅** | PR #7 — C4 egress fix + **C3 interim edge auth** (`_authorize_viewer`: non-anonymous `viewer_id` needs `X-Dev-Viewer-Secret`, fails closed 403); full managed-auth deferred (R3) |

**Merged-to-trunk track PRs:** #2 infra-hygiene · #5 Epic 012 · #6 Epics 011+010 · #7 Epics 014+013+005.

---

## Live in-flight (not yet on trunk)

| Lane | Branch / PR | Contents | State |
|---|---|---|---|
| backend | `claude/integrated-remediation-fixes` | Remediation CRITICAL #1 (route Outcome writes through `run_write` + move Cypher to `graph.queries`) + 4 MODERATEs (#2 Belief merge-key owner pin, #3 `sprint.sh` seam, #4 OSM-hardcode in consolidate, #5 FIRMS key in logs) | **WIP, unpushed** — 8 files spanning all 5 findings (incl. test updates + `deferred_writers` carve-out removal) |
| backend | `claude/test-coverage` (pushed, no PR) | +1 commit "expand unit coverage for orchestration leaf modules" | **diverged** — 1 ahead but **14 behind** (branched at `d8072d5`); rebase before PR or it drops 14 trunk commits |
| UI/design | `claude/web-design-parallel` | design-system Phase 2, frontend prototype, + 13 docs (incl. Epic 006/009 defs) not on trunk | active; reconciliation pending (R4) |
| infra | dependabot PRs #3 (setup-python 5→6), #4 (checkout 4→7) | CI action bumps into trunk | open, mergeable |

---

## Dependency graph & next-up per lane

```
TRUNK STABILIZATION (gates everything downstream)
  [in flight] remediation fix PR  ── CRITICAL #1 + 4 MOD ──┐
  [next]      CI: add Neo4j service container (R2)         ┴─► clean trunk
                                                              │
PHASE-1 CLOSURE (backend lane)                                ▼
  close Epic 002 (outcome)  ◄── after remediation #1
  close Epic 003 (context)  ◄── + M1 Episode.date fix ──► unblocks ▼
       Epic 006 (novelty)   ◄── needs 003 + been_on beliefs
       Epic 009 (eval)      ◄── needs 002/003/006 to score
  Epic 007 (readiness)      ◄── WRITE epic first (M11), then build; needs 004 ✅
  Garmin poller (watch_sync)◄── consumer of device seam (004 ✅); parallel
  Epic 008 (API tests)      ◄── parallel, no deps

DOCS RECONCILIATION (orchestration lane) — parallel, no code conflict
  merge design-branch docs (Stage 7/8/9, T6, design-system, Epics 006/009) → trunk

UI LANE (web-design-parallel) — parallel
  design-system Phase 2 (token spine → components) against ratified §20 contract
```

**Next-up by lane:**
- **Backend:** push + PR the remediation fix → close 002/003 (+ `Episode.date`) → Epic 006 → Epic 007 (write then build) / Garmin poller / 008 (parallel).
- **Orchestration:** reconcile design-branch docs into trunk; add the thread-status tracker (M9) so fallen-behind threads go red.
- **UI:** design-system Phase 2.
- **Infra:** merge dependabot #3/#4; add Neo4j to CI.

---

## ◆ Recommended next 3 work items (dependency order)

1. **Land the integrated-remediation fix + add Neo4j to CI.** The 1 CRITICAL is a structural defense-in-depth gap on a *live* endpoint (`POST /episode/{id}/outcome` writes owned `Outcome`+`Belief` around the scoped-write seam), and CI runs the `test` leg with **no Neo4j**, so DB-backed owner-isolation guardrails pass as no-ops — the bypass is doubly invisible to `make check`. Push the WIP fix branch, open the PR, remove the `deferred_writers` carve-out, and add a `neo4j` service container. **Gates** a clean trunk and all further owned-write work. *(backend + infra; in flight)*

2. **Close Epics 002 + 003 with their DoD — including the M1 `Episode.date` fix.** Both are built but stuck IN_PROGRESS. Closing them requires the remediation fix (#1) plus writing `Episode.date` (currently never set), without which every date-filtered personalization query silently returns zero episodes and the memory layer looks empty after trips are logged. The fix is **small** — the FIT `start_time` is already parsed (`FITSummary.start_time`) and passed to the commons fork; it just isn't threaded into the Episode write (`upsert_episode`). Closing 002/003 **unblocks** Epic 006 (novelty) and the memory-on/off eval. *(backend; after #1)*

3. **Reconcile the design-lane docs into trunk** (Stages 7–9, T6 licensing/consent, design-system v0.1, Epic 006 + 009 definitions — 13 docs total, 2 of them the Epic 006/009 defs, only on `web-design-parallel`). The trunk epic index already references epics/threads it doesn't contain, and the UI lane is building Phase 2 against a §20 design-system contract not on trunk. Reconciling keeps the canonical index honest, adds the M9 thread tracker, and unblocks the Epic 006/009 build wave. **Parallelizable now** — different lane, no code conflict with #1/#2. *(orchestration lane)*

---

## Open risks & cross-cutting threads

| ID | Risk / thread | State | Action / owner |
|---|---|---|---|
| **R1** | **T6 licensing/consent gate.** ODbL `separable` flag has zero code readers (gap-audit m2); best-view cache blends sources → Derivative-DB risk; Valhalla adds unattributed OSM. Commons consent substrate (opt-in + salt) landed with Epic 010, but the public-release ODbL handling is unresolved. | **OPEN** — write half accreting now | **Gates Stage 9 public release.** Enforce separability invariant + ODbL posture before any public commons. Track in T6 doc reconciliation (R4). |
| **R2** | **CI has no Neo4j.** `.github/workflows/ci.yml` `test` leg has no `services:` block → DB-backed guardrail/owner-isolation tests silently skipped. | **OPEN** | Add `neo4j` service to CI matrix. **Folded into next-item #1.** *(infra)* |
| **R3** | **C3 auth — interim built, full auth deferred.** Epic 014 S3 added an edge guard (`_authorize_viewer`): any non-anonymous `viewer_id` must present `X-Dev-Viewer-Secret` (constant-time compare) or gets HTTP 403 — fails closed. But at the query layer `ScopedSession` still trusts `viewer_id` verbatim, so a secret-bearing forged id is still a forged write; the dev-secret is a single shared interim credential, not per-user auth. | **PARTIAL** — interim guard built; full auth deferred | Decide managed auth provider (Supabase/Clerk/Auth0 — undecided) at Stage 8; until then the shared dev-secret is the only gate. |
| **R4** | **Trunk ↔ design-branch divergence.** 13 design docs (2 of them Epic 006/009 defs) only on `web-design-parallel`; trunk index references them. Risk of "wrong memory" / building off un-merged specs. | **OPEN** | **Next-item #3.** *(orchestration lane)* |
| **R5** | **Cost spike unmeasured.** Stage-4 local-vs-cloud bake-off designed; real cost-per-session not yet measured against the real corpus. TTL cache lever now built (Epic 013), so the estimate's main assumption holds. | **OPEN** | Run the spike once Phase-1 flow stabilizes (needs a real flow to measure). |
| **R6** | **M1 `Episode.date` never written.** Personalization date filters return zero; invisible until Stage-7 eval shows no memory effect. | **OPEN** | **Folded into next-item #2.** *(backend)* |
| **R7** | **Always-on infra undecided.** Gates same-day Garmin poller push and Stage-8 multiplayer. | Deferred | Decide host (VPS/Pi/always-on Mac) at Phase-1→2 boundary. |
| **R8** | **CI `workflow-lint` red trunk-wide.** `.github/workflows/ci.yml:23` pins `rhysd/actionlint@v1`, but that action has no moving `v1` tag (only `v1.7.x`) → job fails at *setup* on every PR (#8, #3, #4 all red); the other legs (format/lint/test/typecheck) pass. Pre-existing, not introduced by any open PR. | **OPEN** | One-line infra-lane fix: pin `@v1.7.12` (or a commit SHA). Not PM-lane code — flagged for infra. |

### Thread tracker (T1–T7 — mirrors workplan; the M9 fix)

- **T1 · Infra/secrets/CI.** 🔶 `.env` plaintext only; `SecretProvider` seam not built (gap-audit M6, doc-vs-artifact contradiction). CI exists but no Neo4j (R2) and `workflow-lint` is red trunk-wide (R8). FIRMS key log-leak fix in flight.
- **T2 · Access-control-at-query-layer.** ✅ reads (ScopedSession) + writes (Epic 011 `run_write`) seamed — **except** the live Outcome endpoint bypasses it (remediation CRITICAL #1, fix in flight).
- **T3 · Forked commons write.** ✅ built (Epic 010), accreting born-severed observations. Read/aggregation dormant to Stage 9.
- **T4 · Evaluation.** 🔶 truthfulness harness exists; golden-trip set/cassettes unbuilt; Epic 009 (deep eval) defined on design-branch.
- **T5 · UX.** 🔶 design-system Phase 2 starting; Stage-10 deep work on design-branch, not on trunk.
- **T6 · Legal/licensing/consent.** ⚠️ see R1 — gates Stage 9 public release; separability invariant unenforced.
- **T7 · Naming/branding.** Working title "Adventure Planner"; anytime.

---

## Lane discipline (this doc's owner)

PM lane owns `docs/process/roadmap.md` + `docs/workplan.md`; `docs/epics/README.md` is read-mostly. Never touch `api/`, `graph/`, `orchestration/`, `ingestion/`, `frontend/`, or another lane's epic spec. Work in the `hike-app-pm` worktree; small commits; pull before push; PRs into `claude/vigilant-bohr-yzdcyh`.
