# The Frame & Conditions wave — decision spec (v0.2 addendum)

**Status:** BUILDING (overnight wave, 2026-07-16) · **Owner:** PO (interview of 2026-07-15/16, Q1–Q20 all resolved with Josh)
**Supersedes:** the feed's `ContextSentence` ribbon + `ConditionStates` compact band, and the Detail `EvidencePanel` always-visible sourced list.
**Extends:** `spec-v0.2.md` (all six laws + the 4-tier signal remain in force).

This document is the shared-understanding record of a full decision interview,
and the build spec for Epics 054–057. Where this doc and a mock disagree, the
mock wins for *look*, this doc wins for *behavior*.

---

## 1. The decision ledger (what Josh decided, verbatim intent)

| # | Decision |
|---|----------|
| Q1 | **Warnings are the only actionable signal.** The curator's hazard calls drive both alarm color and the WarningBlock. Conditions are quiet readings. |
| Q2 | **Feed cards are silent on conditions.** No per-card condition summary/status line. Cards keep their WarningBlock (Q1). |
| Q3 | Conditions render as a **scannable glyph strip** (glyph + value chips), never prose, never "we checked N sources". |
| Q4 | The strip's home is the **area level** — inside the "This feed" card, stated once. (Trail-specific conditions live on Detail.) |
| Q5 | **Chips tint when a warning owns their kind** — the strip is the scan layer, the WarningBlock the sentence. |
| Q6 | Detail provenance = **tap a chip to reveal** one quiet receipt line below the strip (source · age · confidence). Default collapsed. No popover/caret bubble. |
| Q7 | **Two alarm levels**: amber `headsUp` (passable) vs terracotta `blocked` (barrier). Backend grades severity; frontend renders it. |
| Q8 | Degraded personalization → **dismissible banner with a retry** (SystemBanner kind `personalization-degraded`). |
| Q9 | Strip loads as **skeleton chips**; ~12 s soft budget, then dashed + quiet retry; late data still fills. No more 60 s "Checking current conditions…". |
| Q10 | **Conditions cache for the whole session; refresh only on demand.** No refetch on navigation. Staleness horizons drive *display* (dashed + age), not refetch. |
| Q11 | Also in scope this wave: feed chrome polish · curation/adjust affordance · metric-line density · header avatar. Test restoration rides as debt. |
| Q12–13 | The frame is a **boarding-pass card ("This feed")** that also holds the area conditions, temporally aligned to the frame's *when*. Prose sentence: killed. |
| Q14–15 | **Slate `#365479` = the interactive color.** Always-on affordance (soft fill / slate text), **no underline, no hover-dependence**, thumb-sized targets. Terracotta/amber stay hazards-only. |
| Q16–17 | Facets render as the **type-scale stack**: From (headline) › When (subline) › Party·Effort (small filled chips). Hierarchy by size, all tappable. |
| Q18 | **Forecast-alignment ships this wave.** Weather forecasts to the frame's day (NWS multi-day periods — already fetched, currently discarded); target-date plumbing engine → verifier → adapter. |
| Q19 | **Recent weather + mud, all in this wave.** Collapsed "Past 3 days" rain reveal + a hedged mud inference (amber, dashed border, tagged "inferred", evidence + source, always "may"). Rule calibration folded into the wave's tests. |
| Q20 | **Claude-only fleet.** Isolated worktrees, frozen contracts, single merge desk. No Gemini this wave. |

**Ground truth that validated the design** (verified in code, 2026-07-16):
- NWS adapter already fetches the multi-day forecast doc and reads only `periods[0]` (`orchestration/adapters/nws.py`). Gridpoint identity already captured.
- `when` plumbing exists in type signatures (`base.py::LiveAdapter.probe`, TTLCache keys) but is never populated by any caller.
- Weather is the **only** forecastable kind. AQI / fire / streamflow / closures are current-only upstream — so the forecast/current zone split is the literal truth of the sources, not a style choice.
- Staleness horizons are already per-kind in `orchestration/engine.py::_STALE_HORIZON_S` (weather/air/fire/closures 2 h · water 1 h · permits 48 h). They become the *display* signal.
- Today nothing caches conditions: every feed re-entry re-POSTs `/plan/conditions`; the localStorage cache strips conditions on read; Detail water refetches every open.

## 2. Mocks of record (committed, `docs/design-system/mocks/`)

| Mock | What it locks |
|---|---|
| `frame-card-typescale.html` | The facet stack (**variant 01** is the pick), slate tokens, tap targets. |
| `frame-card-conditions-zones.html` | The merged card: forecast zone + day toggle + right-now zone + caveat. |
| `frame-card-recent-weather-mud.html` | The collapsed "Past 3 days" reveal + the hedged mud read. |
| `conditions-strip-states.html` | Chip states: fresh · stale (dashed + age) · unavailable (dashed —). |
| `detail-provenance-tap.html` | Detail strip + tinted hazard chip; **the popover is superseded** — build the quiet receipt-line-below-strip pattern instead (Q6 note). |

