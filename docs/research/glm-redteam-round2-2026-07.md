# GLM Red-Team Round 2: New Honesty Surfaces (2026-07-13)

**Status:** OPEN — F4 and F6 are disclosure gaps (not fabrication); F9 is a coverage gap
**Reviewer:** GLM (foreign-model adversarial review, round 2)
**Scope:** surfaces added since round 1 — two-phase render (Epic 040), water overlay (Epic 041), feed conditions ribbon + closure warnings

---

## Methodology

Acted as a foreign adversarial reviewer targeting the three honesty surfaces added
since round 1. Studied each surface end-to-end:

- **Two-phase render:** `orchestration/two_phase.py` (plan_cards, plan_conditions,
  verify_planned, _compose_and_warm), `orchestration/feed_cache.py` (phase-1 holding
  pen, 180s TTL), `api/app.py` (/plan, /plan/conditions endpoints, _condition_fields),
  `api/schemas.py` (PlanConditionsResponse, ConditionPatchResponse), frontend
  `PlannerProvider.tsx` (useFeed hook, phase-1 paint + phase-2 patch composition),
  `composeConditions.ts` (in-place patch application), `httpPlanner.ts` (planConditions
  mapping), `vm.ts` (ConditionsPatchVM, CardConditionsPatch), and the full test suite
  in `PlannerProvider.test.tsx` and `composeConditions.test.ts`.

- **Water overlay (Epic 041):** `api/app.py` (_water_sources, three-way silence),
  `graph/queries.py` (water_sources_near), `api/schemas.py` (TrailWaterResponse,
  WaterSourceResponse), `tests/test_water_surface.py` (unit tests), and
  `tests/test_trail_detail_endpoint.py` (integration tests).

- **Feed conditions ribbon + closure warnings:** `frontend/src/data/feedConditions.ts`
  (splitFeedConditions, hoisting logic), `feedWarnings.ts` (splitFeedWarnings),
  `orchestration/curator.py` (evaluate_guardrails, _closure_alerts, closure warning
  generation), `orchestration/engine.py` (_is_checked_clear, _is_coverage_gap),
  `orchestration/adapters/nps_alerts.py` (fact production, three-way silence),
  and the existing round-1 scenario `closure-alert-no-warning`.

Constructed adversarial inputs targeting:
1. Timing holes and cache discipline in the two-phase flow
2. Three-way silence boundary cases in the water overlay
3. Hoisting correctness and closure warning edge cases in the feed ribbon

Each finding is backed by code-level analysis. Two new eval scenarios are included
for testable findings; frontend-only and API-layer gaps are documented with proposed
test approaches.

---

## Findings Table (ranked by severity)

| ID | Severity | Finding | Scenario | Status | Surface |
|----|----------|---------|----------|--------|---------|
| F4 | **MEDIUM** | `unknown` ids from phase-2 patch silently dropped by frontend — no user disclosure | — | OPEN | Two-phase |
| F6 | **LOW-MEDIUM** | Graph-fallback path (holding pen expired) has zero eval coverage and loses composition fidelity | — | OPEN | Two-phase |
| F9 | **LOW-MEDIUM** | `unavailable` disclosures dropped by frontend in both patch and full-feed mapping | — | OPEN (pre-existing) | Two-phase / Full-feed |
| F7 | **LOW** | Water overlay three-way distinction has zero replay-gate coverage (unit tests are strong) | — | OPEN (by design) | Water overlay |
| F10 | **LOW** | Feed conditions ribbon hoisting has no integration-level gate (unit tests cover the logic) | — | OPEN (by design) | Feed ribbon |
| F11 | **LOW** (passing) | Multi-category closure warnings (Closure + Danger) had no scenario coverage | `closure-multi-category` | PASSES | Closure warnings |
| F12 | **LOW** (passing) | Closures checked-clear (count=0) had no scenario coverage | `closure-checked-clear` | PASSES | Closure warnings |

---

## Detailed Analysis

### F4 (MEDIUM): `unknown` ids silently dropped by frontend

**Attack vector:** The backend `PlanConditionsResponse` includes an `unknown: list[str]`
field — canonical ids the backend could not resolve at all (the holding pen expired and
the graph lookup found nothing). The API schema documents this: "Requested ids the
backend could not resolve at all — disclosed, never fabricated."

