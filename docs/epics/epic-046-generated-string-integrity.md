# Epic 046 — Generated-string integrity (repetition collapse · degenerate-output guards · Character-line honesty)

**Status:** REVIEW
**Phase:** 1 (personal-intelligence app; conditions + Detail surface)
**Spec refs:** `docs/research/generated-string-integrity-sweep-2026-07.md` (the
sweep this epic executes — findings A1–A5, B1–B8, C1–C2, D1–D4, E1) ·
`docs/research/ux-review-conditions-2026-07.md` (F4/F5/F8 origin) · CLAUDE.md
**Rule #1** (source-or-silence) · **Rule #2** (presentation never touches
ranking) · design-system §7 (hedge without clutter).

---

## Capability statement

Every user-facing string states its fact **once, cleanly, and only when it
carries information** — the Detail conditions block stops printing `just now`
11× and stops rendering each condition twice, the backend `_body` builders stop
leaking `1 nearby facilities` / `AQI 45 (None)` / a raw gauge address, and the
Character line stops asserting `— clear today` above a sourced "storms likely"
reading.

## Architectural context

**Builds on:**
- `orchestration/present.py::summarize_fact` — the live wire-line producer
  (`engine.py:64,781,789`); its `_body` output reaches the frontend verbatim as
  `FeedLine.text` via `httpPlanner.mapLines`.
- `orchestration/engine.py::_condition_statuses` (`:731-762`) — sets
  `ConditionStatus.source = provider_short(fact.source)` (short) and
  `checked_at`; the structured half of each fact.
- `frontend/src/data/feedConditions.ts::foldLineValue` (`:139-148`) +
  `unclaimedLines` (`:158-162`) — the F4 merge the sweep found inert on live.
- `frontend/src/screens/ConditionStates.tsx` — the six-state row + compact-group
  renderer; `Detail.tsx` — the commitment view; `summary.ts` — the Character
  line; `Home.tsx` / `water.ts` — the string-hygiene sites.