## 3. The "This feed" card — component spec

One card at the top of the feed, replacing `ContextSentence` + the compact
`ConditionStates` band. Regions, top to bottom:

1. **Header** — overline `This feed` (the one permitted uppercase role,
   `Text` overline). No Edit button — the facets are the controls.
2. **Facet stack** (slate = interactive, all affordances at rest):
   - `From` label (10px muted) + **origin as headline** (slate, ~21–23px,
     chevron `›`) → opens the existing `PanelSheet` for origin.
   - **When as subline** (slate, ~15px, chevron) → PanelSheet for when.
   - **Party · Effort as small filled slate chips** (caret glyph) →
     their PanelSheets. Anonymous viewers: these two are hidden (existing
     world-facet filter); the free-text "describe this feed" stays in the
     Adjust sheet, reachable from the panels' hub as today.
3. **Forecast zone** (border-top): header `‹Day› forecast` (bold, sentence
   case) + **day toggle** (segmented: `Today` + the frame's candidate days).
   Chips: high temp, precip %, optional short condition. Data =
   `regionConditions.forecast`. Toggle switches between days **without
   refetch** (all days arrive in one payload). Zone label reads `Today`
   with a `now` tag when the selected day is today.
   - Forecast absent (null / not yet fetched): skeleton chips while pending,
     then one muted line `Forecast unavailable right now` on degrade.
4. **Past 3 days reveal** (inside the forecast zone, collapsed by default):
   a 12px disclosure `› Past 3 days`. Open: per-day rain row (wet days in
   `forecast.fg`, dry muted) + **the mud read** when present: amber,
   dashed border, `inferred` tag, statement + evidence + source
   (`Trails may be muddy · 1.2" of rain in the last 48h · from NWS
   observations`). Hidden entirely when `recentPrecip` is null
   (degrade-and-disclose: no data → no reveal, never a fabricated row).
5. **Right-now zone** (border-top): header `Right now` + muted caveat
   `· may change by ‹day›` (only when the frame targets a future day) +
   overline tag `current` + a quiet **Refresh** action (calls `reload()` —
   the one on-demand refetch, Q10). Chips = the region-shared current
   readings (existing `splitFeedConditions` hoisting) rendered as strip
   chips.

**Chip states** (one component, `ConditionChip`):
- `pending` — skeleton shimmer, muted placeholder.
- `fresh` — glyph + mono value, raised surface, hairline border.
- `stale` — transparent bg, **dashed** border, muted value, clock glyph +
  age text (gray — staleness is unknown-family, it spends no alarm color).
- `unavailable` — dashed border, italic muted `—`.
- **Tinted** — the kind carries a warning: `headsUp` → amber fg/bg;
  `blocked` → terracotta fg/bg (max severity wins). Q5/Q7.

**Type**: values mono (metrics rule), labels sans. Zone headers sentence
case. `This feed` / `current` / `forecast` tags = overline role only.

## 4. Feed cards & Detail

- **RecommendationCard**: remove the condition summary line
  (`ConditionStatusLine`) and any per-card condition chips — cards are
  silent on conditions (Q2). Keep name, metrics, WarningBlock (Q1),
  actions. Per-card warnings still render with severity tint.
- **Detail**: WarningBlock(s) up top (severity-tinted), then `Current
  conditions` strip of **this trail's** per-kind chips (same
  `ConditionChip`). **Tap a chip → one receipt line** directly below the
  strip (`AirNow · 2 min ago · single source`), swapping on each tap,
  collapsed by default (Q6). This replaces the always-visible sourced
  list. The trail's own recent/forecast data is NOT on Detail this wave —
  area-level lives in the This-feed card.

## 5. Wire schema (backend ⇄ frontend, pinned)

Backend (snake_case) — additions, all additive/optional:

```jsonc
// POST /plan and /plan/conditions responses
{
  "personalization_degraded": false,        // true when the judge fell back
  "warnings": [{ "...existing": "...", "severity": "heads_up" | "blocked" }],
  "region_conditions": {                    // null until phase-2 / when unavailable
    "forecast": {                           // null when NWS forecast unavailable
      "target_key": "sat",                  // which day the frame targets
      "days": [                             // Today first, then frame days
        { "key": "today", "label": "Today", "high_f": 88, "precip_pct": 0, "short": "Sunny" },
        { "key": "sat",   "label": "Sat",   "high_f": 68, "precip_pct": 20, "short": "Partly sunny" },
        { "key": "sun",   "label": "Sun",   "high_f": 71, "precip_pct": 10, "short": "Mostly sunny" }
      ],
      "source": "NWS", "fetched_at": "<iso>"
    },
    "recent_precip": {                      // null when observations unavailable
      "days": [ { "label": "Thu", "amount_in": 0.8 }, { "label": "Fri", "amount_in": 0.4 }, { "label": "Today", "amount_in": 0.0 } ],
      "total_48h_in": 1.2, "source": "NWS observations"
    },
    "mud": {                                // null when rule not met OR precip unknown
      "statement": "Trails may be muddy",
      "evidence": "1.2\" of rain in the last 48h",
      "source": "NWS observations", "provenance": "inferred"
    }
  }
}
```