The frontend `httpPlanner.ts:planConditions()` mapping (lines 369-381) completely
ignores `res.unknown`:

```typescript
return {
  patches: res.patches.map((p) => ({ ... })),
  heldBack: (res.set_aside ?? []).map((s) => ({ ... })),
}
```

The `ConditionsPatchVM` interface (`vm.ts:369-372`) has no `unknown` field. The
`composeConditions` function has no handling for unknown ids. A card whose id appears
in `unknown` stays with its phase-1 `not-fetched` silence — which is honest, but the
user gets no disclosure that the backend explicitly attempted resolution and failed.

**User-facing impact:** A card that the backend says "I can't resolve this" looks
identical to "I haven't checked yet." The phase-1 `not-fetched` silence is honest, but
the distinction between "not yet verified" and "verified, couldn't find" is lost. The
card silently stays in its pending state with no error or disclosure.

**Why it survives:** The silence is honest (Rule #1 holds — no fabricated facts). The
card's per-kind states are all `not-fetched`, which is truthful. The issue is a
disclosure gap, not a fabrication. The user sees a card with no conditions and no
indication that resolution was attempted.

**Fix direction:** Add an `unknown: string[]` field to `ConditionsPatchVM` and
`CardConditionsPatch`, map it in `httpPlanner.ts:planConditions()`, and in
`composeConditions` either (a) remove unknown cards from the composed feed and disclose
them at the feed level (like `heldBack`), or (b) mark them with a disclosure note
("couldn't resolve this trail's conditions"). Option (a) is more consistent with the
existing `heldBack` pattern.

**Test approach:** A frontend unit test in `PlannerProvider.test.tsx` that mocks
`planConditions` returning a patch with `unknown: ['some-id']` and asserts the
composed feed either removes the card or discloses the resolution failure.

---

### F6 (LOW-MEDIUM): Graph-fallback path has zero eval coverage

**Attack vector:** When the phase-1 holding pen expires (180s TTL), `plan_conditions`
falls back to `_patch_from_graph` — a path that probes the trails' own points without
the phase-1 plan context. The code documents this: "a faithful composition needs the
phase-1 plan; a partial one must never pose as it."

The replay gate's `run_scenario_two_phase` always uses `verify_planned` (the
holding-pen path). The graph-fallback path is never exercised by any test or eval
scenario. This means:

- Drive-time facts from phase 1 are lost (the graph fallback doesn't have them)
- The composition may differ from what a single-pass would have produced
- The `from_cache` flag is set to `False` but this is only used for metrics, not for
  any user-facing disclosure

**User-facing impact:** The user still gets verified conditions for each card — the
honesty invariant holds. But the conditions may differ from what a single-pass would
have produced (e.g., different drive times, missing drive-time lines). There's no
disclosure that the conditions were computed from a partial context.

**Why it survives:** Each card's conditions are still honestly sourced — the probes
run against the trails' own points, and the guardrail evaluation is the same. The gap
is in composition fidelity, not honesty. The drive-time line may be missing, but
that's an enrichment gap, not a fabrication.

**Fix direction:** Add a replay-gate criterion that exercises the graph-fallback path
by simulating holding-pen expiry (would require a new harness feature). Alternatively,
add a unit test in `tests/test_two_phase.py` that calls `plan_conditions` with an
empty/expired holding pen and verifies the graph-fallback behavior.

---

### F9 (LOW-MEDIUM): `unavailable` disclosures dropped by frontend

**Attack vector:** The `_condition_fields` function (`api/app.py:321-358`) maps
`unavailable` from `FeedCard` to `ConditionUnavailableResponse` in both the full feed
and the phase-2 patch. The wire types in `api.ts` include `unavailable?` on both
`FeedCardResponse` and `ConditionPatchResponse`.

But the frontend mapping in both paths drops it:

- `mapFeed` (`httpPlanner.ts:123-167`): maps `conditionLines`, `conditions`,
  `warnings`, but NOT `unavailable`
- `planConditions` (`httpPlanner.ts:369-381`): maps `conditionLines`, `conditions`,
  `warnings`, but NOT `unavailable`
- `CardVM` (`vm.ts`) has no `unavailable` field
- `CardConditionsPatch` (`vm.ts:375-380`) has no `unavailable` field

**User-facing impact:** When a condition couldn't be verified (e.g., weather probe
failed), the backend sends an `unavailable` disclosure with a cause and source. The
frontend silently drops it. The card's per-kind `conditions` array still shows
`unavailable` state for that kind, so the user sees the state — but the specific
cause text ("weather couldn't be verified") and source attribution are lost.

