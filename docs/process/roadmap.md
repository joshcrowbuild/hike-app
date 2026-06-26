# Roadmap — Adventure Planner

*Living status doc. Owned by the PM/planner lane. Terse by design — delete stale entries, wrong memory is worse than none (CLAUDE.md).*

**Last updated:** 2026-06-26 · **Trunk:** `claude/vigilant-bohr-yzdcyh` @ `7039efb` (PR #1 → `main`, open) · **Version:** v2

> Companion to `docs/workplan.md` (the 11-stage agenda + threads T1–T7) and `docs/epics/README.md` (epic index). This doc aggregates *live* state across lanes; the workplan is the plan, the index is the per-epic source of truth, this is the dashboard.

---

## TL;DR — where we are

At the **Phase-0 → Phase-1 boundary.** The Phase-0 spine is built (ingestion → engine → JIT verify → feed) and the **6 gap-audit CRITICALs (C1–C6) are remediated and merged** (PRs #5/#6/#7). The post-merge **integrated-remediation review's 1 CRITICAL + 4 MODERATE are now also fixed and merged (PR #9)**, and the rebased test-coverage work landed (PR #10) — so the trunk in-flight queue is **clear**. Phase-1 personal-intelligence epics are partly landed (001/004/005/010/011/012/013/014 done; 002/003 built, blocker now cleared, **still formally IN_PROGRESS — ready to close**). The UI lane is on **design-system Phase 2**. **Now actionable:** harden CI (no Neo4j yet — R2; `workflow-lint` red — R8), close 002/003 (+ the `Episode.date` fix — R6), and reconcile the design-branch docs (Stages 7–9, T6, design-system, Epics 006/009 — R4).

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
| 002 | Outcome card endpoint | **REVIEW 🔶 — ready to close** | `orchestration/outcome.py` + `POST /episode/{id}/outcome` on trunk; remediation CRITICAL #1 (write-seam bypass) **RESOLVED — PR #9** (`24efd39` routes Outcome writes through the scoped-write seam). Index/doc still say IN_PROGRESS → just needs DoD checkoff |
| 003 | Context assembly in `engine.plan()` | **REVIEW 🔶** | `orchestration/context_assembly.py` on trunk; C3/C4 risks remediated by Epic 014; needs DoD close + **M1 `Episode.date` fix** (R6 — still unwritten; else date-filtered retrieval returns zero) |
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

**Merged-to-trunk PRs:** #2 infra-hygiene · #5 Epic 012 · #6 Epics 011+010 · #7 Epics 014+013+005 · **#8 roadmap** · **#9 remediation (1 CRITICAL + 4 MODERATE)** · **#10 test-coverage (rebased)**.

---

## Live in-flight (not yet on trunk)

Backend in-flight queue is **clear** — the remediation fix (PR #9) and test-coverage (PR #10) both merged; their branches are deleted.

| Lane | Branch / PR | Contents | State |
|---|---|---|---|
| UI/design | `claude/web-design-parallel` | design-system Phase 2, frontend prototype, + 13 docs (incl. Epic 006/009 defs) not on trunk | active; **27 ahead / 60 behind** trunk; reconciliation pending (R4) |
| infra | dependabot PRs #3 (setup-python 5→6), #4 (checkout 4→7) | CI action bumps into trunk | open, mergeable |

---

## Dependency graph & next-up per lane

```
CI HARDENING (infra) — makes the just-merged seams actually enforced
  add Neo4j service to CI (R2) ─┐   the PR#9 write-seam test can't run without it
  fix workflow-lint pin (R8) ───┴─► green, trustworthy merge gate

PHASE-1 CLOSURE (backend lane) — blocker cleared by PR #9
  close Epic 002 (outcome)  ◄── remediation #1 RESOLVED; just needs DoD checkoff
  close Epic 003 (context)  ◄── + M1 Episode.date fix (R6) ──► unblocks ▼
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
- **Backend:** close 002/003 (+ `Episode.date`) → Epic 006 → Epic 007 (write then build) / Garmin poller / 008 (parallel).
- **Infra:** add Neo4j to CI (R2) + fix `workflow-lint` pin (R8); merge dependabot #3/#4.
- **Orchestration:** reconcile design-branch docs into trunk; add the thread-status tracker (M9) so fallen-behind threads go red.
- **UI:** design-system Phase 2.

---

## ◆ Recommended next 3 work items (dependency order)

1. **Harden CI: add a Neo4j service (R2) + fix the `workflow-lint` pin (R8).** PR #9 just landed the scoped-write seam on the Outcome endpoint and removed the `deferred_writers` carve-out — but the `test` leg runs with **no Neo4j**, so the DB-backed owner-isolation guardrail that's supposed to enforce it still passes as a no-op. The just-merged defense-in-depth isn't actually enforced until CI can run it. Co-located cheap win: `workflow-lint` is red on every PR (`ci.yml:23` pins `rhysd/actionlint@v1`, an unresolvable tag → pin `@v1.7.12`). *(infra)*

2. **Close Epics 002 + 003 with their DoD — including the M1 `Episode.date` fix.** Both are built and the remediation CRITICAL blocker is now cleared (PR #9), but they're still formally IN_PROGRESS. Closing 003 needs `Episode.date` written (currently never set), without which every date-filtered personalization query silently returns zero episodes and the memory layer looks empty after trips are logged. The fix is **small** — the FIT `start_time` is already parsed (`FITSummary.start_time`) and passed to the commons fork; it just isn't threaded into the Episode write (`upsert_episode`). Closing 002/003 **unblocks** Epic 006 (novelty) and the memory-on/off eval. *(backend)*

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
| **R8** | **CI `workflow-lint` red trunk-wide.** `.github/workflows/ci.yml:23` pins `rhysd/actionlint@v1`, but that action has no moving `v1` tag (only `v1.7.x`) → job fails at *setup* on every PR (#3, #4 still red); the other legs (format/lint/test/typecheck) pass. Survived the #9/#10 merges untouched. | **OPEN** | One-line infra-lane fix: pin `@v1.7.12` (or a commit SHA). **Folded into next-item #1.** Not PM-lane code. |

### Thread tracker (T1–T7 — mirrors workplan; the M9 fix)

- **T1 · Infra/secrets/CI.** 🔶 `.env` plaintext only; `SecretProvider` seam not built (gap-audit M6, doc-vs-artifact contradiction). CI exists but no Neo4j (R2) and `workflow-lint` is red trunk-wide (R8). FIRMS key log-leak **fixed (PR #9)**.
- **T2 · Access-control-at-query-layer.** ✅ reads (ScopedSession) + writes (Epic 011 `run_write`) seamed; the Outcome-endpoint bypass is **closed (PR #9** routed it through the write seam) — but the guardrail isn't executed in CI until Neo4j lands (R2).
- **T3 · Forked commons write.** ✅ built (Epic 010), accreting born-severed observations. Read/aggregation dormant to Stage 9.
- **T4 · Evaluation.** 🔶 truthfulness harness exists; golden-trip set/cassettes unbuilt; Epic 009 (deep eval) defined on design-branch.
- **T5 · UX.** 🔶 design-system Phase 2 starting; Stage-10 deep work on design-branch, not on trunk.
- **T6 · Legal/licensing/consent.** ⚠️ see R1 — gates Stage 9 public release; separability invariant unenforced.
- **T7 · Naming/branding.** Working title "Adventure Planner"; anytime.

---

## Lane discipline (this doc's owner)

PM lane owns `docs/process/roadmap.md` + `docs/workplan.md`; `docs/epics/README.md` is read-mostly. Never touch `api/`, `graph/`, `orchestration/`, `ingestion/`, `frontend/`, or another lane's epic spec. Work in the `hike-app-pm` worktree; small commits; pull before push; PRs into `claude/vigilant-bohr-yzdcyh`.
