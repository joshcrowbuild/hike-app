# GLM Red-Team: Honesty Gates (2026-07-13)

**Status:** ACTIVE (adversarial findings — 2 failing scenarios gate-skipped, 1 passing)
**Reviewer:** GLM (foreign-model adversarial review)
**Scope:** source-or-silence invariant, six condition states, verdict derivation, guardrail routing

---

## Methodology

Acted as a foreign adversarial reviewer with no stake in the codebase's assumptions.
Studied the full honesty-gate pipeline:

- **Backend condition classification:** `orchestration/engine.py` `_condition_summary` (six states: present, stale_degraded, no_hazard, no_data, unavailable, not_fetched)
- **Guardrail routing:** `orchestration/curator.py` `evaluate_guardrails` (weather → CardWarning, air → block/warn, fire → CardWarning)
- **Presentation:** `orchestration/present.py` (FeedLine formatting, source notes, hedging)
- **Frontend verdict:** `frontend/src/data/verdict.ts` `deriveVerdict` (go/caution/unverified from warnings + conditions)
- **Eval gate:** `evals/replay.py` (hermetic replay, hard expectation checks)
- **Adapters:** `nws.py`, `airnow.py`, `firms.py`, `nps_alerts.py`, `usgs_water.py`

Constructed concrete adversarial inputs targeting:
1. Verified hazards that bypass the warning path
2. Condition states that are untestable in the replay gate
3. Threshold boundary conditions lacking coverage

Each finding is backed by a new eval scenario under `evals/scenarios/`.

---

## Findings Table (ranked by severity)

| ID | Severity | Finding | Scenario | Status | Root Cause |
|----|----------|---------|----------|--------|------------|
| F1 | **HIGH** | NPS closure/danger alerts are not routed to `CardWarning` | `closure-alert-no-warning` | FAILS (gate-skipped) | `evaluate_guardrails` in `curator.py` only checks weather, air, and fire — the `closures` kind (ConditionKind.closures) is absent from the function entirely. The NPS alerts adapter (`nps_alerts.py`) produces a sourced `VerifiedFact` with `count: 1` for a Closure-category alert, the engine classifies it as `present`, and a condition line renders on the card. But no `CardWarning` is generated, so `deriveVerdict` sees zero warnings and returns `"go"` — the card says "Good to go" beside an active closure alert. |
| F2 | **MEDIUM** | `stale_degraded` state is untestable in the replay gate | `stale-degraded-untestable` | FAILS (gate-skipped) | The cassette player in `evals/replay.py` calls `adapter.probe(point)` which invokes `fetch()` without the `now` parameter, so `fetched_at = datetime.now(timezone.utc)` at replay time. `check_condition_states` calls `feed_card(trail)` without `now`, so `render_now` is also current time. `age_s` is always ~0, always less than any `_STALE_HORIZON_S` value. The `stale_degraded` classification logic (`engine.py:643-644`) has zero replay coverage — a bug in the horizon values or comparison operator would go undetected. |
| F3 | **LOW** (passing) | AQI warn threshold (101–200) had no scenario coverage | `aqi-warn-boundary` | PASSES | The existing `guardrail-trip-aqi` scenario tests AQI 250 (block path). No scenario tested the warn-only path (AQI 101–200). This scenario pins AQI 150 to confirm `evaluate_guardrails` correctly routes it to `CardWarning` (not a block), the card carries the warning, and the verdict is `caution`. The code handles it correctly — this scenario documents the boundary and adds missing coverage. |

---

## Detailed Analysis

### F1 (HIGH): Closure alerts bypass the warning path

**Attack vector:** An NPS Closure or Danger alert is a verified, sourced hazard — the adapter produces a `VerifiedFact` with `count: 1` and a source timestamp. The engine classifies the condition as `present` and renders a condition line. But `evaluate_guardrails` (`curator.py:125-212`) only inspects three kinds:

- `ConditionKind.weather` → alerts → `CardWarning`
- `ConditionKind.air` → AQI ≥ 201 → `BlockReason`, AQI 101–200 → `CardWarning`
- `ConditionKind.fire` → hotspot_count > 0 → `CardWarning`

`ConditionKind.closures` is never inspected. The closure fact travels on the card as a condition line, but the guardrail verdict has `warnings=()` and `blocked=False`. The frontend's `deriveVerdict` sees no warnings → tone is `"go"`.

