# Epic 054 — Conditions truth backend (severity · frame-date forecast · recent precip · mud)

**Status:** IN_PROGRESS
**Phase:** 1 (frame-conditions wave, backend lane)
**Spec refs:** `docs/design-system/frame-conditions-wave.md` §1 (Q7/Q18/Q19), §5 (the pinned wire schema)

---

## Capability statement

The engine can now say *how bad* a hazard is (graded `heads_up` vs `blocked`
instead of one undifferentiated warning), *what the weather will be on the day
the user is actually going* (NWS forecast periods selected by the frame's
`when`, not just `periods[0]`), *how much it rained recently*, and — hedged,
quantified, and provenance-tagged `inferred` — *whether trails may be muddy*.

## Architectural context

Builds on: the NWS adapter's existing multi-day forecast fetch (it already
pulls the full periods doc and discards all but `periods[0]`); the dormant
`when` parameter that already exists on `LiveAdapter.probe` and in the
TTLCache key but is never populated; `_STALE_HORIZON_S` per-kind freshness.
Enables: Epic 055's forecast zone + day toggle + mud read; Epic 056's severity
parsing.
Does NOT include: any frontend change; forecasting non-weather kinds (AQI /
fire / streamflow / closures are current-only upstream — verified); AHPS river
forecasts; AirNow's forecast endpoint.

---

## Stories

### S1 — Graded warning severity

**Given** the curator builds a warning for a hazard
**When** the wire payload is emitted
**Then** each warning carries `severity: "heads_up" | "blocked"`.

**AC-1.1:** NWS alert `severity` is no longer dropped at the adapter; alerts
graded `Extreme`/`Severe` → `blocked`, else → `heads_up`.
**AC-1.2:** AQI ≥ 201 → `blocked`; 101–200 → `heads_up` (existing thresholds
unchanged).
**AC-1.3:** NPS Closure/Danger warnings → `blocked`; fire/water warnings →
`heads_up`; any ungraded path defaults to `heads_up` (never louder than
graded).
**AC-1.4:** Schema + tests cover both values; old clients unaffected
(additive field).

### S2 — Frame-date forecast

**Given** a plan request whose tuning carries a `when` key
**When** conditions are fetched
**Then** the response's `region_conditions.forecast` holds per-day forecasts
(Today + the frame's candidate days) with the frame's `target_key`, selected
from the NWS forecast doc already being fetched.

**AC-2.1:** `when` → target days per the spec table (tomorrowMorning →
[today, tomorrow]; weekend* → [today, sat, sun] of the coming weekend;
fullDay → [today, sat, sun] targeting today), region-local tz
(`ADVENTURE_REGION_TZ`, default `America/New_York`).
**AC-2.2:** The NWS adapter selects daytime periods matching each target date
from the single forecast document — no additional NWS calls per day.
**AC-2.3:** Forecast unavailable → `forecast: null` (source-or-silence; never
a fabricated day).
**AC-2.4:** The region-level probe runs once per plan (region centroid), not
per card.

### S3 — Recent precipitation

**Given** the region's NWS observation station reports precipitation
**When** conditions are fetched
**Then** `region_conditions.recent_precip` holds per-day rain for the last 3
days + `total_48h_in`.

**AC-3.1:** Station resolved via the points doc's `observationStations`; no
station or no precip fields → `recent_precip: null` (disclosed silence, never
zero-filled).
**AC-3.2:** Fetch is cached with the existing TTL mechanics; failures degrade
without failing the plan.

### S4 — Mud inference

**Given** recent precip totals exist
**When** `total_48h_in >= ADVENTURE_MUD_PRECIP_48H_IN` (default 0.5)
**Then** `region_conditions.mud` carries a hedged statement, quantified
evidence, source, and `provenance: "inferred"`.

**AC-4.1:** Statement always hedged ("may"), never categorical.
**AC-4.2:** Missing precip data → no mud block (an inference from absent data
is fabrication).
**AC-4.3:** Threshold env-tunable; calibration = unit tests over fixture
scenarios (dry, trace, soaking, missing-data) + a threshold-rationale note in
this epic.

### S5 — Wire + personalization flag

**AC-5.1:** `region_conditions` rides `/plan/conditions` (and the classic
complete `/plan` path) exactly per the pinned schema; absent on phase-1
shells.
**AC-5.2:** `personalization_degraded: bool` emitted whenever the judge falls
back to generic ranking (Q8).
**AC-5.3:** API schema tests + engine tests green; `make check` green.

---

## Definition of Done
- [ ] All ACs covered by at least one passing test
- [ ] `make check` green
- [ ] Targeted review agent run; CRITICALs fixed
- [ ] Committed and pushed
