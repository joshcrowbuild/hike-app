# Roadmap — Adventure Planner

*Living status doc. Owned by the PM/planner lane. Terse by design — delete stale entries, wrong memory is worse than none (CLAUDE.md).*

**Last updated:** 2026-06-26 · **Trunk:** `claude/vigilant-bohr-yzdcyh` @ `c7052c9` (PR #1 → `main`, open) · **Version:** v4

> **Overnight batch LANDED & verified.** All four items merged (#18 close 002 · #19 Epic 015 CI-Neo4j · #20 close 003+Episode.date · #21 docs reconcile). An adversarial 6-reviewer pass (2026-06-26) confirmed the DoDs are **genuinely met, not status-flipped**: 516 tests pass / 8 neo4j-deselected, ruff+mypy clean, all 6 CI jobs green incl. the **live, required `integration (neo4j)` job** (8 tests vs a real DB on trunk). No merge-skew. **Open flag:** PR #22 (UI) targets `main` not trunk — build agent owns the retarget (R9).

> Companion to `docs/workplan.md` (the 11-stage agenda + threads T1–T7) and `docs/epics/README.md` (epic index). This doc aggregates *live* state across lanes; the workplan is the plan, the index is the per-epic source of truth, this is the dashboard.

---

## TL;DR — where we are

**Phase 1 personal-intelligence is now substantially built.** The Phase-0 spine + all gap-audit/remediation CRITICALs were already in; the **overnight batch then closed the open Phase-1 work**: Epics **002 (outcome) and 003 (context assembly + the `Episode.date` fix) are DONE**, the access-control invariant is now **proven live in CI** (Epic 015 — required `integration (neo4j)` job), and the 13 design docs are reconciled onto trunk (R4). All verified genuinely-done by an adversarial review (falsification harnesses, full `make check` on the merged tree — no skew). So Phase-1 epics 001–005, 010–015 are DONE; only Epic 006 (novelty), 007 (readiness), 008 (API tests), 009 (eval) remain — **each needs a design/definition pass** (see "Next, and what each needs"). **Open flag:** PR #22 (UI) targets `main` not trunk (R9). Still unmeasured: the Stage-4 cost spike (R5).

---

## 11-stage position

| Stage | Phase | Design | Build | Status |
|---|---|---|---|---|
| 0 Setup | 0 | ✅ | ✅ | Done |
| 1 Data sources | 0 | ✅ | ✅ | Done |
| 2 Schema/graph | 0 | ✅ | ✅ v0.2.0 | Done |
| 3 Corpus pipeline | 0 | ✅ | ✅ | Done — CorpusSource seam landed (Epic 012) |
| 4 Engine + cost | 0 | ✅ | ✅ | Built — **cost spike (real measurement) still pending**; TTL cache now wired (Epic 013) |
| 5 Personalization | 1 | ✅ | ✅ | Belief pipeline (001), commons fork (010), outcome (002), context-assembly + `Episode.date` (003) all **DONE**; novelty (006) + readiness (007) remain |
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
| 002 | Outcome card endpoint | **DONE ✅** | PR #18 — all 20 ACs tested (falsification-checked, not tautologies); all-None preference-marker drains safely. Minor: AC-5.2 stores *stripped* delta vs "raw" (whitespace edge untested) — non-blocking |
| 003 | Context assembly in `engine.plan()` | **DONE ✅** | PR #20 — `Episode.date` now written from `start_time` (R6 fixed); 18-month filter proven as unit + **live-DB E2E**. Minor: seeded-Josh E2E is split (live DB proves the date filter; Curator-enrichment half is fake-backed) — non-blocking |
| 015 | CI Neo4j integration (live owner-isolation guardrail) | **DONE ✅** | PR #19 — **required** `integration (neo4j)` job runs live in GH Actions (6 tests PR / 8 trunk); read+write isolation + a real falsifiability test (removing `owner_scope` reds it). Fast legs stay DB-free |
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

**Merged-to-trunk PRs:** remediation/seam set #2/#5/#6/#7/#9/#10 · roadmap #8/#11/#16 · #12 workflow-lint · #3/#4 dependabot · UI #14/#17 · **overnight batch #18 (close 002) / #19 (Epic 015) / #20 (close 003) / #21 (docs reconcile)**.

---

## Live in-flight (not yet on trunk)

Backend + infra queue is **clear**; the overnight batch all merged. Open items are the UI lane's.

| Lane | Branch / PR | Contents | State |
|---|---|---|---|
| UI | **PR #22** `claude/zen-bohr-b5uf3m` | personal-intelligence UX (plan + mock-first Confidence/Staleness screens; 39 files, frontend-only) | **open → `main` (wrong base, R9)**; build agent owns retarget to trunk + a `/plan`+`/outcome` contract check |
| PM | `claude/roadmap` (this PR) | roadmap v4 | in review |

---

## Dependency graph & next-up per lane

```
DONE (overnight batch, verified) ───────────────────────────────────────
  ✅ Epic 002 close · ✅ Epic 015 CI-Neo4j (live, enforced) · ✅ Epic 003 + Episode.date · ✅ docs reconcile

NEXT WAVE — every remaining Phase-1 epic needs a human design/definition pass first
  Epic 008 (API tests)  ── SMALL: write its epic-with-ACs, ratify → then buildable
  Epic 006 (novelty)    ── needs a been_on PRODUCER (unbuilt) + semantics decided
  Epic 007 (readiness)  ── needs a design session (safety-adjacent: mapping / vendor
                            normalization / party composition); no epic yet
  Epic 009 (eval)       ── needs 006 + the reconciled stage-7 methodology

OTHER OPEN
  PR #22 (UI → main, R9) ── build agent retargets to trunk + contract-checks /plan,/outcome
  Stage-4 cost spike (R5) ── measure once the flow is exercised end-to-end
```

**Next-up by lane:**
- **Needs your design first (pick one to tackle):** Epic 007 (readiness — biggest lift), Epic 006 `been_on` producer, or Epic 008 epic-with-ACs (smallest/quickest to a buildable state).
- **Build agent:** retarget PR #22 to trunk; verify the inert HTTP adapter against trunk's real `/plan`+`/outcome` contracts.
- **UI:** continue design-system Phase 2.

---

## ◆ The overnight batch — COMPLETE & verified (2026-06-26)

All four landed and merged; a 6-reviewer adversarial pass confirmed each DoD is genuinely met (not status-flipped). Full `make check` on the merged tree: **516 passed / 8 neo4j-deselected, ruff + mypy clean; all 6 CI jobs green** incl. the live `integration (neo4j)`. No merge-skew across the four near-simultaneous merges.

1. ✅ **Epic 002 (outcome)** — #18. All 20 ACs tested (falsification-checked). *Minor:* AC-5.2 stores *stripped* delta vs "raw" (non-blocking).
2. ✅ **Epic 015 (CI Neo4j)** — #19. Required `integration (neo4j)` job ran live in GH Actions (6 PR / 8 trunk); falsifiability real.
3. ✅ **Epic 003 + `Episode.date`** — #20. R6 fixed; 18-month filter proven unit + live-DB E2E. *Minor:* E2E split (Curator-enrichment half fake-backed).
4. ✅ **Docs reconcile (R4)** — #21 + earlier UI commits. All 13 docs on trunk; README union preserved DONE statuses; links resolve.

**Still held back (need a human design pass):** Epic 007 readiness (safety-adjacent) · Epic 006 `been_on` producer · Epic 008 epic-with-ACs.

---

## Open risks & cross-cutting threads

| ID | Risk / thread | State | Action / owner |
|---|---|---|---|
| **R1** | **T6 licensing/consent gate.** ODbL `separable` flag has zero code readers (gap-audit m2); best-view cache blends sources → Derivative-DB risk; Valhalla adds unattributed OSM. Commons consent substrate (opt-in + salt) landed with Epic 010, but the public-release ODbL handling is unresolved. | **OPEN** — write half accreting now | **Gates Stage 9 public release.** Enforce separability invariant + ODbL posture before any public commons. Track in T6 doc reconciliation (R4). |
| ~~**R2**~~ | ~~No live-Neo4j test coverage.~~ | **RESOLVED — Epic 015 (PR #19)** | Required `integration (neo4j)` job proves read+write isolation + falsifiability against a real DB, live in CI (verified). |
| **R3** | **C3 auth — interim built, full auth deferred.** Epic 014 S3 added an edge guard (`_authorize_viewer`): any non-anonymous `viewer_id` must present `X-Dev-Viewer-Secret` (constant-time compare) or gets HTTP 403 — fails closed. But at the query layer `ScopedSession` still trusts `viewer_id` verbatim, so a secret-bearing forged id is still a forged write; the dev-secret is a single shared interim credential, not per-user auth. | **PARTIAL** — interim guard built; full auth deferred | Decide managed auth provider (Supabase/Clerk/Auth0 — undecided) at Stage 8; until then the shared dev-secret is the only gate. |
| ~~**R4**~~ | ~~Trunk ↔ design-branch doc divergence (13 docs).~~ | **RESOLVED — PR #21** | All 13 design docs on trunk; README union preserved DONE statuses, links resolve. |
| **R5** | **Cost spike unmeasured.** Stage-4 local-vs-cloud bake-off designed; real cost-per-session not yet measured against the real corpus. TTL cache lever now built (Epic 013), so the estimate's main assumption holds. | **OPEN** | Run the spike once Phase-1 flow stabilizes (needs a real flow to measure). |
| ~~**R6**~~ | ~~M1 `Episode.date` never written.~~ | **RESOLVED — Epic 003 (PR #20)** | `upsert_episode` SETs `e.date` from `start_time`; 18-month filter proven by a live-DB E2E. |
| **R7** | **Always-on infra undecided.** The in-process Garmin poller is built (Epic 004); only the **always-on host** (same-day push) + Stage-8 multiplayer need it. | Deferred | Decide host (VPS/Pi/always-on Mac) at Phase-1→2 boundary. |
| ~~**R8**~~ | ~~CI `workflow-lint` red trunk-wide.~~ | **RESOLVED — PR #12** | `actionlint` now runs via its official download script; `workflow-lint` green trunk-wide. |
| **R9** | **PR #22 (UI) targets `main`, not trunk.** Bypasses the trunk integration/review gate; `main` is *behind* on the backend batch, so "main = integrated state" is false. Merging it as-is forks the integration line (UI-only on main, backend-only on trunk). Content blast radius is nil (frontend-only + one additive `.gitignore` line). | **OPEN** | **Build agent owns:** retarget to trunk; cross-check the "inert" HTTP adapter against trunk's real `/plan`+`/outcome` contracts before it lands. |

### Thread tracker (T1–T7 — mirrors workplan; the M9 fix)

- **T1 · Infra/secrets/CI.** 🔶 `workflow-lint` **fixed (#12)**; FIRMS key log-leak **fixed (#9)**; **live-Neo4j CI guardrail enforced (Epic 015, #19)**. Still open: the `SecretProvider` seam (`.env` plaintext only — gap-audit M6).
- **T2 · Access-control-at-query-layer.** ✅✅ reads + writes seamed (Epic 011); Outcome-endpoint bypass closed (#9); **the invariant is now proven end-to-end against a live Neo4j in CI on every PR (Epic 015)** — a forgotten owner clause reds the build. (Forged-identity auth is still R3.)
- **T3 · Forked commons write.** ✅ built (Epic 010), accreting born-severed observations. Read/aggregation dormant to Stage 9.
- **T4 · Evaluation.** 🔶 truthfulness harness exists; golden-trip set/cassettes unbuilt; Epic 009 (deep eval) + the stage-7 methodology now **on trunk** (R4 reconciled) — defined, unbuilt.
- **T5 · UX.** 🔶 design-system v0.1 + UX specs now **on trunk**; UI lane building the personal-intelligence screens (PR #22). Stage-10 deep work continues.
- **T6 · Legal/licensing/consent.** ⚠️ see R1 — gates Stage 9 public release; separability invariant unenforced.
- **T7 · Naming/branding.** Working title "Adventure Planner"; anytime.

---

## Lane discipline (this doc's owner)

PM lane owns `docs/process/roadmap.md` + `docs/workplan.md`; `docs/epics/README.md` is read-mostly. Never touch `api/`, `graph/`, `orchestration/`, `ingestion/`, `frontend/`, or another lane's epic spec. Work in the `hike-app-pm` worktree; small commits; pull before push; PRs into `claude/vigilant-bohr-yzdcyh`.