**Why it survives:** This is a pre-existing gap in BOTH paths (full feed and patch),
not a two-phase regression. The `conditions` array carries the `unavailable` state,
so the card does show "couldn't verify" — just without the detailed cause/source
disclosure that the backend provides.

**Fix direction:** Add an `unavailable` field to `CardVM` and `CardConditionsPatch`,
map it in both `mapFeed` and `planConditions`, and render it on the card.

---

### F7 (LOW): Water overlay has zero replay-gate coverage

**Attack vector:** The water overlay three-way distinction (sources / none_nearby /
silence) is the core honesty surface of Epic 041. The replay gate
(`evals/replay.py`) has no water overlay criteria — `run_scenario` and
`run_scenario_two_phase` don't exercise the water overlay at all.

**Why it's LOW:** The water overlay is an API-layer enrichment, not an engine-layer
condition — it's structurally outside the replay gate's scope. The unit test coverage
in `tests/test_water_surface.py` is excellent: it covers all three states, distance
honesty, basis selection (route vs start), error degradation, sorting, capping, and
the no-potability-claim guard. The integration tests in
`tests/test_trail_detail_endpoint.py` cover the end-to-end detail payload.

**What's missing:** No integration-level gate exercises the water overlay through the
replay harness. A bug in the API layer that misclassified `none_nearby` as `silence`
or vice versa would not be caught by the replay gate. The unit tests would catch it,
but the replay gate provides an additional layer of protection for engine-layer
invariants.

**Fix direction:** This is a known architectural boundary. The water overlay is
correctly tested at the unit and integration level. Adding it to the replay gate
would require extending the harness to exercise API-layer enrichments, which is out
of scope for the current gate design.

---

### F10 (LOW): Feed conditions ribbon hoisting has no integration gate

**Attack vector:** `splitFeedConditions` and `splitFeedWarnings` are frontend-only
functions with complex hoisting logic (strict majority, verbatim line matching,
severity ordering). The replay gate only exercises engine-layer code.

**Why it's LOW:** The unit test coverage in `feedConditions.test.ts` and
`feedWarnings.test.ts` is thorough: it covers verbatim hoisting, differing readings
kept per card, silent states hoisted, value-bearing states not hoisted, no hoisting
on ties or single-card feeds, severity ordering, and empty feed behavior. The logic
is well-tested at the unit level.

**Fix direction:** The hoisting logic is correctly tested at the unit level. An
integration-level test would require a frontend E2E harness, which is out of scope
for the current gate design.

---

### F11 (LOW, passing): Multi-category closure warnings

**Not a finding — coverage addition.** The existing `closure-alert-no-warning`
scenario tests one Closure-category alert. No scenario tested the case where the NPS
alerts endpoint returns BOTH a Closure and a Danger alert for the same park. This
scenario verifies that `evaluate_guardrails` generates a separate `CardWarning` for
each category, that `dict.fromkeys` deduplication works correctly (same title +
different category = both warn), and that the warning text includes the category and
park scope. The code handles it correctly.

---

### F12 (LOW, passing): Closures checked-clear

**Not a finding — coverage addition.** No scenario tested the case where the NPS
alerts endpoint returns zero relevant alerts (Closure/Danger). The adapter produces
a fact with `count: 0`, the engine classifies it as `no_hazard` (checked-clear), and
no `CardWarning` is generated. This scenario pins that behavior: the closures
condition state is `no_hazard`, no closure warning appears, and the card is not
blocked. The code handles it correctly — `_is_checked_clear` for closures checks
`value.get("count") == 0` and routes to the `no_hazard` state.

---

## What was tested and survived

The following adversarial vectors were investigated and found to be handled correctly:

- **Phase-1 holding pen cache discipline** (`feed_cache.py`): The holding pen is
  separate from the feed cache, with its own short TTL (180s). Phase-1 plans are
  never served as full plans prematurely. The `get_or_compute` method is
  single-flighted through the cache's own gate. ✅

