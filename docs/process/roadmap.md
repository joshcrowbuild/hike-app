# Roadmap — Adventure Planner

*Living status doc. Owned by the PM/planner lane. Terse by design — delete stale entries, wrong memory is worse than none (CLAUDE.md).*

**Last updated:** 2026-06-26 · **Trunk:** `claude/vigilant-bohr-yzdcyh` @ `86206c5` (PR #1 → `main`, open) · **Version:** v3

> **Overnight build batch is staged** — see `docs/process/overnight-runbook.md` for the sequenced, AC-level brief an unattended session can execute (close 002 · Epic 015 CI-Neo4j · close 003+Episode.date · docs reconciliation).

> Companion to `docs/workplan.md` (the 11-stage agenda + threads T1–T7) and `docs/epics/README.md` (epic index). This doc aggregates *live* state across lanes; the workplan is the plan, the index is the per-epic source of truth, this is the dashboard.

---

## TL;DR — where we are

At the **Phase-0 → Phase-1 boundary.** The Phase-0 spine is built and all **6 gap-audit CRITICALs + the integrated-remediation 1 CRITICAL/4 MODERATE are merged** (PRs #5/#6/#7/#9); test-coverage rebased in (#10); **`workflow-lint` fixed (#12)** and dependabot bumps merged (#3/#4) — trunk in-flight queue is **clear**. Phase-1 epics 001/004/005/010–014 are DONE; **002/003 are built but still formally IN_PROGRESS — staged to close in the overnight batch**. An AC-level readiness audit (2026-06-26) defined the next moves and corrected two stale entries: the Garmin in-process poller is **already built** (Epic 004 subsumed it), and R2 was reframed — there's no silently-skipped guardrail; the real gap is **zero live-Neo4j tests**, now specced as **Epic 015**. **Staged for an overnight session:** close 002 · build Epic 015 (CI-Neo4j) · close 003 + `Episode.date` (R6) · reconcile the 13 design docs (R4). Still needing human design: Epic 007 (readiness, safety-adjacent), Epic 006's `been_on` producer, Epic 008's epic-with-ACs.

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
| 6 Watch integration | 1 | ✅ | 🔶 | Device seam (004) done — **incl. the in-process Garmin poller (`watch_sync`, 55 tests)**; only the **always-on deployment** (R7) + **readiness filter (007, unwritten)** remain |
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
| 002 | Outcome card endpoint | **REVIEW 🔶 — staged (overnight #1)** | Built + write-seam fixed (PR #9); audit found ~5 ACs lack a dedicated test + DoD unchecked. Close = add those tests + verify the all-None preference-marker drain + tick DoD. No product decisions |
| 003 | Context assembly in `engine.plan()` | **REVIEW 🔶 — staged (overnight #3)** | Built; load-bearing gap is **AC-3.2** (`P18M` date filter) returning zero because **`Episode.date` is never written (R6)**. Fix is small — `FITSummary.start_time` is parsed, just not threaded into `upsert_episode`. Close = that fix + AC coverage + seeded-Josh E2E |
| 015 | CI Neo4j integration (live owner-isolation guardrail) | **DEFINED — staged (overnight #2)** | New epic (R2 reframed): separate **required** `integration` job; read+write isolation + falsifiability test against a real Neo4j; `@pytest.mark.neo4j` marker keeps fast legs DB-free |
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

**Merged-to-trunk PRs:** #2 infra-hygiene · #5 Epic 012 · #6 Epics 011+010 · #7 Epics 014+013+005 · #8 roadmap v1 · #9 remediation (1 CRITICAL + 4 MODERATE) · #10 test-coverage · #11 roadmap v2 · **#12 workflow-lint fix** · **#3/#4 dependabot bumps**.

---

## Live in-flight (not yet on trunk)

Backend + infra in-flight queue is **clear** — remediation (#9), test-coverage (#10), `workflow-lint` fix (#12) and dependabot (#3/#4) all merged. Only the UI lane is divergent.

| Lane | Branch / PR | Contents | State |
|---|---|---|---|
| UI/design | `claude/web-design-parallel` | design-system Phase 2, frontend prototype, + 13 docs (incl. Epic 006/009 defs) not on trunk | active; well behind trunk; reconciliation pending (R4) |
| PM | `claude/roadmap` (this PR) | roadmap v3 + Epic 015 + overnight runbook | in review |

---

## Dependency graph & next-up per lane

```
OVERNIGHT BATCH (one unattended session — see overnight-runbook.md)
  1. close Epic 002 (outcome)     ── add missing per-AC tests + DoD; no DB
  2. Epic 015 (CI Neo4j)          ── stands up the live-Neo4j fixture ──┐
  3. close Epic 003 + Episode.date────reuses fixture for the E2E DoD ◄──┘ ──► unblocks ▼
  4. reconcile 13 design docs     ── docs-only, selective cherry-pick (not a merge)
                                                                         │
NEXT WAVE (needs the above + human design)                              ▼
  Epic 006 (novelty)  ◄── needs 003 closed + a been_on PRODUCER (unbuilt; needs design)
  Epic 009 (eval)     ◄── needs 002/003/006 + reconciled stage-7 spec
  Epic 007 (readiness)◄── needs a design session first (safety-adjacent); no epic yet
  Epic 008 (API tests)◄── ready once its epic-with-ACs is written + ratified

UI LANE (web-design-parallel) — parallel
  design-system Phase 2 (token spine → components) against ratified §20 contract
```

**Next-up by lane:**
- **Overnight session:** items 1–4 above (per the runbook).
- **Needs your design first:** Epic 007 (readiness mapping/normalization/party), Epic 006 `been_on` producer, Epic 008 epic-with-ACs.
- **Orchestration:** add the M9 thread-status tracker (folded into item 4's reconciliation).
- **UI:** design-system Phase 2.

---

## ◆ The overnight batch (sequenced; full brief in `overnight-runbook.md`)

All four are audit-verified buildable from trunk **without product decisions**. Ordered so item 2's live-Neo4j fixture is available to item 3's end-to-end DoD.

1. **Close Epic 002 (outcome).** Built + write-seam fixed; add the ~5 missing per-AC tests, verify the all-None preference-marker drain no-ops safely, tick DoD, flip status. *(S — `tests/`, `docs/epics/`)*
2. **Build Epic 015 (CI Neo4j integration).** Separate **required** `integration` job proving owner-isolation (read + write + falsifiability) against a real Neo4j; `@pytest.mark.neo4j` keeps the four fast legs DB-free. *(M — `tests/`, `pyproject.toml`, `ci.yml`, `Makefile`)*
3. **Close Epic 003 + the `Episode.date` fix (R6).** Thread `FITSummary.start_time` → `Episode.date` in `upsert_episode`, prove AC coverage, run the seeded-Josh E2E (reusing item 2's fixture). Unblocks Epic 006 + the memory eval. *(S–M — `graph/`, `ingestion/`, `tests/`)*
4. **Reconcile the 13 design docs → trunk (R4).** Selective path checkout (NOT a branch merge — trunk is ahead), README *union*, add the M9 thread tracker. *(S — `docs/` only)*

**Held back (need a human design pass first):** Epic 007 readiness filter (safety-adjacent mapping/normalization/party composition) · Epic 006 `been_on` producer (unbuilt; semantics undecided) · Epic 008 API tests (needs its epic-with-ACs written/ratified).

---

## Open risks & cross-cutting threads

| ID | Risk / thread | State | Action / owner |
|---|---|---|---|
| **R1** | **T6 licensing/consent gate.** ODbL `separable` flag has zero code readers (gap-audit m2); best-view cache blends sources → Derivative-DB risk; Valhalla adds unattributed OSM. Commons consent substrate (opt-in + salt) landed with Epic 010, but the public-release ODbL handling is unresolved. | **OPEN** — write half accreting now | **Gates Stage 9 public release.** Enforce separability invariant + ODbL posture before any public commons. Track in T6 doc reconciliation (R4). |
| **R2** | **No live-Neo4j test coverage** *(reframed by the 2026-06-26 audit — the earlier "silently-skipped guardrail" was wrong: the scope guard already runs as fake-session unit tests).* The real gap: **zero** tests round-trip a real Neo4j, so the Rule #4 invariant is never proven end-to-end. | **SPECCED** → **Epic 015** | Build Epic 015 (overnight #2): a separate required `integration` job with read+write isolation + falsifiability against a `neo4j:5-community` service. *(infra/test)* |
| **R3** | **C3 auth — interim built, full auth deferred.** Epic 014 S3 added an edge guard (`_authorize_viewer`): any non-anonymous `viewer_id` must present `X-Dev-Viewer-Secret` (constant-time compare) or gets HTTP 403 — fails closed. But at the query layer `ScopedSession` still trusts `viewer_id` verbatim, so a secret-bearing forged id is still a forged write; the dev-secret is a single shared interim credential, not per-user auth. | **PARTIAL** — interim guard built; full auth deferred | Decide managed auth provider (Supabase/Clerk/Auth0 — undecided) at Stage 8; until then the shared dev-secret is the only gate. |
| **R4** | **Trunk ↔ design-branch divergence.** 13 design docs (2 of them Epic 006/009 defs) only on `web-design-parallel`; trunk index references them. Risk of "wrong memory" / building off un-merged specs. | **OPEN** | **Next-item #3.** *(orchestration lane)* |
| **R5** | **Cost spike unmeasured.** Stage-4 local-vs-cloud bake-off designed; real cost-per-session not yet measured against the real corpus. TTL cache lever now built (Epic 013), so the estimate's main assumption holds. | **OPEN** | Run the spike once Phase-1 flow stabilizes (needs a real flow to measure). |
| **R6** | **M1 `Episode.date` never written.** Personalization date filters return zero; invisible until Stage-7 eval shows no memory effect. | **OPEN** | **Folded into next-item #2.** *(backend)* |
| **R7** | **Always-on infra undecided.** The in-process Garmin poller is built (Epic 004); only the **always-on host** (same-day push) + Stage-8 multiplayer need it. | Deferred | Decide host (VPS/Pi/always-on Mac) at Phase-1→2 boundary. |
| ~~**R8**~~ | ~~CI `workflow-lint` red trunk-wide.~~ | **RESOLVED — PR #12** | `actionlint` now runs via its official download script; `workflow-lint` green trunk-wide. |

### Thread tracker (T1–T7 — mirrors workplan; the M9 fix)

- **T1 · Infra/secrets/CI.** 🔶 `.env` plaintext only; `SecretProvider` seam not built (gap-audit M6). `workflow-lint` **fixed (#12)**; FIRMS key log-leak **fixed (#9)**; live-Neo4j CI coverage specced as **Epic 015** (R2). Still open: the secrets-store seam.
- **T2 · Access-control-at-query-layer.** ✅ reads (ScopedSession) + writes (Epic 011 `run_write`) seamed; the Outcome-endpoint bypass is **closed (#9)**. The end-to-end live-DB proof of the invariant lands with **Epic 015** (overnight #2).
- **T3 · Forked commons write.** ✅ built (Epic 010), accreting born-severed observations. Read/aggregation dormant to Stage 9.
- **T4 · Evaluation.** 🔶 truthfulness harness exists; golden-trip set/cassettes unbuilt; Epic 009 (deep eval) defined on design-branch.
- **T5 · UX.** 🔶 design-system Phase 2 starting; Stage-10 deep work on design-branch, not on trunk.
- **T6 · Legal/licensing/consent.** ⚠️ see R1 — gates Stage 9 public release; separability invariant unenforced.
- **T7 · Naming/branding.** Working title "Adventure Planner"; anytime.

---

## Lane discipline (this doc's owner)

PM lane owns `docs/process/roadmap.md` + `docs/workplan.md`; `docs/epics/README.md` is read-mostly. Never touch `api/`, `graph/`, `orchestration/`, `ingestion/`, `frontend/`, or another lane's epic spec. Work in the `hike-app-pm` worktree; small commits; pull before push; PRs into `claude/vigilant-bohr-yzdcyh`.
