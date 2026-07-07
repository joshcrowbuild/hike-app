# Epic 032 — Grade-aware pedestrian ETA (port Valhalla's MIT grade-speed curve)

**Status:** REVIEW
**Phase:** 1 (CoMaps/OSS borrow — Wave 1, `valhalla-pedestrian` lane)
**Spec refs:** CLAUDE.md Rules #1 (source-or-silence), #2 (confidence never penalizes ranking / weight-vs-eta split), #7 (an inference never poses as a stated fact; capability ≠ preference) · research briefs `docs/research/valhalla-pedestrian.md` and `docs/research/brouter-profiles.md` (this sprint) · CoMaps borrow plan item **D2** (per-segment hiking ETA) · builds on Epic 022 (duration-truth wiring) · Epics 016/017 (maps + 3DEP elevation profile)

> **Sources (read end-to-end before coding):**
> - `/Users/joshcrow/.hike-lanes/oss-sprint/research/valhalla-pedestrian.md` — the verdict (**port the math, don't call the deployed Valhalla**) + every `file:line` anchor.
> - `/Users/joshcrow/.hike-lanes/oss-sprint/research/brouter-profiles.md` — the independent BRouter+CoMaps Tobler second opinion + the speed-vs-grade oracle table this epic's cross-check test is built from.

---

## Capability statement
A live trail's Detail screen shows a hiking-duration estimate that **respects the shape of the climb** — it slows on sustained ascent, speeds slightly on gentle descent, and slows again on steep descent — instead of the flat whole-route Naismith figure that ignores where the elevation actually goes. The number stays viewer-independent and disclosed as an estimate.

## Architectural context

**Builds on:**
- Epic 022 already wired the backend `estimated_duration_min` through the adapter → view-model → Detail with a render-layer `est.` disclosure. **That plumbing and disclosure are unchanged by this epic** — we only replace how the number is *computed*.
- `_elevation_profile(row)` (`api/app.py:692-727`) already reads the persisted per-sample arrays `profile_distances_m` / `profile_elevations_m` (`api/app.py:706-715`) and already runs `compute_gain_loss_grade` over them. **The per-segment integral's input data is already in hand at the exact call site** (`api/app.py:726`) — zero new network, zero new query, zero schema change.
- The distance arrays are **horizontal cumulative ground distance** (`ingestion/elevation.py` docstrings: "the profile's x-axis is real distance"; `_cumulative_ground_distance` uses great-circle horizontal distance). So per-segment grade = `Δelev / Δhoriz-dist` is planimetric rise/run — exactly Tobler's tangent. **No slope-distance correction needed.**

**Enables:** an honest, climb-shaped live Duration on Detail; the un-personalized substrate a later `pace_on_grade` effort-floor (Epic 007) would multiply — without re-plumbing.

**Does NOT include (scope fence — a diff touching any of these fails review):**
- **NO `pace_on_grade` personalization / effort-floor / effort rank term.** That is Epic-007-gated (Rule #7: the watch measures *capability*, not *preference*; folding a measured pace into a surfaced-to-everyone number, or into ranking, is forbidden until Epic 007's design session). The number this epic produces is generic physics, viewer-independent, anonymous-safe. **Do not read `PhysicalProfile.pace_on_grade`, do not touch `orchestration/engine.py` or `orchestration/belief_update.py`.**
- **NO call to the deployed Valhalla.** `orchestration/adapters/valhalla.py` is `costing:"auto"` drive-time only, built on tiles that almost certainly lack an elevation dataset — a pedestrian call there collapses to the flat grade bucket (research §4.1) and would *downgrade* our authoritative 10 m 3DEP. We **port the curve constants into Python**, we do not route.
- **NO >2500 m altitude term.** Valhalla's pedestrian model has none; CoMaps' `kMountainSicknessAltitudeM=2500` never triggers on our sub-2500 m corpus (Shenandoah/Richmond/OBX). Carry it as a documented no-op at most; build no logic and no UI for it.
- **NO ranking use.** ETA is presentation-only and must never become a rank signal (Rule #2, weight-vs-eta split). This epic touches only the surfaced number, never a Curator/Scout score.
- **NO schema-shape change.** `estimated_duration_min` stays a single `float` on `ElevationProfile` with the ESTIMATE disclosure (`api/schemas.py:134`). The docstring wording may change from "Naismith's-rule" to "grade-aware … ESTIMATE"; the field, its type, and the "never a stated fact" contract stay.
- **NO frontend change.** Epic 022 already renders and discloses the field. This epic is backend-only (`api/app.py` + tests).

**License / attribution (BINDING — this is a code PORT, not pattern-only):**
- **Valhalla is MIT** (`/Users/joshcrow/.hike-lanes/oss-sprint/repos/valhalla-pedestrian/COPYING`, "Copyright (c) 2018 Valhalla contributors / Mapzen"). **PORT-OK:** the 16-entry `kGradeBasedSpeedFactor` array and its DIN-33466/modified-Tobler derivation (`src/sif/pedestriancost.cc:169-216`) MAY be copied into `api/app.py` **with an attribution header** naming the source file and the MIT license.
- **BRouter (MIT) and CoMaps/Organic Maps (Apache-2.0)** are **cross-check-only** in this lane: their Tobler constants (`exp(-3.5·…)`, offset `+0.05`) are used **only to build the oracle test fixture** (an independent second opinion), never copied as product code. Re-derive the Tobler speeds in the test from the published formula.

---

## Stories

### S1 — Port Valhalla's grade→time-factor curve into `api/app.py` with attribution

**Given** Valhalla's MIT `kGradeBasedSpeedFactor` — a 16-bucket curve indexed by weighted grade, `1.33× at −10%` (steep-descent slowdown, DIN 33466) → **`0.88×` fastest at −3%** → `1.00× flat` → `2.50× at +15%` (`pedestriancost.cc:201-216`), where the factor is a **time multiplier** (higher = slower) applied to the reported `sec` at `pedestriancost.cc:747-750`
**When** we port the constants and expose a grade→factor lookup
**Then** `api/app.py` carries the curve as data with an attribution header and a pure interpolation helper

**AC-1.1:** `api/app.py` defines two parallel module constants: the grade breakpoints (percent) `(-10.0, -8.0, -6.5, -5.0, -3.0, -1.5, 0.0, 1.5, 3.0, 5.0, 6.5, 8.0, 10.0, 11.5, 13.0, 15.0)` and the matching time factors `(1.33, 1.22, 1.08, 0.97, 0.88, 0.92, 1.00, 1.10, 1.20, 1.33, 1.43, 1.57, 1.83, 2.03, 2.23, 2.50)` — verbatim from `pedestriancost.cc:201-216`. Both arrays have length 16 (a test asserts `len(...) == 16` for each and that the flat breakpoint `0.0` maps to factor `1.00`).
**AC-1.2:** An **attribution header comment** immediately precedes the constants, naming: the source `valhalla/valhalla src/sif/pedestriancost.cc` (`kGradeBasedSpeedFactor`, lines ~201-216), the license (**MIT**), and the copyright ("Copyright (c) 2018 Valhalla contributors / Mapzen"). (A test greps the source file for the substrings `"pedestriancost"`, `"MIT"`, and `"Valhalla"` within the module so the attribution can't be silently dropped.)
**AC-1.3:** A pure helper `_grade_time_factor(grade_pct: float) -> float` returns the factor by **piecewise-linear interpolation between breakpoints** (our 10 m 3DEP beats Valhalla's coarse 16 buckets, so we interpolate rather than quantize — research §5 fidelity note). Exact-breakpoint inputs return the exact tabulated factor: `_grade_time_factor(0.0) == 1.00`, `_grade_time_factor(-3.0) == 0.88`, `_grade_time_factor(15.0) == 2.50`. A midpoint interpolates: `_grade_time_factor(-4.0)` lies strictly between `0.88` and `0.97` (a test asserts `0.88 < f < 0.97`).
**AC-1.4:** For grades **outside** `[-10%, +15%]`, `_grade_time_factor` **linearly extrapolates from the two endpoint buckets** (NOT clamp): below −10% the factor keeps *rising* (steeper descent → slower, honest per DIN/Tobler); above +15% it keeps rising (steeper ascent → slower). Tests: `_grade_time_factor(-20.0) > _grade_time_factor(-10.0)` (i.e. `> 1.33`) and `_grade_time_factor(30.0) > _grade_time_factor(15.0)` (i.e. `> 2.50`). (Clamping is a defect here — it would make a −40% descent read *faster* than a −10% one; see the oracle in S3.)

### S2 — Replace the flat estimator with a per-segment grade-aware integral

**Given** `_estimated_duration_min` today is flat Naismith over two whole-route scalars — `(distance/1000)/5.0*60 + gain*0.1` (`api/app.py:686-689`, constants `:682-683`), called at `api/app.py:726` as `_estimated_duration_min(distances_f[-1], gain)`
**When** we replace it with an integral over the per-sample arrays already in hand
**Then** the estimate reflects the climb's shape, stays honest at 5 km/h on the flat, and drops the now-redundant separate ascent term

**AC-2.1:** `_estimated_duration_min` is re-signatured to take the parallel sample arrays — `_estimated_duration_min(distances_m: list[float], elevations_m: list[float]) -> float` — and its call site at `api/app.py:726` passes `(distances_f, elevations_f)` (both already computed at `:711-712`). No other production call site exists (verified: `grep -rn _estimated_duration_min api/` shows only the definition + `:726`). The old `(distance_m, gain_m)` two-scalar signature is gone.
**AC-2.2:** The estimate is a **sum over consecutive segments**: for each segment, `grade_pct = (Δelev / Δhoriz-dist) * 100`, and `segment_min = (Δhoriz-dist/1000) / 5.0 * 60 * _grade_time_factor(grade_pct)`. The **flat pace anchor is 5.0 km/h** (CoMaps flat-normalized form: the flat breakpoint factor is `1.00`, so a level route yields exactly the 5 km/h base — Rule #1, the surfaced flat number stays honest). The separate `gain * 0.1` ascent term is **removed** — the ascent slowdown now lives in the grade factor (do not double-count).
**AC-2.3 (flat honesty):** A perfectly flat profile (all elevations equal) yields the flat-pace duration exactly: for a 5000 m flat profile the result is `pytest.approx(60.0)` minutes (5 km ÷ 5 km/h). A test pins this.
**AC-2.4 (climb slows it):** For the same horizontal distance, a sustained-ascent profile takes strictly longer than a flat one, and a steeper ascent takes strictly longer than a gentler one (monotonic in grade). Tests pin both.
**AC-2.5 (gentle descent is slightly faster than flat; steep descent is slower):** A profile that descends at a steady −3% takes **less** time than the same-distance flat profile (factor `0.88 < 1.0`); a profile that descends at a steady −20% takes **more** time than flat (extrapolated factor `> 1.0`). Two tests pin the sign of each — this is the whole point of the epic vs. flat Naismith, which never slows for descent.
**AC-2.6 (DEM-jitter guard):** Sub-threshold DEM noise must not inflate the estimate. The implementation coarsens to a minimum segment ground-length before computing each segment grade (module constant `_ETA_MIN_SEGMENT_M`, e.g. `30.0` m — comfortably above the `DEFAULT_NOISE_THRESHOLD_M = 3.0` m jitter floor), accumulating short samples until the run clears it. A test: two profiles with identical endpoints and net gain, one smooth and one with ±2 m per-sample jitter added, produce estimates within a small tolerance (e.g. `rel=0.05`) — the jitter version does not blow up. (Rationale mirrors `ingestion.elevation._max_grade_pct`'s windowing, `ingestion/elevation.py:99-123`.)
**AC-2.7 (degenerate input):** `< 2` samples, or a total horizontal distance of `0`, returns `0.0` (no fabricated time); zero-length individual segments are skipped (no divide-by-zero). Tests pin the empty/single-sample and duplicate-point cases.
**AC-2.8 (contract preserved):** `_elevation_profile` still returns `ElevationProfile(..., estimated_duration_min=<the new value>)`; the field stays a single `float` and the `api/schemas.py:134` "never a stated fact" ESTIMATE disclosure is unchanged (the docstring may be reworded from "Naismith's-rule" to "grade-aware … ESTIMATE" but the field, type, and disclosure remain). A test asserts the field is still present and finite on a full profile.

### S3 — Speed-vs-grade oracle: cross-check the ported curve against the independent BRouter+CoMaps Tobler second opinion

**Given** BRouter (MIT) and CoMaps (Apache-2.0) independently converge on Tobler's hiking function — `exp(-3.5·|g + 0.05|)`, optimum offset `+0.05`, flat ≈ 5 km/h — which is an **independent corroboration** of the *shape* of the climb-speed curve (research brief `brouter-profiles.md`, "the one load-bearing finding")
**When** we assert our ported Valhalla curve against a re-derived Tobler oracle at 10 grades from −40% to +40%
**Then** the two independent models agree on the *shape and direction* (both slow on ascent, both fastest in the −1.5…−5% sweet spot, both slower-than-flat on steep descent, both ≈5 km/h flat), documenting where they diverge in *magnitude* — Valhalla's DIN-derived curve is the **more conservative** sibling

**AC-3.1 (oracle fixture):** A test module defines the effective **speed (km/h)** our model implies at each grade `g` — computed as `dist / (_estimated_duration_min(constant-grade profile) / 60)` over a synthetic constant-grade segment — at `g ∈ {−40, −30, −20, −10, −5, 0, +10, +20, +30, +40}` %. Alongside it, the **re-derived Tobler oracle** `tobler_kmh(g) = 5.0 * exp(3.5 * (0.05 − |g/100 + 0.05|))` (CoMaps flat-anchored form — re-derived in the test from the formula, NOT copied from CoMaps source). Expected Valhalla-model speeds (informative, for the fixture): `≈ 1.7, 2.1, 2.7, 3.8, 5.2, 5.0, 2.7, 1.6, 1.1, 0.85`; Tobler (evaluated from the `+0.05`-offset formula, so descent is **asymmetric** to ascent — do NOT sanity-check these against a symmetric mirror): `≈ 1.75, 2.48, 3.52, 5.0, 6.0, 5.0, 3.5, 2.5, 1.75, 1.23`. (These are informative only — the test re-derives both rows from the formulas; with these corrected values `our_kmh/tobler_kmh` stays in `(0.5, 2.0)` at all 10 grades, so AC-3.5 holds.)
**AC-3.2 (flat anchor honesty):** At `g = 0`, our model's effective speed is `pytest.approx(5.0)` km/h and Tobler is `pytest.approx(5.0, rel=0.02)` — both honest at 5 km/h flat (Rule #1). Pinned.
**AC-3.3 (descent sweet spot):** Both models are **faster than flat** somewhere in the −1.5…−5% band: our model's speed at `g = −3` and `g = −5` is `> 5.0`, and Tobler's peak (near −5%) is `> 5.0`. Pinned. (This is the behavior flat Naismith can never produce.)
**AC-3.4 (ascent monotonic + Valhalla more conservative):** On ascent (`g = 0 → +40`), our model's effective speed is **strictly decreasing**, and at every ascent grade our (Valhalla-DIN) speed is `≤` Tobler's (the DIN curve is the more conservative/slower sibling — e.g. at +10% our `≈2.7` ≤ Tobler `≈3.5`). Both pinned as an ordered walk over the fixture.
**AC-3.5 (steep descent both slower than flat, same order of magnitude):** Below ~−12% both models drop below 5 km/h; across the full −40…+40% range the two independent models stay within the **same order of magnitude** (assert `0.5 < our_kmh / tobler_kmh < 2.0` at each of the 10 grades) — corroboration of *shape*, explicitly **not** a false-precision 1% equality (the DIN vs Tobler magnitude gap is the documented finding, brief §"Risks"). A comment in the test records that the ~1% agreement cited in the brief is between **BRouter and CoMaps** (both Tobler), whereas **Valhalla-DIN is deliberately more conservative**.

---

## Definition of Done
- [ ] All ACs (S1–S3) covered by at least one passing test in `tests/test_app_eta.py`
- [ ] The pre-existing tests that call the **old** `_estimated_duration_min(distance_m=…, gain_m=…)` signature or pin its flat-Naismith outputs are **migrated to the new model**, not left broken:
  - `tests/test_elevation_profile_api.py:58-80` — the `_estimated_duration_min` monotonic/`matches_naismiths_rule`/`34.8`-pin tests (re-signature the calls; replace the exact flat pins with grade-model pins or move them into `test_app_eta.py`; keep the `_elevation_profile` provenance/gain tests untouched).
  - `tests/test_trail_detail_endpoint.py:188,392` — the `estimated_duration_min == pytest.approx(33.0)` endpoint pins (recompute the expected value under the new model from that test's fixture profile and update; the endpoint contract itself is unchanged).
  - `tests/test_maps_contract.py:45` and any other test that only asserts the field's *presence* stay green untouched.
- [ ] `make check` green (`ruff format --check` + ruff + mypy + pytest) before the commit
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed, MODERATE+ documented
- [ ] Attribution header present in `api/app.py` for the ported Valhalla constants (S1 AC-1.2)
- [ ] Epic file copied into `docs/epics/` and an index row added to `docs/epics/README.md` (status `REVIEW` at PR-open)
- [ ] Committed on `claude/grade-aware-eta` and pushed; PR "Epic 032: Grade-aware pedestrian ETA — FOR REVIEW" opened into `main` with the 5 sections (summary / why / scope / validation / merge-risk)