- **Phase-1 silence invariant** (`two_phase.py:plan_cards`): Phase 1 returns cards
  with zero live probes — every probe-able kind is `not_fetched` with no attribution.
  The replay gate's `check_phase1_silence` criterion enforces this. ✅

- **Two-phase composition equivalence** (`replay.py:check_two_phase_composition`):
  The composed (phase-1 + phase-2) output is equivalent to the single-pass output
  over the same bundle: same surfaced set, same per-kind facts, same dispositions,
  same warnings, same unavailable disclosures, same set-asides, same notices. ✅

- **D4 write-gate** (`PlannerProvider.tsx:320-321`): Only the composed
  (phase-2-complete) feed reaches the snapshot or the stale-paint cache. An
  all-not-fetched frame is never persisted. The test `AC-3.5` verifies this. ✅

- **Phase-2 patch failure handling** (`PlannerProvider.tsx:326-339`): A patch
  failure keeps the phase-1 cards usable with their honest silence, discloses the
  gap, and retry re-posts phase 2 only (not the whole plan). Test `AC-3.4` verifies
  this. ✅

- **Stale-paint cache never holds phase-1 frame** (`PlannerProvider.test.tsx:574-600`):
  The write-gate holds until the patch resolves. The test verifies nothing is cached
  while revalidating, and the cached feed has `conditionsPending: undefined` and
  verified conditions. ✅

- **Water overlay three-way distinction** (`test_water_surface.py`): All three states
  (sources, none_nearby, silence) are correctly distinguished. Distance honesty is
  maintained for both `route` and `start` basis. Error degradation returns silence,
  never a 500. ✅

- **Water overlay no-potability guard** (`test_water_surface.py:215-221`): Field
  names in `WaterSourceResponse` and `TrailWaterResponse` never carry potability
  tokens. ✅

- **Closure warning generation** (`curator.py:235-258`): Verified NPS closure/danger
  alerts generate `CardWarning` entries with category, title, park scope, and source.
  Deduplication via `dict.fromkeys` prevents duplicate warnings. ✅

- **Closure checked-clear** (`engine.py:173-184`): A closures fact with `count: 0`
  is correctly classified as `no_hazard` — the checked-clear silence state. ✅

- **Closure no-data** (`engine.py:161-170`): A closures fact with `in_range: False`
  is correctly classified as `no_data` — the coverage-gap silence state. ✅

- **Feed conditions ribbon majority hoisting** (`feedConditions.ts`): Strict majority
  (> n/2) required for hoisting. Verbatim line matching. Value-bearing states not
  hoisted. No hoisting on ties or single-card feeds. ✅

- **Feed warnings banner severity ordering** (`feedWarnings.ts`): Warnings sorted by
  severity in the banner. Trail-specific warnings excluded from banner. No hoisting
  on single-card feeds. ✅

---

## New Eval Scenarios

### `closure-multi-category` (PASSES)

Pins two NPS alerts (Closure + Danger) for Shenandoah NP. Verifies:
- Both categories generate separate `CardWarning` entries
- Warning text includes category and park scope
- `dict.fromkeys` deduplication works (different category = both warn)
- Condition state for closures is `present`
- No trails are blocked (closures are presentation-only)

### `closure-checked-clear` (PASSES)

Pins zero relevant NPS alerts (empty alerts list). Verifies:
- Adapter produces a fact with `count: 0`
- Engine classifies closures as `no_hazard` (checked-clear)
- No `CardWarning` generated for closures
- No trails blocked
- The distinction between "checked, nothing to flag" and "not checked" is maintained

---

## Comparison to Round 1

Round 1 found three issues (F1: HIGH, F2: MEDIUM, F3: LOW). F1 and F2 were fixed and
now block the gate. Round 2 finds no HIGH-severity issues — the new surfaces are
well-built with strong honesty discipline. The findings are disclosure gaps (F4, F9)
and coverage gaps (F6, F7, F10), not fabrication vectors. The two-phase render's
core invariants (phase-1 silence, composition equivalence, write-gate, patch-failure
handling) are all correctly implemented and tested. The water overlay's three-way
distinction is correct with comprehensive unit tests. The closure warning path
(fixed in round 1) is now covered by three scenarios testing the full range of
closure states.
