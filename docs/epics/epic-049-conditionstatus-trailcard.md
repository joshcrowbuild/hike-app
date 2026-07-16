# Epic 049 — ConditionStatus engine + TrailCard restyle (WP-2)

**Status:** DONE ✅
**Phase:** 1
**Spec refs:** `docs/design-system/spec-v0.2.md` §II.B · Contract B (`ConditionTier`)

---

## Capability statement
The feed card leads with the trail name, shows mono decision-metrics, stays **silent when conditions are clear**, and surfaces a single tiered status line only when there is something to act on — driven by one shared ConditionStatus engine that maps the six coverage states to the four signal tiers.

## Architectural context
Builds on: Epic 047 (tokens + Contract B), Epic 048 (Text / Button / MetricRow).
Adds: `frontend/src/screens/ConditionStatus.tsx` (`toTier` mapper + `ConditionStatusLine` + `summarizeConditions`); restyles `RecommendationCard.tsx` (name-leads, silence-when-clean, one action zone, per-card weather removed), `cardParts.tsx`, `ConditionStates.tsx`.
Does NOT include: the Detail screen (Epic 050).

## Stories
### S1 — ConditionStatus engine
**AC-1.1:** `toTier` maps `no-hazard → clear`, `present`+closures/permits `→ blocked`, `present`+other `→ headsUp`, the rest `→ unknown`.
**AC-1.2:** `ConditionStatusLine` renders nothing for `clear` (Law 1).
**AC-1.3:** `summarizeConditions` returns the most-severe tier plus a conclusion.

### S2 — TrailCard restyle
**AC-2.1:** Name leads; metrics via `MetricRow` (mono, named-missing).
**AC-2.2:** Status line renders only when tier ≠ `clear`.
**AC-2.3:** One action zone; the whole card opens Detail on tap.

## Definition of Done
- [x] `build` + `test:a11y` green; feed card verified against the mock.
- [x] Shipped via the combined `epic-049-050` assembly PR (delivered by a Gemini/Antigravity agent; extracted and re-integrated cleanly off `main` by the PO merge desk).

## Known follow-ups (tracked for Epic 054 assembly close-out)
- **Test-coverage regression:** the delivering agent thinned `RecommendationCard.test.tsx` (~400 lines removed). New behavioral tests must be restored — see the assembly close-out.
