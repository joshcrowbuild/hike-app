# Generated-String Integrity Sweep (2026-07)

*A codebase-wide sweep for one defect class, triggered by "just now" rendering
11× on the Dickey Ridge Detail screen. Not a screen review — a hunt for the
class that defect belongs to, across `frontend/src/` and the backend string
builders (`orchestration/present.py`, `adapters/`, `curator.py`, `engine.py`).
Findings are grouped into the fix-surface lanes that became Epic 046.*

**Last verified:** 2026-07-15 · **Owner:** PO (point-in-time sweep) ·
**Status:** ACTIVE (findings → Epic 046)

> Companion to `ux-review-conditions-2026-07.md` (the 2026-07-12 screen review).
> That review is ~40% shipped; this sweep verifies against **current code**, not
> the review, and only reports what is still live. The already-fixed list in §4
> records what NOT to re-chase.

---

## 1. The defect class

A per-atom rule, primitive, or formatter that is **individually correct but
wrong in the whole** — either:
- **repetition** — the same token/fact/source/stamp/hedge rendered N times when
  it carries information once (or only when it differs across items), or
- **degenerate output** — a formatter that emits broken text on an edge input
  (`1 nearby facilities`, `AQI 45 (None)`, `str(dict)`, a dangling `· `).

"just now" is the exemplar: `relativeAge()` (`age.ts`) and `_age()`
(`present.py`) are both correct — sub-minute *is* "just now" — but when every
fact in a JIT batch shares one fetch instant, every stamp collapses to the same
string and the signal becomes noise.

**Why the class evades review — three structural blind spots:**
1. **Generated, not written.** These strings are *computed at runtime*, so a
   literal-grep microcopy audit (which is how `glm-microcopy-audit-2026-07.md`
   found `we learn` / `holds under this frame`) structurally cannot see them.
   Every finding in this sweep is invisible to that method.
2. **Individually correct.** Each primitive is a clean, unit-tested honesty
   function. A component/code review of `relativeAge` sees a virtue; nobody's
   job was to ask what happens when 11 callers hit it in the same second — the
   noise is emergent across callers and has no single owner.
3. **The invariant camouflages its own overuse.** Rule #1 puts `source · stamp`
   on every fact, so a reviewer's eye reads `· NWS · just now` as *compliance*
   (✅ provenance) and stops. We trained ourselves to verify the stamp is
   present, never that the eleventh one still earns its place.

## 2. Method

Three parallel audits, each verified against current code on 2026-07-15:
- **Repetition / aggregate-collapse** — every surface where a shared token
  renders per-item.
- **Generated-string inventory + degenerate outputs** — the full map of runtime
  string generators (the blind-spot net) plus their edge-case failures.
- **Weird conditions** — fallback/default logic that asserts unverified state,
  contradicts a sourced fact, or emits a degenerate label.

The PO hand-verified the anchor (Lane A, at `feedConditions.ts:145` ×
`present.py:147` × `engine.py:737`) and the honesty regression (Lane C, at
`summary.ts:70`). Remaining findings are traced to `file:line` with a trigger;
each is re-verified in place at implementation.

## 3. Findings by lane

### Lane A — Conditions block: each fact once (the "just now" lane)

Root cause is **A3**: the backend welds source + age into each line's display
text, so no surface downstream can state them once.

- **A1 · merge inert on live data.** `feedConditions.ts:145` folds a line into
  its per-kind row only when `line.source === status.source`. But
  `engine.py:737` sets the status source to the **short** name
  (`provider_short(fact.source)` → `"NWS"`) while `present.py:147` sets the line
  source to the **full** label (`"NWS api.weather.gov · single authoritative
  source (NWS LWX 56,65)"`). Full ≠ short → the fold **never matches on live**,
  so `Detail.tsx:236` falls through to the residual `<ul>` (`:240-250`) and
  every condition renders **twice** — once as a table row, once as prose. Unit
  tests pass only because their fixtures use short line sources (`'NWS'`). This
  is `ux-review` F4, shipped-but-inert.
