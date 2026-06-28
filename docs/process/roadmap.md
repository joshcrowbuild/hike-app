# Roadmap — Adventure Planner

*Living status doc. Owned by the PM/planner lane. Terse by design — delete stale entries, wrong memory is worse than none (CLAUDE.md).*

**Last verified:** 2026-06-28 · **Owner:** PM/planner lane · **Repo:** `joshcrowbuild/hike-app` · **Baseline:** tag `v0.1-phase1` @ `c12be36` · `main` is the protected line · **Version:** v9

> **◆ PHASE-1 BASELINE + DOCS OVERHAUL — both complete; `main` is the single line.** Phase-1 build is done (backend personalization + design-system + the personal-intelligence app UX, all verified honest) and collapsed onto `main`, tagged `v0.1-phase1`. Repo is on the `joshcrowbuild` Team org; `main` is the default + protected branch with **7 required CI checks**: `format-check` · `lint` · `typecheck` · `test` · `integration (neo4j)` · `workflow-lint` · `docs-lint`. No force-push/delete; admin override retained. All merged feature branches swept (only `main` remains remote). **The documentation overhaul is complete** (PRs #27–30): 55 live docs (down from 60), ~115KB of closed history archived, 0 broken links, a lean always-load hot path, and a CI `docs-lint` gate that **fails the build on wrong memory** (stale-marker denylist · broken-link check · auto-generated epic index). **Go-forward model:** feature branches off `main`; lanes are conventions, not long-lived branches.

> **◆ MAPS SHIPPED + REAL DATA LOADED — going live (v9).** Two big moves since v8. **(1) Maps shipped:** Epics 016 (frontend) + 017 (backend 3DEP elevation) are **DONE & merged** (#38, #39) — topographic Detail map, assembled route, trailhead, card glyph, and a real elevation profile. The one cross-lane risk (the two lanes guessing differently on the shared wire contract) was caught in pre-merge review and reconciled on #39 before it reached `main`. **(2) Real data exists:** the **Shenandoah-GWJ pilot region is loaded into managed Neo4j (Aura Free)** — **1458 trails, every one with geometry *and* a real 10 m USGS-3DEP elevation profile**, 24 trailheads, ~5.3k nodes / ~6k rels (far under Free caps). Verified honest: 0 half-profiles, full Rule #7 provenance, 96.7% DEM coverage, no-coverage→`null` (never faked). **This flips R7 from "deferred" to "in progress":** frontend = Vercel (decided, live) · DB = Aura Free (provisioned + loaded) · API = Render (deploy config #40 + Aura-TLS CA hardening #41 both merged). **Last two steps to real trails on the phone:** deploy the API to Render + flip the Vercel env to the live API (Josh, this afternoon). A Python CA-path TLS gotcha (Aura over `neo4j+s://`) surfaced during ingest and is fixed app+container + documented (#41).

> Companion to `docs/workplan.md` (the 11-stage agenda + threads T1–T7) and `docs/epics/README.md` (epic index — now generated from epic headers). This doc aggregates *live* state across lanes; the workplan is the plan, the index is the per-epic source of truth, this is the dashboard. New here? Start at `docs/README.md` (the doc map).

---

## TL;DR — where we are

**Phase-1 is baselined; Maps shipped; real data is loaded; the app is going live for real.** Backend personalization (Epics 001–005, 010–015 DONE, verified), the design system, and the app UX are all on `main`. **Maps (Epics 016 + 017) are DONE & merged** (#38/#39) — topo Detail map, route, trailhead, elevation profile. **The Shenandoah-GWJ pilot region is now loaded into Aura Free** (1458 trails + geometry + real 10 m elevation, verified honest), so **the live-data path is in flight (R7 now in progress):** frontend = Vercel · DB = Aura (loaded) · API deploy config + Aura-TLS hardening merged (#40/#41). **The only two steps left to real trails on the phone:** Render deploy + Vercel env flip (Josh, this afternoon). **New follow-ups from the ingest** (none block the demo): verify the 1643→1458 slug merge (~185 collapsed `canonical_id`s — same-trail or collision?), commit the untracked `apply_schema.py` + `python3`/preflight tooling fixes, drop the seeded Old Rag duplicate. **Behind all this, still design-gated:** Epic 008 (API tests, smallest), 006 (novelty — needs a `been_on` producer), 007 (readiness — biggest, safety-adjacent, no epic yet), 009 (eval). **Still unmeasured:** the Stage-4 cost spike (R5).

---

## 11-stage position

| Stage | Phase | Design | Build | Status |
|---|---|---|---|---|
| 0 Setup | 0 | ✅ | ✅ | Done |
| 1 Data sources | 0 | ✅ | ✅ | Done |
| 2 Schema/graph | 0 | ✅ | ✅ v0.2.0 | Done |
| 3 Corpus pipeline | 0 | ✅ | ✅ | Done — CorpusSource seam (012) + **enrichment loader (017)**; **first real region ingested** (Shenandoah-GWJ → Aura, 1458 trails + geometry + 3DEP elevation) |
| 4 Engine + cost | 0 | ✅ | ✅ | Built — **cost spike (real measurement) still pending (R5)**; TTL cache wired (Epic 013) |
| 5 Personalization | 1 | ✅ | ✅ | Belief pipeline (001), commons fork (010), outcome (002), context-assembly + `Episode.date` (003) all **DONE**; novelty (006) + readiness (007) remain |
| 6 Watch integration | 1 | ✅ | 🔶 | Device seam (004) done — **incl. the in-process Garmin poller (`watch_sync`, 55 tests)**; only the **always-on deployment** (R7) + **readiness filter (007, unwritten)** remain |
| 7 Eval deep-dive | 1 | ✅ | ❌ | Methodology designed (on `main`); Epic 009 **DEFINED**; harness unbuilt |
| 8 Multiplayer | 2 | ✅ | ❌ | Designed (on `main`); gated by always-on infra + auth provider (R3/R7) |
| 9 Commons | 3 | ✅ | 🔶 | Write half accreting (010 on `main`); read/aggregation dormant; **gated by T6** |
| 10 Experience/design-system | 4 | ✅ v0.1 | ✅ shipped | design-system + **app UX** (Home/Detail/Tuning/Outcome, Confidence/Staleness honesty primitives) + **Maps (016/017)** all on `main`; topo map + route + real elevation. Going live on real Aura data (R7 final leg) — Render deploy + Vercel flip pending |
| 11 Native shell | 4 | ❌ | ❌ | Not started |

---

## Per-epic status (aggregated from index + live PRs/code)

| # | Epic | Status | Evidence / note |
|---|---|---|---|
| 001 | Belief update pipeline | **DONE ✅** | merged |
| 002 | Outcome card endpoint | **DONE ✅** | PR #18 — all 20 ACs tested (falsification-checked, not tautologies); all-None preference-marker drains safely. Minor: AC-5.2 stores *stripped* delta vs "raw" (whitespace edge untested) — non-blocking |
| 003 | Context assembly in `engine.plan()` | **DONE ✅** | PR #20 — `Episode.date` now written from `start_time` (R6 fixed); 18-month filter proven as unit + **live-DB E2E**. Minor: seeded-Josh E2E is split (live DB proves the date filter; Curator-enrichment half is fake-backed) — non-blocking |
| 004 | Device-integration seam | **DONE ✅** | merged (supersedes Garmin-only 004) |
| 005 | Valhalla drive-time | **DONE ✅** | absorbed into Epic 013 / PR #7 |
| 006 | Novelty filter in Curator | **DEFINED** | epic on `main`; depends on Epic 003 (done) + a `been_on` belief **producer** (unbuilt) + semantics decided |
| 007 | Readiness filter (Body Battery → Curator) | **NOT WRITTEN** | gap-audit M11: no epic file yet; depends on Epic 004 (done); solo-vs-party composition unspecified |
| 008 | API tests (`/plan` + `/health`) | **BACKLOG** | no epic file yet; no deps — quickest to a buildable state |
| 009 | Eval harness expansion | **DEFINED** | epic on `main`; needs 002/003/006 to evaluate |
| 010 | Commons fork write | **DONE ✅** | PR #6 (remediates C1); doc-guard re-inverted now Epic 010 shipped (#32) |
| 011 | Scoped-write seam | **DONE ✅** | PR #6 (remediates C2) |
| 012 | CorpusSource seam | **DONE ✅** | PR #5 (remediates C5) |
| 013 | LiveAdapter seam | **DONE ✅** | PR #7 (remediates C6; +TTL cache, drive-time) |
| 014 | Overlay-egress + viewer-auth hardening (C3 + C4) | **DONE ✅** | PR #7 — C4 egress fix + **C3 interim edge auth** (`_authorize_viewer`: non-anonymous `viewer_id` needs `X-Dev-Viewer-Secret`, fails closed 403); full managed-auth deferred (R3) |
| 015 | CI Neo4j integration (live owner-isolation guardrail) | **DONE ✅** | PR #19 — **required** `integration (neo4j)` job runs live in GH Actions; read+write isolation + a real falsifiability test (removing `owner_scope` reds it). Fast legs stay DB-free |
| 016 | Maps & terrain (topographic Detail map · route · elevation) | **DONE ✅** | #38 — MapLibre topo map + assembled route + trailhead + card glyph + elevation chart. Code-split (feed stays map-free), honest empty/failure states, attribution. Built on mock, swaps to live at the contract |
| 017 | Terrain elevation enrichment (USGS 3DEP profiles) | **DONE ✅** | #39 — enrichment loader (closed the "no graph write yet" gap) + 3DEP sampler → parallel-array store → API on the feed card. Pre-merge review caught + fixed the cross-lane contract drift (snake_case + card placement) before `main`. Real data: 1458 trails carry a 10 m profile in Aura |

**Merged PRs (baseline + docs):** remediation/seam set #5/#6/#7/#9/#10 · UI #14/#17/#22 · overnight batch #18/#19/#20/#21 · R10 secret #25 · roadmap+runbook #26 · **doc overhaul #27/#28/#29/#30** · commons doc-guard #32 · **Maps #38 (frontend) + #39 (backend 3DEP)** · **hosting #40 (Render deploy config + CORS) + #41 (Aura-TLS CA hardening)** · plus the roadmap/workflow-lint/dependabot housekeeping PRs.

---

## Live in-flight

Phase-1, the baseline, the docs overhaul, **and Maps** are all merged. The current push is **going live for real**: Maps shipped, the Shenandoah region is loaded into Aura, and the API is two manual steps from serving real data to the phone.

### ◆ Maps & terrain — SHIPPED ✅ (Epics 016 + 017)
Built dogfood-first ("no maps, I can't see shit") as two parallel lanes that converged at the elevation chart. **016 (frontend, #38):** MapLibre topo Detail map + assembled route + trailhead + card glyph + elevation profile, code-split so the feed stays map-free, with honest empty/failure states + attribution. **017 (backend, #39):** the enrichment **loader** (closed the long-standing "no graph write yet" gap) + USGS-3DEP sampler → parallel-array store → exposed on the feed card. The lanes were coupled only by a frozen wire contract; a **pre-merge adversarial review caught the one real risk — the two lanes had drifted on field casing + placement — and reconciled it on #39 before it hit `main`** (`tests/test_maps_contract.py` now locks the API shape to the frontend type).

### ◆ Live-data path — IN FLIGHT (R7 hosting, going live)
Real data now exists: the **Shenandoah-GWJ pilot region is loaded into Aura Free** (1458 trails + per-segment geometry + 10 m 3DEP elevation, 24 trailheads, ~5.3k nodes — verified honest, full provenance, no fabricated curves). The hosting picture (R7) is resolving piece by piece:
- **Frontend = Vercel** (decided, live) · **DB = Aura Free** (provisioned + loaded) · **API = Render** — deploy config (Docker + `render.yaml` + default-deny CORS, #40) and the Aura-TLS CA hardening (#41) are both merged; a deploy runbook (`docs/runbooks/deploy-api-render.md`) is in place.
- **Remaining (Josh, this afternoon):** ① deploy the API to Render per the runbook, ② flip Vercel env (`VITE_USE_MOCK=false`, `VITE_API_BASE_URL=<render>`, viewer secret) → real Shenandoah trails on the phone.
- **Gotcha resolved (#41):** a Python CA-path gap broke the `neo4j+s://` TLS handshake to Aura ("Unable to retrieve routing information"); fixed in app + container via certifi/`ca-certificates`, **strict TLS preserved** (no `+ssc`/trust-all), with a test guarding against future downgrades.
- **Ingest follow-ups (none block the demo):** verify the 1643→1458 `canonical_id` slug merge (~185 collapsed — same-trail or collision?); commit the untracked `scripts/apply_schema.py` (the Aura schema-applier) + the `make`/`preflight` `python3`/Docker tooling fixes; drop the seeded Old Rag duplicate (`ct:old-rag-loop`); 15/24 trailheads are unlinked (OSM sparsity, not a bug).
- **Still deferred:** the always-on **watch-poller** host (Garmin sync) — not needed to browse trails.

### ◆ Baseline promotion — DONE ✅
Trunk promoted to `main` (`725c442`) · R10 secret fix (#25) · repo → `joshcrowbuild` Team org · default branch → `main` · **branch protection** (7 required checks incl. `integration (neo4j)` + `docs-lint`, no force-push/delete) · tag `v0.1-phase1` cut (`c12be36`) · merged feature branches swept. Nothing outstanding.

### ◆ Documentation overhaul — COMPLETE ✅ (#27–30)
Four waves, one PR each: **(1) Freshness** — killed the stale "current position" in CLAUDE.md/README/decision-log + 6 research banners (point at roadmap as the status SSOT). **(2) Navigation** — new `docs/README.md` map + `docs/research/README.md` index (25 docs classified) + wired roadmap into CLAUDE.md. **(3) Dedupe/archive** — `git mv` ~115KB closed audits → `docs/research/archive/`; folded decision-log-additions §32–40 into the decision log; single-sourced git/PR hygiene into `development-process.md`. **(4) Anti-drift** — `scripts/gen_epic_index.py` + `scripts/doc_lint.py` + the CI `docs-lint` job (denylist · broken-link · epic-index-sync). Result: a lean hot path, a findable map, and a gate that fails on wrong memory. *PM follow-ups closed: `docs-lint` added to branch protection; this v7 reconciliation.*

---

## Dependency graph & next-up per lane

```
DONE & BASELINED ─────────────────────────────────────────────────────────
  ✅ Phase-1 backend (001–005, 010–015) · ✅ app UX · ✅ R10 secret · ✅ docs overhaul
  ✅ v0.1-phase1 tag · ✅ commons doc-guard (#32) · ✅ Maps (016/017, #38/#39)
  ✅ Shenandoah-GWJ loaded into Aura (1458 trails + geometry + 10 m elevation)

GOING LIVE NOW — the last leg of the real-data path (R7 in progress)
  ✅ frontend = Vercel · ✅ DB = Aura (loaded) · ✅ API config #40 + Aura-TLS #41 merged
  ▶ ① deploy API to Render (runbook) → ② flip Vercel env → real trails on the phone (Josh, PM)
  follow-ups (non-blocking): verify 1643→1458 slug merge · commit apply_schema.py + tooling fixes
                             · drop seeded Old Rag dup · watch-poller host still deferred

BEHIND IT — the design-gated Phase-1 remainder
  Epic 008 (API tests)  ── SMALL: write its epic-with-ACs, ratify → buildable (no deps)
  Epic 006 (novelty)    ── DEFINED, needs a been_on PRODUCER (unbuilt) + semantics decided
  Epic 007 (readiness)  ── needs a design session (safety-adjacent); NO epic file yet
  Epic 009 (eval)       ── DEFINED; needs 006 closed + golden-trip set / cassettes

OTHER OPEN
  Stage-4 cost spike (R5) ── now measurable: a real corpus + Anthropic query-time path exist
  Watch-poller host       ── the one still-deferred piece of R7 (Garmin sync; not needed to browse)
```

**Next-up by lane:**
- **Going live (the priority, Josh this afternoon):** ① deploy the API to Render per the runbook, ② flip the Vercel env to the live API → real Shenandoah trails on the phone. Then dogfood the *real* data and let the next findings set priorities.
- **Hardening follow-ups (build lane, post-live):** audit the 1643→1458 slug merge; commit `apply_schema.py` + the `python3`/preflight tooling fixes; drop the seeded Old Rag duplicate.
- **Behind that (your design call, when ready):** Epic 007 (readiness — biggest, safety-adjacent), Epic 006's `been_on` producer, or Epic 008's epic-with-ACs.

---

## ◆ The overnight batch — COMPLETE & verified (2026-06-26)

All four landed and merged; a 6-reviewer adversarial pass confirmed each DoD is genuinely met. Full `make check` on the merged tree: **516 passed / 8 neo4j-deselected, ruff + mypy clean; all CI jobs green** incl. the live `integration (neo4j)`. No merge-skew across the four near-simultaneous merges.

1. ✅ **Epic 002 (outcome)** — #18. All 20 ACs tested (falsification-checked). *Minor:* AC-5.2 stores *stripped* delta vs "raw" (non-blocking).
2. ✅ **Epic 015 (CI Neo4j)** — #19. Required `integration (neo4j)` job ran live in GH Actions; falsifiability real.
3. ✅ **Epic 003 + `Episode.date`** — #20. R6 fixed; 18-month filter proven unit + live-DB E2E. *Minor:* E2E split (Curator-enrichment half fake-backed).
4. ✅ **Docs reconcile (R4)** — #21 + UI commits. Design docs on `main`; README union preserved DONE statuses; links resolve.

**Still held back (need a human design pass):** Epic 007 readiness (safety-adjacent) · Epic 006 `been_on` producer · Epic 008 epic-with-ACs.

---

## Open risks & cross-cutting threads

| ID | Risk / thread | State | Action / owner |
|---|---|---|---|
| **R1** | **T6 licensing/consent gate.** ODbL `separable` flag has zero code readers (gap-audit m2); best-view cache blends sources → Derivative-DB risk; Valhalla adds unattributed OSM. Commons consent substrate (opt-in + salt) landed with Epic 010, but the public-release ODbL handling is unresolved. | **OPEN** — write half accreting now | **Gates Stage 9 public release.** Enforce separability invariant + ODbL posture before any public commons. |
| ~~**R2**~~ | ~~No live-Neo4j test coverage.~~ | **RESOLVED — Epic 015 (#19)** | Required `integration (neo4j)` job proves read+write isolation + falsifiability against a real DB, live in CI. |
| **R3** | **C3 auth — interim built, full auth deferred.** Epic 014 S3 added an edge guard (`_authorize_viewer`): any non-anonymous `viewer_id` must present `X-Dev-Viewer-Secret` (constant-time compare) or gets HTTP 403 — fails closed. But at the query layer `ScopedSession` still trusts `viewer_id` verbatim, so a secret-bearing forged id is still a forged write; the dev-secret is a single shared interim credential, not per-user auth. | **PARTIAL** — interim guard built; full auth deferred | Decide managed auth provider (Supabase/Clerk/Auth0 — undecided) at Stage 8; until then the shared dev-secret is the only gate. |
| ~~**R4**~~ | ~~Trunk ↔ design-branch doc divergence (13 docs).~~ | **RESOLVED — #21 + docs overhaul** | All design docs on `main`; the docs overhaul (#27–30) then indexed + drift-guarded the whole surface. |
| **R5** | **Cost spike unmeasured.** Stage-4 local-vs-cloud bake-off designed; real cost-per-session not yet measured. TTL cache lever built (Epic 013); ingest confirmed corpus-load is deterministic (no LLM), so spend is a *query-time* concern (intent + curation). | **OPEN — now measurable** | A real Aura corpus + the Anthropic query-time path now exist; run the spike against live `/plan` once the API is deployed. |
| ~~**R6**~~ | ~~M1 `Episode.date` never written.~~ | **RESOLVED — Epic 003 (#20)** | `upsert_episode` SETs `e.date` from `start_time`; 18-month filter proven by a live-DB E2E. |
| **R7** | **Hosting/compute — resolving piece by piece.** Frontend = **Vercel** (live). DB = **Neo4j Aura Free** (provisioned + Shenandoah loaded). API = **Render** (deploy config #40 + Aura-TLS hardening #41 merged; the actual Render deploy + Vercel env flip are the two remaining manual steps). Only the always-on **watch-poller** host (Garmin sync, Epic 004) + Stage-8 multiplayer compute stay deferred. | **IN PROGRESS** — DB+frontend done, API deploy pending | Josh deploys the API to Render + flips Vercel this afternoon → first real-data dogfood. Revisit Aura Free's caps/idle-pause + the watch host if/when usage grows. |
| ~~**R8**~~ | ~~CI `workflow-lint` red trunk-wide.~~ | **RESOLVED — #12** | `actionlint` now runs via its official download script; `workflow-lint` green. |
| ~~**R9**~~ | ~~PR #22 (UI) targets `main`, not trunk.~~ | **RESOLVED** | Retargeted + merged; honesty invariants verified. The contract-check surfaced R10. |
| ~~**R10**~~ | ~~HTTP-adapter dev-viewer-secret gap (guaranteed 403 on live calls).~~ | **RESOLVED — #25** | `httpPlanner.ts` now injects `X-Dev-Viewer-Secret` from `VITE_DEV_VIEWER_SECRET` for non-anonymous viewers (omitted for anonymous; tested). Live-data wiring is unblocked; secret stays in `.env` (Rule #10). |

### Thread tracker (T1–T7 — mirrors workplan; the M9 fix)

- **T1 · Infra/secrets/CI.** ✅ `workflow-lint` fixed (#12); FIRMS key log-leak fixed (#9); **live-Neo4j CI guardrail enforced (Epic 015)**; **doc-drift now CI-guarded (`docs-lint`, #30)**. Still open: the `SecretProvider` seam (`.env` plaintext only — gap-audit M6).
- **T2 · Access-control-at-query-layer.** ✅✅ reads + writes seamed (Epic 011); Outcome-endpoint bypass closed (#9); **the invariant is proven end-to-end against a live Neo4j in CI on every PR (Epic 015)** — a forgotten owner clause reds the build. (Forged-identity auth is still R3.)
- **T3 · Forked commons write.** ✅ built (Epic 010), accreting born-severed observations. Read/aggregation dormant to Stage 9. (Doc-guard cleanup in flight — build lane.)
- **T4 · Evaluation.** 🔶 truthfulness harness exists; golden-trip set/cassettes unbuilt; Epic 009 (deep eval) + the stage-7 methodology on `main` — **DEFINED**, unbuilt.
- **T5 · UX.** ✅ design-system v0.1 + the **personal-intelligence app UX** (Home/Detail/Tuning/Outcome + Confidence/Staleness honesty primitives, verified honest) + **Maps (016/017): topo map, route, real elevation**. Going live on real Aura data (Render deploy + Vercel flip pending).
- **T6 · Legal/licensing/consent.** ⚠️ see R1 — gates Stage 9 public release; separability invariant unenforced.
- **T7 · Naming/branding.** Working title "Adventure Planner"; anytime.

---

## Lane discipline (this doc's owner)

PM lane owns `docs/process/roadmap.md` + `docs/workplan.md`; `docs/epics/README.md` is read-mostly (now generated by `gen_epic_index.py`). Never touch `api/`, `graph/`, `orchestration/`, `ingestion/`, `frontend/`, or another lane's epic spec. Work in the `hike-app-pm` worktree; small commits; pull before push; **PRs into `main`** (the baseline).