**Does NOT include:**
- **No ranking change.** All of this is presentation only (Rule #2) — no engine
  sort, no Curator input, no confidence-floor change.
- **No new condition kind, no schema-format bump, no wire *field* removal** — S1
  *adds* structured `body`/`age` to the existing `FeedLine`; it does not delete
  `text` until the frontend reads the structured fields (staged, tests green at
  each step).
- **No re-chase of already-fixed findings** (sweep §4: F1, F2, F3/F9a, F6,
  F7-mileage). C1 is explicitly the *regrown* twin of F2 in a second file — in
  scope.
- **No streamflow vs-normal band** (green/elevated needs percentile data + its
  own honesty design — a later epic). B7 renders the *discharge already
  fetched*, nothing derived.

### Binding decisions

1. **One source identity for folding.** The fold must compare like-to-like.
   Match on the short provider name both sides can produce
   (`provider_short(line.source) === status.source`), or carry an explicit
   per-line `kind` on the wire. Do **not** "fix" it by widening the status
   source to the full label — that re-bloats the ledger row.
2. **Collapse-when-agree, expand-when-diverge.** The block renders **one**
   freshness stamp when all rows share an age ("Checked just now"); a per-row
   age appears **only** for a row whose age diverges from the block. Source
   stays per-row (it differs and carries info); age collapses.
3. **Relocate provenance, never drop it (Rule #1).** S1 moves source/age out of
   `text`; every fact still shows its source and a freshness stamp somewhere —
   the change is where it's stated (once, at true scope), not whether.
4. **Answer or disclose (Rule #1).** B7/B8: render the fetched reading, or flag
   the fact as `not-fetched`/`no_data` (CDP-02) — never a ✓-sourced line that
   answers nothing.
5. **No fabricated grammar.** Plurals resolve (`facility`/`facilities`), null
   sub-fields drop their clause rather than printing `None` or `str(dict)`.

---

## Stories

### S1 — Conditions block: each fact once (Lane A) · size M · anchor

**Given** a Detail page whose six conditions were fetched in one JIT batch
**When** the conditions block renders
**Then** each condition appears once, with one block-scope freshness stamp, and
no residual duplicate list.

**AC-1.1:** `summarize_fact` (`present.py:135-154`) emits `body` (value only),
`source` (full label), and `age` as **separate** `FeedLine` fields; `text` is
either derived from them or retired once the frontend reads the structured
fields. The wire-contract test (TS ⇄ EXPECTED ⇄ Pydantic) is updated in lockstep.
**AC-1.2:** `foldLineValue` (`feedConditions.ts:145`) matches on the shared
short-provider identity (binding decision 1); a test with a **full** line source
(`"NWS api.weather.gov · single authoritative source (…)"`) and a **short**
status source (`"NWS"`) asserts the fold now claims the line. This is the
regression test that would have caught A1.
**AC-1.3:** `Detail.tsx` renders one row per kind; `unclaimedLines` yields `[]`
for a normal live payload, so the residual `<ul>` (`:240-250`) does not render.
A `Detail.test.tsx` case asserts each condition's value + source appears exactly
once (no prose+row double, no `ConditionStates.tsx:203` in-row double).
**AC-1.4:** The block renders one stamp when all row ages agree
(`ConditionStates.tsx:184-195` → block-scope), and a per-row age only when a
row diverges (binding decision 2). Test: all-`just now` batch → one stamp; a
mixed batch (`just now` + `2h ago`) → the diverged row keeps its own age.
**AC-1.5:** A4 (`ConditionStates.tsx:128-131` compact group) and A5
(`_source_note` per-row descriptor, `Detail.tsx:296-298` Sources) state their
shared part once. `ConditionStates.test.tsx:182`'s verbatim assertion is updated.

### S2 — `present.py._body` answers and stops leaking (Lane B) · size S+M

**Given** any live fact value, including edge cases (`count ∈ {0,1}`, null
sub-fields)
**When** `_body` / the warning builders compose the line
**Then** no `(s)` plural, no `None`, no `str(dict)`, and water/permits answer a
hiker's question.

**AC-2.1 (guards):** pluralize on count — `facility`/`facilities` (`:77`, B1),
`detection`/`detections` (`:73` + `curator.py:229`, B2),
`alert`/`alerts` (`:78`, B3); drop the parenthetical when its value is falsy —
`AQI {n}` without `(None)` (`:71`, B4), unit defaults to `F` and the "forecast"
placeholder is dropped for a temp-only reading (`:69`, B5); `park =
value.get("park") or "the nearest park"` (truthy guard, B3), and guard the null
`title` at `curator.py:254` (B3 sibling); `_body`'s `str(value)` fallback
(`:63`,`:86`, B6) logs at the boundary and emits a neutral placeholder.
**AC-2.2 (water answers, B7):** `_body("water", …)` renders the fetched
`latest_discharge_cfs` (`usgs_water.py:144`) — e.g. `~12 cfs at Pass Run gauge`,
gauge name title-cased and truncated to the recognizable part, with
distance-to-gauge as the honest hedge when far; never the bare ALL-CAPS name,
never `None`.
**AC-2.3 (permits answer, B8):** `_body("permits", …)` answers the permit
question, or the permits fact is flagged `not-fetched` for the permit
disposition (CDP-02) rather than counting RIDB facilities as if it answered.
**AC-2.4:** `tests/test_present_edgecases.py` feeds `count ∈ {0,1,2}` and null
sub-fields through every `_body` and warning branch; asserts no `(s)`, `None`,
or dict-repr on the wire (the §6 process-net guard, delivered here).

### S3 — Character line honesty (Lane C) · size S

**Given** a verified live "go" verdict derived from a `"Showers And
Thunderstorms Likely"` reading
**When** the Character line renders on Detail
**Then** it does not append `— clear today`.

**AC-3.1:** `clearConditionTail` (`summary.ts:68-70`) is removed (the verdict
owns the go/no-go claim) or gated on an actual checked-clear disposition rather
than any `tone==='go'`. `summary.test.ts` gains the stormy-reading case
(`tone:'go'`, `provenance:'live'`, reading = storms) asserting **no** tail — the
case `:102` currently omits.
**AC-3.2:** `formatMiles` (`summary.ts:208-210`, C2) suppresses the mileage
clause (or hedges "under 0.1 mi") when the rounded value is `0`; a test with a
sub-0.05-mi length asserts no `0-mile` subject.

### S4 — String-hygiene guards (Lane D) · size S

**Given** a missing origin, empty reasons, unparseable timestamp, or empty water
source array
**When** the affected string renders
**Then** no dangling `· ` / `— `, no leading space, no `time unknown` token.

**AC-4.1:** `Home.tsx:55-56` (D1) builds its context sentence from an array and
`.filter(Boolean).join(' · ')` (the `RecommendationCard.tsx:62` pattern); tests
cover missing origin and empty region.
**AC-4.2:** `age.ts`'s `time unknown` (D2) is treated as "no stamp" by its
callers (`httpPlanner.ts:119/210`) — the age segment is omitted, not rendered.
**AC-4.3:** `Home.tsx:559` (D3) appends `— {causes}` only when `causes.length >
0`; `water.ts:64/77` (D4) treats an empty `sources` array as `none-nearby`
before composing the headline.

### S5 — Map chrome pointer-gate (Lane E) · size XS

**AC-5.1:** `TerrainMap.tsx:140-142` gates the `⌘ + scroll` hint on a
coarse-pointer / `hover: none` media query (hidden on touch); MapLibre's
cooperative-gestures already shows the two-finger hint there. A test or story
asserts the hint is absent under a coarse-pointer match.

### S6 — Process net (repetition + generated-string guards) · size S

**AC-6.1:** A repetition snapshot test over assembled Detail + feed that fails
if any token repeats > 3× on one surface (the `just now` ×11 would trip it).
**AC-6.2:** The `_body` plural/`None`/dict guard test (AC-2.4) exists and is
wired into `make check`.
**AC-6.3:** `docs/research/glm-microcopy-audit-2026-07.md`'s method note (or the
review rubric) records that computed strings are out of a literal grep's scope
and points at the generator inventory (sweep §5) as the walk-list.

---

## Definition of Done
- [x] All ACs covered by at least one passing test; the A1 fold-regression
      (AC-1.2) and the `_body` guard (AC-2.4) are falsifying (red if the guard
      is reverted).
- [x] `make check` green; frontend `npm test` + `npm run test:a11y` green;
      condition-state goldens updated intentionally, not silently.
- [x] Rule #1 preserved: every fact still shows source + a freshness stamp
      (relocated, never dropped) — asserted, not assumed.
- [x] Targeted self-review agent run; CRITICALs fixed, MODERATE+ documented.
- [x] Epic row added to `docs/epics/README.md`; `scripts/gen_epic_index.py` run;
      status flipped `DEFINED → IN_PROGRESS → REVIEW` (→ `DONE ✅` on merge).
- [x] Committed and pushed on `claude/just-now-overuse-87c0q2`.

---

## Review outcome (2026-07-15)

Targeted self-review over `git diff origin/main..HEAD`. **No CRITICALs.** Clean:
source-or-silence preserved through the S1 wire split (`body`/`source`/`age`
relocated, never dropped); stamp-collapse correct across all-agree / all-diverge
/ mixed / single / empty; every `observedAgo`/`checkedAgo` render site guarded;
the merge with main's managed-auth (Epic 043) is type-clean (the new
`tsc --noEmit` gate stage is load-bearing here — vitest/esbuild does not
type-check); the AC-1.2 fold-regression and the S6 repetition snapshot are
verified non-vacuous (S6 confirmed red-on-revert).

**Follow-ups (documented, not blocking merge):**
- **MODERATE — permits/water disposition vs glyph.** `_body` now renders honest
  text (`Permit info not fetched — N nearby facilities`; `flow reading
  unavailable at {gauge}`), but `engine.py`'s `_is_coverage_gap` /
  `_is_checked_clear` never special-case permits or a sentinel discharge, so the
  row keeps the `present` disposition → `✓ … reported`. The text is honest, the
  glyph contradicts it — the epic's own class at the text/glyph boundary. S2 was
  scoped to `present.py`/`curator.py`; the real fix is a `permits`/no-reading
  branch in `engine.py`'s CDP-02 disposition, which touches the six-state goldens
  and is deferred to its own change.
- **LOW —** `foldLineValue` matches by short-provider only (safe for today's six
  distinct providers; a future kind sharing a prefix would mis-route — worth a
  guard comment); two air-kind test fixtures use `source: 'AirNow'` vs the real
  `'EPA AirNow'` (still folds; fidelity nit); `sharedAmong` lacks a dedicated
  single/empty unit test; the S5 `matchMedia` stubs lack an explicit
  `vi.unstubAllGlobals()` (harmless — last block in the file).