- **A2 · uniform stamp.** `ConditionStates.tsx:184-195` builds a per-row
  `· {source} · <Staleness>{checkedAgo}</Staleness>` for each of six rows; the
  source differs and carries info, the age is identical across the JIT batch.
  The pure collapse-when-agree case.
- **A3 · baked text (root).** `present.py:146` —
  `text = f"{hedge}{body} · {provider_short(fact.source)}, {_age(...)}"`. The
  same fact's `ConditionStatus` already carries `source` + `checked_at` as
  structured fields (`engine.py:744/752/759`), so provider+stamp exist twice on
  the wire. Because they're welded into a display string, no surface can relocate
  or collapse them — and fixing A1 naively resurfaces an in-row double
  (`value.text` ends `· NWS, just now`, then the row appends `· NWS · just now`
  at `ConditionStates.tsx:203`).
- **A4 · compact-group age repeat.** `ConditionStates.tsx:128-131` →
  `Fire (NASA · just now), Closures (NPS · just now)` — state stated once for
  the group, age repeated per kind. Renders on `RecommendationCard`'s compact
  block and the `ContextRibbon` (`FeedConditions.tsx:70`).
- **A5 · Sources descriptor repeat.** `_source_note` (`present.py:123-132`) +
  `:147` render `single authoritative source` on nearly every provider row of
  the Detail Sources section (`Detail.tsx:296-298`) — a posture true once for
  the whole section, printed per row (and the provider names' third appearance).

**Fix surface:** `summarize_fact` emits `body` / `source` / `age` as separate
fields; the frontend folds by the short-provider identity both sides share and
renders one block-scope stamp, expanding to a per-row age only where a row
diverges. A4/A5 are the same state-once move on the compact group and Sources.

### Lane B — `present.py._body` answers and stops leaking

Same backend file as Lane A. Two halves:

**Degenerate-output guards (mechanical):**
- **B1 · permits plural.** `present.py:77` — `f"{count} nearby facilities"` →
  `1 nearby facilities` (RIDB `count = len(facilities)`; single-facility
  trailheads are common); `0 nearby facilities` on empty.
- **B2 · fire plural.** `present.py:73` + the reliably-reached warning twin
  `curator.py:229` — `active-fire detection(s) nearby`: the `(s)` never resolves.
- **B3 · closures plural + `None`.** `present.py:78-80` — `alert(s)` plural, and
  `park = value.get("park", "nearest park")` returns `None` when the key is
  present-but-null (nps_alerts sets `"park": full_name`, `fullName` can be null)
  → `1 NPS closure/danger alert(s) — None`. Sibling: `curator.py:254` leaks
  `closure alert: None` when the alert `title` is null (park scope *is* guarded
  at `:249`; title is not).
- **B4 · air `None`.** `present.py:71` — `f"AQI {aqi} ({category})"` →
  `AQI 45 (None)` when AirNow omits `Category.Name` (`airnow.py:76`; `aqi`
  itself is guarded).
- **B5 · weather unit / placeholder.** `present.py:69` — `Sunny 72°` when
  `temperature_unit` is null; `forecast 72°F` (the literal word "forecast" as
  the sky) when `short_forecast` is null.
- **B6 · raw-dict leak.** `present.py:63` & `:86` — `str(value)` fallback
  renders a Python dict repr (`{'foo': 'bar'}`) for an unhandled `kind` or
  non-dict value. Fail-loud + neutral placeholder instead.

**Answering (higher value — `ux-review` F5, still unremediated):**
- **B7 · water dumps a gauge address, not a reading.** `present.py:74-75` —
  `f"nearest gauge: {monitoring_location or site_id}"` renders an ALL-CAPS
  station name that wraps two lines at 390px and **discards** the fetched
  `latest_discharge_cfs` (available at `usgs_water.py:144`). Null name+id →
  `nearest gauge: None`. Render `~{cfs:.0f} cfs at {TitleCased, truncated} ·
  gauge N mi away`.
- **B8 · permits count facilities instead of answering.** `present.py:77`
  answers "how many RIDB facilities are nearby", not "do I need a permit".
  Answer the permit question or flag `not-fetched` for the permit fact (CDP-02).

### Lane C — Character line honesty (`summary.ts`)

- **C1 · `— clear today` regrowth (the one honesty regression).**
  `summary.ts:68-70` (`clearConditionTail`, applied `:56`, rendered on Detail
  `:143-148`) appends `— clear today` whenever `deriveVerdict` returns
  `tone:'go', provenance:'live'` — which it does for a verified NWS
  `"Showers And Thunderstorms Likely 77°F"` with no active alert. So Character
  renders `"…climbing 860 ft — clear today."` directly above a sourced
  `"✓ Showers And Thunderstorms Likely 77°F · NWS, just now."` This is the F2
  `'conditions look clear'` defect — fixed in `verdict.ts` — grown back in a
  second file. The verdict already owns the go/no-go claim; drop the tail. The
  test at `summary.test.ts:102` only exercises a `"Sunny"` reading, so the
  stormy case passes CI uncaught.
- **C2 · `0-mile` subject.** `summary.ts:208-210` (`formatMiles`, consumed
  `:47`) rounds a sub-0.05-mi length to `0` → `"A flat 0-mile loop."` Floor the
  mileage clause (the `resolveMiles` SSOT fix reconciled the two *numbers*, but
  the degenerate label survived).

### Lane D — String-hygiene guards (frontend, same shape)

All fixed by building segments in an array and `.filter(Boolean).join(' · ')` —
the pattern `RecommendationCard.tsx:62` already uses correctly.

- **D1 · context sentence dangling separator.** `Home.tsx:55-56` —
  `` `${when} · ${region} · from ${origin}` `` with `origin = … ?? ''` (`:54`)
  and `region` from `resolveRegionLabel`, which can return `''`
  (`resolveRegion.ts:48`). An origin not in the fetched catalog (the case
  `httpPlanner.ts:53 FALLBACK_COORDS` exists for) → `Weekend morning ·
  Shenandoah · from ` (dangling); both empty → `Weekend morning ·  · from …`
  (doubled ` · `).
- **D2 · `time unknown` rendered as a stamp.** `age.ts:9` returns the internal
  token `time unknown` for an unparseable iso; `httpPlanner.ts:119`
  (`observedAgo`) and `:210` (`checkedAgo`) pass it through unguarded → it
  renders inside `<Staleness>` and survives the compact `.filter(Boolean)` join
  (`ConditionStates.tsx:129`, it's truthy) → `NWS · time unknown`. Callers
  should treat it as "no stamp" (omit the age segment).
- **D3 · held-back dangling em-dash.** `Home.tsx:559` — `{count} — {causes}`
  with `causes` from `:555`; an item with empty `reasons` → `1 trail held back
  — `.
- **D4 · water empty headline.** `water.ts:64/77` — `summarizeWaterCounts`
  returns `''` for an empty array, prefixed unconditionally in the `sources`
  branch → ` within ~50 ft of the route` (leading space). Treat empty `sources`
  as `none-nearby` first.

### Lane E — Map chrome

- **E1 · `⌘ + scroll` hint on touch.** `TerrainMap.tsx:140-142` renders
  `Use ⌘ + scroll (Ctrl + scroll on Windows) to zoom the map.` gated on
  `supportsWebGL`, **not** pointer type — so it shows on the primary phone
  dogfood surface, which has no ⌘ and no scroll wheel. Gate on a coarse-pointer
  (`hover: none`) media query. (`ux-review` F8; a static literal, so greppable —
  the one finding here outside the generated-string blind spot.)

## 4. Already fixed — do NOT re-chase (verified in current code)

- **F1** card-vs-Detail verdict disagreement → `feedWarnings.ts` returns a
  suppression set; the verdict derives from the full `CardVM` on both surfaces
  (`Home.test.tsx:349`).
- **F2** `'conditions look clear'` default → `checkedDetail()` ("nothing flagged
  across N checks", 1-check singular guarded); `verdict.ts:41-54, 84-86`,
  `verdict.test.ts:74-78`. *(But see C1: the twin literal regrew in
  `summary.ts`.)*
- **F3 / F9a** region-scope verbatim repetition ×10 cards → `splitFeedConditions`
  hoists shared readings/dispositions into one `ContextRibbon`; cards suppress
  via `hoistedLineKeys` / `hoistedStateKeys`. (This works because it compares
  like-to-like — `lineKey` line↔line, `conditionStateKey` status↔status — unlike
  A1's fold, which compares line↔status across the two source representations.
  Same root data, opposite outcomes.)
- **F6** 14-decimal max-grade → `ElevationProfile.tsx:27` `pct.toFixed(1)`,
  applied to both the visible header (`:93`) and the sr-only summary (`:42-44`);
  `ElevationProfile.test.tsx:66`.
- **F7 (mileage half)** two length sources on one screen → `resolveMiles`
  (`summary.ts:137`) is the single geometry SSOT, consumed by both
  `DecisionFacts` (`cardParts.tsx:284`) and the Character line.

## 5. The generated-string inventory (the blind-spot net)

The full list of runtime user-facing string generators — the map a future audit
must walk, because a literal grep can't. Frontend: `age.ts:7 relativeAge`,
`duration.ts:16 formatEstimatedDuration`, `summary.ts` (`deriveSummary:29`,
`formatMiles:208`, `indefiniteArticle:218`, `clearConditionTail:68`,
`deriveDifficulty:109`), `verdict.ts` (`deriveVerdict:62`, `checkedDetail:50`),
`water.ts` (`waterTypeNoun:32`, `formatWaterDistance:42`, `summarizeWaterCounts:52`,
`waterHeadline:72`, `waterNote:81`, `waterMarkerLabel:98`),
`resolveRegion.ts:36`, `cardParts.tsx` (`formatDrive:256`, `formatTrail:257`,
`cardAccessibleName:175`, `DecisionFacts:282`, `DifficultyBadge:148`),
`ConditionStates.tsx` (`CompactGroup:126`, `StateBody:170`, `kindLabel/compactLabel:45/154`),
`ElevationProfile.tsx:22-27`, `Home.tsx` (`contextSentence:45`, stack-meta:250,
search-meta:427, `HeldBackNote:554`, `SetAsideList:565`), `TerrainMap.tsx:122/141/169`,
`Outcome.tsx:126-136`. Backend: `present.py` (`_age:37`, `provider_short:50`,
`_body:62`, `_origin:95`, `_source_note:123`, `summarize_fact:135`),
`curator.py:201-254`, `engine.py:358/713`, adapter disclosures
(`usgs_water.py:136`, `nps_alerts.py:135`). **Note:** no generator truncates
anywhere (B7's ALL-CAPS gauge name is the visible cost); title-casing appears
only at `waterMarkerLabel:100`.

## 6. Process net (why this shipped, and the cheap guards)

1. **Add a generated-string / rendered-DOM pass to the review rubric.** The
   microcopy audit greps literals; extend it to walk the assembled DOM (or the
   generator inventory in §5) so computed strings are in scope.
2. **A repetition snapshot test** on assembled Detail + feed that counts any
   token repeating > 3× (the "just now" ×11 would have tripped it).
3. **A plural/`None`-leak guard for the `_body` family** — a test or helper that
   feeds `count ∈ {0,1,2}` and null sub-fields through every `_body`/warning
   branch and asserts no `(s)`, no `None`, no `str(dict)` reaches the wire.

## 7. Batching → Epic 046

| Story | Lane | Fix surface | Size | Order |
|---|---|---|---|---|
| S1 | A | conditions block: `present.summarize_fact` seam + frontend fold/stamp-collapse | M | anchor |
| S2 | B | `present.py._body` guards + water/permits answering (+ `curator.py` twins) | S+M | after/with S1 (shared file) |
| S3 | C | `summary.ts`: drop `— clear today`, floor `0-mile` | S | parallel-safe |
| S4 | D | frontend string-hygiene guards (`.filter(Boolean)` family) | S | parallel-safe |
| S5 | E | `TerrainMap` pointer-gate the zoom hint | XS | parallel-safe |
| S6 | — | process net (rubric pass + repetition snapshot + `_body` guard test) | S | with S1/S2 |

**S1 and S3 carry the weight** — the core defect (plus a live double-render bug)
and the one honesty regression. S1 → S2 share `present.py` and should not run in
parallel; S3/S4/S5 touch disjoint files and are parallel-safe.
