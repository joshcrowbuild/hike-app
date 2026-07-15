# Epic 045 — Deep-link a trail by id: a verified card for any trail

**Status:** DEFINED
**Phase:** C (Real Intake) / cross-cutting UX correctness
**Spec refs:** dogfood 2026-07-14 (signed-in deep-link `/#/trail/ct:osm:way_138445924` → "This trail isn't in your current set") · CLAUDE.md Rule #1 (source-or-silence) · Epic 038 (`_plan_from_candidates` shared tail) · Epic 040 (condition states)

---

## Capability statement

The app resolves a trail **directly by its canonical id** — returning a fully verified card with sourced+timestamped live conditions — so any deep link, bookmark, shared link, page refresh on Detail, or (soon) saved-trails / manual-log tap opens the trail, instead of only trails that happen to sit in the current origin-based feed's top-K.

## The bug this closes

`useCard` (frontend) resolves a tapped/linked trail by **re-running `/plan` from a fallback origin and searching its top-K results** (`httpPlanner.getCard` → `planWith`). A trail outside that set returns null → Detail renders "This trail isn't in your current set." The backend already serves the trail: `GET /trail/{id}` returns 200 with full corpus detail (verified via live probe 2026-07-14). The stale `getCard` comment even claims "No GET /trail/{id} exists yet" — it does. What's missing is a **card-shaped** response carrying live conditions for a single id.

## Architectural context

**Builds on:** `/search` (Epic 038) — the exemplar: it takes non-origin candidates, runs the SAME verify→present pipeline as `/plan` (`search_trails` → `_plan_from_candidates`), and returns a `FeedResponse` with `conditions_complete=True`. This epic is the by-**id** analogue of by-**name** search.
**Enables:** honest deep links · refresh-on-Detail · shared links · the upcoming saved-trails and manual-log (Epic 042) taps, which all address a trail by id.
**Does NOT include:** any change to the existing `GET /trail/{canonical_id}` → `TripDetailResponse` (geometry/elevation/water — leave it exactly as is; it serves the map + elevation + water slice) · personalized ranking (a single card has no ranking) · auth changes (this path is viewer-independent — a trail's conditions are the same for everyone; anonymous verify→present, mirroring `/search`).

---

## Stories

### S1 — Candidate-by-id in the graph + scout

**AC-1.1:** `graph/queries.candidate_trail_by_id(canonical_id)` returns a single-row candidate projection with the **same fields, same shape** as `candidate_trails_by_name` (so the verify→present tail is byte-for-byte reusable). Unknown id → zero rows.
**AC-1.2:** `orchestration.scout.scout_by_id(canonical_id, session)` returns `list[Candidate]` of length 0 or 1, mirroring `scout_by_name`.

### S2 — Engine: verify→present one trail by id

**AC-2.1:** `orchestration.engine.plan_trail_by_id(canonical_id, session, probes, *, cache, probe_max_workers)` mirrors `search_trails` — scout-by-id → the shared `_plan_from_candidates` tail — returning a batch with 0 or 1 verified `PlannedTrail`s (live conditions + confidence + warnings + set-aside, per Rule #1). No new verify/present logic; reuse the shared tail.

### S3 — Endpoint: `GET /trail/{canonical_id}/card`

**Given** a canonical id
**When** `GET /trail/{canonical_id}/card` is called
**Then** it returns a `FeedResponse` (the `/plan` and `/search` shape) with the one verified card (`conditions_complete=True`), or an **honest-empty `FeedResponse`** (never a 404, never an error) when the id doesn't exist

**AC-3.1:** the response schema is exactly `FeedResponse` — identical to `/plan`/`/search`, so the frontend reuses its existing feed→card mapping unchanged.
**AC-3.2:** the card carries sourced+timestamped conditions + confidence (source-or-silence); a set-aside/unverifiable trail routes through the existing set-aside/flagged path, never a false clear.
**AC-3.3:** anonymous-capable, same rate-limit class as `/plan`/`/search`; assembly mirrors the `/search` handler (`_feed_response(..., conditions_complete=True)`), with the same observability (`PlanMetrics`) and correlation-id error handling.
**AC-3.4:** a real trail that is NOT in any default-origin top-K (the exact dogfood id `ct:osm:way_138445924`) resolves to a card here — the regression that proves the bug is closed.

### S4 — Frontend: resolve deep links by id

**AC-4.1:** `HttpPlannerClient.getCard(id, scope, tuning)` calls `GET /trail/{id}/card` and maps the single returned card to `CardVM` (reuse the existing feed→card mapping). The "re-run `/plan` and search top-K" hack is removed; the stale "No GET /trail/{id} exists yet" comment is corrected.
**AC-4.2:** the in-memory snapshot fast-path in `useCard` is unchanged (a card tapped from the live feed still resolves instantly from `feedSnapshot`); only the miss path changes.
**AC-4.3:** the mock planner client (`VITE_USE_MOCK`) gets the parallel `getCard`-by-id behavior so mock and live stay identical (find the trail in the mock corpus by id; honest-not-found only for a genuinely unknown id).
**AC-4.4:** "This trail isn't in your current set" now shows **only** for a genuinely nonexistent id; a transient/network failure maps to the retryable error state, never to `notfound` (preserve the existing R1 throw-on-transient discipline).

---

## Definition of Done
- [ ] All ACs covered by tests; the S3.4 regression (the exact dogfood id, or a fixtured non-top-K id) is explicit
- [ ] Frontend: `getCard` deep-link test (mock + http) resolves a non-feed id; "not in your current set" only on true absence
- [ ] `make check` green (backend + frontend vitest + tsc + build)
- [ ] Live verification (operator/PO): `GET /trail/ct:osm:way_138445924/card` returns a card with conditions on the hosted API; the deep link opens in the app
- [ ] Targeted review agent run; CRITICALs fixed