**User-facing impact:** A hiker sees "Good to go" on a trail with an active NPS closure alert. The closure information is present as a condition line, but the verdict headline — the most prominent signal — says go. This is a source-or-silence violation in spirit: a verified hazard is not surfaced as a warning, making the card's headline tone misleading.

**Why the code survives partially:** The condition line itself is source-backed (not a silence violation). The issue is the verdict tone — the headline says "go" when it should say "caution" or "unverified". The card/Detail would agree (both derive from the same warnings list), so there's no card-vs-Detail disagreement, but both are wrong in the same way.

**Fix direction:** Add a `closures` branch to `evaluate_guardrails` that routes `count > 0` to `CardWarning` (not a block — closures are presentation, like weather alerts, per the 2026-07-02 decision pattern).

### F2 (MEDIUM): Stale-degraded is untestable in replay

**Attack vector:** The staleness classification in `_condition_summary` (`engine.py:643-644`) compares `(render_now - fact.fetched_at).total_seconds()` against `_STALE_HORIZON_S`. In the replay gate, both `fetched_at` and `render_now` are `datetime.now(utc)`, so `age_s ≈ 0`. No scenario can ever produce a `stale_degraded` state.

**Why it matters:** The stale_degraded state is one of the six condition states in the product's core vocabulary. If someone accidentally swaps the comparison operator (`<` instead of `>`), inverts the horizon values, or deletes the branch entirely, the replay gate would stay green. The frontend's `stale-degraded` rendering path (which should visually demote aged facts) is also untestable end-to-end through the gate.

**Fix direction:** Thread a `now` parameter through the cassette player's `probe()` call so `fetched_at` can be pinned to a past time, and thread `now` through `check_condition_states`'s `feed_card` call so `render_now` can be pinned to a later time. This would allow scenarios to construct realistic age gaps.

### F3 (LOW, passing): AQI warn boundary coverage

**Not a finding — coverage addition.** The existing `guardrail-trip-aqi` scenario tests AQI 250 (block path, `must_be_blocked`). No scenario tested the warn-only path (AQI 101–200). This scenario pins AQI 150 to confirm the boundary is correctly handled. The code handles it correctly — `evaluate_guardrails` routes AQI 150 to `CardWarning` (not `BlockReason`), the card carries the warning, and the verdict is `caution`.

---

## What was tested and survived

The following adversarial vectors were investigated and found to be handled correctly:

- **Weather alerts with `active_alerts: None`** (alerts sub-call failed): `evaluate_guardrails` correctly routes to `ConditionUnavailable`, not "clear" — the card carries a disclosed "weather alerts couldn't be verified" note. ✅
- **AirNow empty response** (`[]`): Returns `None` (couldn't verify), not a fabricated AQI 0. ✅
- **FIRMS zero detections** (header-only CSV): Returns a sourced fact with `hotspot_count: 0` → `no_hazard` (checked-clear). ✅
- **NPS no park in range**: Returns a sourced `in_range: False` fact → `no_data` (not "clear"). ✅
- **NPS catalog-wide parse failure** (`parseable == 0`): Returns `None` (couldn't verify), not a fabricated coverage claim. ✅
- **NWS forecast URL SSRF**: Validates `forecast_url` starts with `https://api.weather.gov/` before following. ✅
- **NWS alert dedup**: `dict.fromkeys(alerts)` dedupes overlapping issuances. ✅
- **AQI as float**: `int(aqi)` safely converts before threshold comparison. ✅
- **AQI as bool**: `isinstance(aqi, bool)` guard prevents `True` (== 1) from being treated as AQI 1. ✅
- **Blocked trails never surfaced**: `plan_from_origin` routes blocked trails to `set_aside`, never to `planned`. ✅
- **Drive-time facts folded after guardrail check**: Drive facts are added to `facts` after `evaluate_guardrails` runs, so they can never trigger a block. ✅

---

## Scenario inventory

| Scenario | Type | Gate status | Purpose |
|----------|------|-------------|---------|
| `closure-alert-no-warning` | Adversarial (failing) | Skipped | F1: pins closure warning that doesn't exist |
| `stale-degraded-untestable` | Adversarial (failing) | Skipped | F2: pins stale_degraded state that can't be produced in replay |
| `aqi-warn-boundary` | Coverage (passing) | Active | F3: AQI 150 warn-only path (boundary coverage) |