Frontend VM mirror (camelCase) — already added to `vm.ts` in PR-0:
`WarningVM.severity?: 'headsUp' | 'blocked'`, `ForecastVM`/`ForecastDayVM`,
`RecentPrecipVM`, `MudVM`, `RegionConditionsVM`,
`FeedVM.regionConditions?`, `FeedVM.personalizationDegraded?`,
`ConditionsPatchVM.regionConditions?`, `ConditionsPatchVM.personalizationDegraded?`.

**Severity mapping (curator, backend truth):**
- closures (NPS Closure/Danger) → `blocked`
- NWS alert severity `Extreme` | `Severe` → `blocked`; `Moderate` | `Minor` | unknown → `heads_up`
- AQI ≥ 201 → `blocked`; 101–200 → `heads_up`
- fire hotspots present → `heads_up` · high streamflow → `heads_up` · default → `heads_up`

**Target-day derivation (backend, from the tuning `when` key,
region-local tz, default `America/New_York`, env `ADVENTURE_REGION_TZ`):**
- `tomorrowMorning` → days `[today, tomorrow]`, target `tomorrow`
- `weekendMorning` / `weekendAfternoon` → `[today, sat, sun]` of the *coming*
  weekend (if today is Sat/Sun, this weekend), target `sat` (or `sun` when
  Sat has passed)
- `fullDay` → `[today, sat, sun]`, target `today`
NWS period selection: match period start date + daytime flag; forecast doc
is already fetched — select, don't re-fetch.

**Mud rule (env-tunable, calibration-tested):**
`total precip last 48 h ≥ ADVENTURE_MUD_PRECIP_48H_IN (default 0.5)` →
mud block present. Statement always hedged ("may"), provenance always
`inferred`, evidence always quantified. Missing precip data → no mud block
(silence, never a guess). Calibration = unit tests over fixture scenarios +
a documented threshold rationale in the epic; a field eval is a follow-up.

## 6. Data-layer behavior (Epic 056)

- **Session cache**: composed feed (with conditions) reused across
  navigation for the whole session, keyed by scope + frame. Re-entering
  the feed does NOT re-POST `/plan/conditions`. `reload()` (the Refresh
  affordance + banner retry) forces phase-1 + phase-2 fresh.
- **Cold start**: localStorage stale-paint unchanged (conditions still
  neutralized on read — honest).
- **Phase-2 presentation budget**: chips render `pending` immediately;
  at ~12 s without resolution flip the surface to degraded (dashed
  `unavailable` + quiet `Couldn't reach current conditions · Retry`);
  the underlying fetch keeps its 60 s abort and late success still fills.
- **Detail**: `getCard` (deep link) + `GET /trail/{id}` water cached
  in-memory per session (key: id + scope). No refetch on re-open.
- **personalizationDegraded** → surfaced on FeedVM; the card lane renders
  the dismissible banner (retry = `reload()`).

## 7. Chrome & polish (Epic 057)

SAVED pill + trail count styling per the states mocks · quiet the
anonymous `Browsing` chip · header avatar (signed-in: initial-circle
opening the account/sign-out sheet; anonymous: `Sign in` text button) ·
metric-line density pass (mono, middot separators, weight/spacing per
mock) · remaining uppercase/sentence-case holdouts outside Epic-055 files.

## 8. Sequencing, fleet & budget

| Lane | Epic | Model | Scope guard |
|---|---|---|---|
| PR-0 (merge desk) | — | Fable (main loop) | this doc · mocks · tokens · vm/contracts · epics |
| Backend | 054 | Sonnet 5 | `orchestration/` · `api/` · `evals` fixtures. No frontend. |
| Card | 055 | Opus 4.8 | `frontend/src/screens/*` + mock engine + styles. No data-layer files. |
| Mechanics | 056 | Sonnet 5 | `frontend/src/data/*` only. **Never** `screens/` or `Home.tsx`. |
| Polish | 057 | Sonnet 5 (low) | launches after 055 merges (Home.tsx contention). |

Merge order: PR-0 → 054/055/056 as they land (single desk, targeted review
each, local-green before push) → 057 → live verify. CI budget: ≤6 PR runs
total; path-gating (#252) keeps cross-leg runs cheap; one push per PR.

**Tokens added (PR-0):** `color.slate.600 #365479` (+alpha 10/16),
`color.sky.600 #2f6d84` (+alpha 08); semantic `interactive.{fg,bg,bgPress}`
and `forecast.{fg,bg}`. Slate is *interactive-only*; it never encodes
condition state. Terracotta/amber remain hazard-only (Q14).
