# Epic 022 — Duration truth: wire the dead-computed Naismith estimate through the live feed with a render-layer estimate disclosure

**Status:** DEFINED
**Phase:** 1
**Spec refs:** CLAUDE.md Rules #1 (source-or-silence) / #7 (provenance + confidence — an inference never poses as a stated fact) · CoMaps borrow plan item A5 (wave 1) · decision-log (estimate-vs-fact disclosure)

---

## Capability statement
A live trail's Detail screen shows an honest hiking-duration estimate — the Naismith's-rule figure the backend already computes but the frontend today silently drops — rendered with an explicit "estimate" disclosure so it is never mistaken for a verified fact.

## Architectural context
**Builds on:** Epic 016/017 (the maps/terrain payload — `WireElevationProfile` and the VM `ElevationProfile`). The backend ALREADY computes and attaches the estimate: `api/app.py:608-611` (`_estimated_duration_min`, classic Naismith's rule — 5 km/h base pace + 0.1 min per metre of ascent) and `api/app.py:648` writes it onto `ElevationProfile(estimated_duration_min=…)`; `api/schemas.py:134` declares the field with the explicit "never a stated fact" contract. The wire DTO already mirrors it: `frontend/src/data/api.ts:127` (`WireElevationProfile.estimated_duration_min: number`).

**The dead value (the whole bug):** the HTTP adapter's `mapElevationProfile` (`frontend/src/data/http/httpPlanner.ts:136-146`) maps every other profile field onto the VM but NOT `estimated_duration_min`, and the VM `ElevationProfile` interface (`frontend/src/data/vm.ts:177-185`) has no field to receive it. So the computed number reaches the browser and is thrown away. Meanwhile Detail renders Duration ONLY from `enrichment.durationHours` (a mock-only string) — `frontend/src/screens/Detail.tsx:116-118` — so a LIVE card (which has no `enrichment`) never shows a duration at all, and the estimate never surfaces.

**Enables:** an honest live Duration decision-fact on Detail; the substrate for a later Tobler/pace-personalised ETA (Epic 007 / D2) without re-plumbing.

**Does NOT include:**
- Any edit to `api/app.py` or `api/schemas.py` — the backend already computes and attaches the estimate correctly. This epic is pure frontend wiring + disclosure.
- Tobler-function or pace-personalised ETA — that is D2 / Epic 007-gated, explicitly out of scope. Ship the plain Naismith figure the backend already gives.
- Any change to the mock `enrichment.durationHours` string path or the mock engine — that is separate `sample`-provenance data already disclosed by the sample strip.
- Any ranking/scoring use of duration — duration is presentation-only, never a rank signal (Rule #2).

**BINDING verifier corrections (from the CoMaps borrow plan, item A5 — the builder cannot read the plan, so they are embedded here):**
1. **`durationHours` is a formatted STRING; `estimated_duration_min` is a NUMBER nested on `WireElevationProfile`.** Do NOT "fix" this by editing the one-liner at `vm.ts:88` (`durationHours?: string` on `CardEnrichment`) — that is the mock string field and is a red herring. The NEW field is a NUMBER on the VM `ElevationProfile` (vm.ts:177-185), mirroring the wire's nesting. Two different concepts; keep them distinct.
2. **The estimate disclosure does not exist today.** `Detail.tsx:117` renders `<DecisionItem label="Duration" value={e.durationHours} …>` with NO qualifier — nothing marks it an estimate. Rules #1/#7 require it: a Naismith figure is an inference, not a stated fact, so the render layer MUST disclose it as an estimate. Build that qualifier at the render layer.

---

## Stories

### S1 — Carry the computed estimate through the adapter onto the view-model

**Given** the backend attaches `estimated_duration_min` (a NUMBER) on `WireElevationProfile`, and the wire DTO already declares it
**When** the HTTP adapter maps a card's `elevation_profile` to the VM `ElevationProfile`
**Then** the VM carries `estimatedDurationMin`, so the computed figure is no longer silently dropped at the adapter boundary

**AC-1.1:** `ElevationProfile` in `frontend/src/data/vm.ts` (interface at lines 177-185) declares a new `estimatedDurationMin?: number` — a NUMBER, nested on the profile. It is NOT a string and is NOT added to `CardEnrichment` (leave `vm.ts:88 durationHours?: string` untouched). [verifier correction 1]
**AC-1.2:** `mapElevationProfile` in `frontend/src/data/http/httpPlanner.ts:136-146` sets `estimatedDurationMin: p.estimated_duration_min`. The `if (!p) return null` branch is unchanged (a null wire profile still yields a null VM profile — no fabricated figure).
**AC-1.3:** A unit test in `frontend/src/data/http/httpPlanner.test.ts` asserts that a wire profile with `estimated_duration_min: 26` surfaces as `result.cards[0].geo?.elevationProfile?.estimatedDurationMin === 26`. (The existing fixture at `httpPlanner.test.ts:158-166` already sets `estimated_duration_min: 26` but never asserts it — add the assertion, extending that test or adding a sibling.)
**AC-1.4:** `WireElevationProfile` in `frontend/src/data/api.ts` (lines 119-128) already declares `estimated_duration_min: number` (line 127), matching `api/schemas.py:134`. The builder VERIFIES this and leaves it unchanged unless a genuine mismatch is found — no new wire field is invented. (This is why `api.ts` appears in the touched-file list even though it likely needs no diff.)

### S2 — An honest minutes→string transform (never false precision, always marked an estimate)

**Given** `estimatedDurationMin` is a raw Naismith float (e.g. `25.9`, `155.4`)
**When** it is formatted for display
**Then** it renders as a coarse, human, explicitly-approximate string — never a raw decimal posing as verified precision

**AC-2.1:** A pure function `formatEstimatedDuration(minutes: number): string` lives in a NEW module `frontend/src/data/duration.ts` with its own unit test `frontend/src/data/duration.test.ts` (mirrors the one-util-per-file layout of `data/age.ts`, `data/geo.ts`). New module gets tests before its caller.
**Pinned output template (one deterministic shape all S2 tests assert against):** `~<duration core> · est.` — a leading `~`, the coarse duration core, then a ` · est.` disclosure suffix. Examples: `26` → `~25 min · est.`, `155` → `~2 hr 35 min · est.`, `120` → `~2 hr · est.`. The `est.` token lives INSIDE the `formatEstimatedDuration` return value (per prompt §Approach — `cardParts.tsx`/`DecisionItem` is out of scope, so the disclosure must be folded into the string, never a component change). Because `DecisionItem` renders `value` as a single text node, the whole template is one string.

**AC-2.2:** The output carries an approximation marker (a leading `~`) and rounds to avoid false precision: a raw `25.9` never renders with a decimal figure like `25.9 min`. Round the duration to the nearest 5 minutes. A positive minutes value that rounds down to 0 floors at `~5 min · est.` — never `~0 min` (Rule #1: no fabricated zero). (A test asserts `formatEstimatedDuration(25.9)` starts with `~` and contains no false-precision decimal — i.e. it matches neither `/\d\.\d/` nor a `.\d` before a unit; the `.` inside the `est.` token is fine and is not a decimal digit.)
**AC-2.3:** Values `≥ 60` min render hours, plus minutes when the remainder is nonzero — `155` → `~2 hr 35 min · est.`, `120` → `~2 hr · est.`. Values `< 60` min render minutes — `26` → `~25 min · est.`. Tests assert the numeric core with `toContain`, NOT `toBe` (the `· est.` suffix is asserted by AC-2.4 on the same output; `toBe` on a bare core would contradict AC-2.4): `expect(formatEstimatedDuration(155)).toContain('2 hr 35 min')`, `expect(formatEstimatedDuration(120)).toContain('2 hr')`, `expect(formatEstimatedDuration(26)).toContain('25 min')`. (Pin at least one of each of hr+min / hr-only / min-only.)
**AC-2.4:** The Duration fact is disclosed as an estimate: the `formatEstimatedDuration` output carries the explicit `est.` token from the pinned template (a `~2 hr` figure with no qualifier is a fail — Rules #1/#7). A test asserts `expect(formatEstimatedDuration(155)).toContain('est')` on the SAME output whose core AC-2.3 checks. [verifier correction 2]

### S3 — Surface the live estimate on Detail, disclosed, where nothing shows today

**Given** a LIVE card with a real `geo.elevationProfile` (so `estimatedDurationMin` is present) but no mock `enrichment.durationHours`
**When** Detail renders the decision-facts row
**Then** a Duration fact appears — formatted by S2, carrying the S2 estimate disclosure — where today a live card shows no duration at all (verifier correction 2)

**AC-3.1:** `frontend/src/screens/Detail.tsx` renders a `DecisionItem` labelled `Duration` (glyph `glyphs.duration`) from `card.geo?.elevationProfile?.estimatedDurationMin` when `enrichment.durationHours` is absent — mirroring the existing `ascentFeet` fallback at `Detail.tsx:75` (`e?.ascentFeet ?? geoAscentFeet(card.geo)`). The change lives in the `detail-facts` block (`Detail.tsx:104-119`).
**AC-3.2:** The rendered live-estimate Duration fact includes the estimate qualifier from AC-2.4. A Detail test asserts the disclosure text (substring `est`) is present in the Duration fact for a live-profile card. Because `DecisionItem` renders the whole value (`~25 min · est.`) as one text node, an exact-string `getByText('est')` will NOT match — use a substring/regex matcher, e.g. `screen.getByText(/est/)`, or assert on the `.decision-value` node's `textContent`.
**AC-3.3:** The existing mock path is unchanged: when `enrichment.durationHours` is present it still renders its string (`3–4 hr`), and the existing assertion in `frontend/src/screens/Detail.test.tsx:76` (`getByText('3–4 hr')`) still passes.
**AC-3.4:** When neither `enrichment.durationHours` nor a profile `estimatedDurationMin` exists, NO Duration fact renders — never a fabricated or zero figure (Rule #1). (A test with a card whose `geo.elevationProfile` is `null` and no `durationHours` asserts no Duration item appears.)
**AC-3.5:** Scope fence holds: no edit to `api/app.py`/`api/schemas.py` (grep the diff), and no Tobler/pace/Epic-007 ETA logic is introduced.

---

## Definition of Done
- [ ] All ACs covered by at least one passing test
- [ ] Frontend gate green: `npm run test` and `npm run build` (tsc typecheck + vite build) from `frontend/`
- [ ] Repo `make check` green (no Python touched, but confirm nothing broke)
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed
- [ ] Epic file copied into `docs/epics/` and a row added to `docs/epics/README.md` index
- [ ] Committed and pushed; PR opened into `main`
