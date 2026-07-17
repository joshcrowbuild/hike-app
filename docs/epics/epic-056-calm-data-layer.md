# Epic 056 — Calm data layer (session conditions cache · phase-2 budget · wire parsing)

**Status:** IN_PROGRESS
**Phase:** 1 (frame-conditions wave, mechanics lane)
**Spec refs:** `docs/design-system/frame-conditions-wave.md` §5 (wire), §6 (behavior); ground truth in §1

---

## Capability statement

Moving around the app no longer refetches conditions: the composed feed
(conditions included) is reused for the whole session, and `/plan/conditions`
fires only on a genuinely new frame or an explicit Refresh. The 60-second
"Checking current conditions…" feeling is gone — chips are pending
immediately and the surface degrades honestly at ~12 s while late data still
fills. The new wire fields (severity, region_conditions,
personalization_degraded) flow through to the VM.

## Architectural context

Builds on: Epic 040's two-phase render; Epic 052's per-viewer localStorage
cache (cold-start behavior unchanged); PR-0's `vm.ts` extensions.
Enables: Epic 055's card states (it renders whatever this lane exposes —
`pending`→`revalidating`, degrade→`revalidateError`, refresh→`reload()`).
Does NOT include: ANY file under `frontend/src/screens/` or `Home.tsx`
(Epic 055 owns those); backend changes (054).

---

## Stories

### S1 — Session-lifetime conditions reuse
**AC-1.1:** Re-mounting `useFeed` with the same scope+frame key reuses the
in-memory composed feed — no `/plan` POST, no `/plan/conditions` POST
(feed → Detail → back is fetch-free).
**AC-1.2:** A changed frame (any facet) or scope is a real refetch.
**AC-1.3:** `reload()` forces phase-1 + phase-2 fresh (the Refresh affordance
and banner retry).
**AC-1.4:** Cold-start localStorage stale-paint behavior unchanged
(conditions still neutralized on read).

### S2 — Phase-2 presentation budget
**AC-2.1:** Phase-2 pending is exposed immediately (`revalidating`), never a
blocking overlay.
**AC-2.2:** At ~12 s without resolution, expose the degraded state
(`revalidateError`) while the 60 s fetch abort stays; a late success still
composes and clears the error.
**AC-2.3:** `reload()` after degrade re-enters phase 2 only (existing
`retryConditions` path preserved).

### S3 — Wire parsing
**AC-3.1:** `severity` ("heads_up"/"blocked") → `WarningVM.severity`
('headsUp'/'blocked'); absent → undefined.
**AC-3.2:** `region_conditions` → `RegionConditionsVM` (snake→camel,
humanised ages, null-safe); rides `FeedVM.regionConditions` from both
`/plan` and the phase-2 patch (`composeConditions` merges it).
**AC-3.3:** `personalization_degraded` → `FeedVM.personalizationDegraded`.
**AC-3.4:** Mapping tests over fixture payloads incl. nulls + missing fields.

### S4 — Detail fetch calm
**AC-4.1:** `getCard` (deep link) and `GET /trail/{id}` water responses cached
in-memory per session (key: id + scope); re-opening a Detail is fetch-free.
**AC-4.2:** Failures degrade exactly as today (null water, error card path).

---

## Definition of Done
- [ ] All ACs covered by at least one passing test
- [ ] `npm run build` + `npm test` green
- [ ] Targeted review agent run; CRITICALs fixed
- [ ] Committed and pushed
