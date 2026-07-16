# Epic 050 — Detail + EvidencePanel + ContextSentence + MapControls (WP-3)

**Status:** DONE ✅
**Phase:** 1
**Spec refs:** `docs/design-system/spec-v0.2.md` §II.B · Contract B (`EvidenceItem`)

---

## Capability statement
The Detail screen leads with a conclusion and keeps the per-source evidence one tap away (progressive disclosure), the feed context becomes an editable sentence, and the map controls adopt the v0.2 primitives — so the commitment view shows the decision, not the verifier's worklog.

## Architectural context
Builds on: Epic 047 (tokens + Contract B), Epic 048 (Text / Button), Epic 049 (`ConditionStatus` engine).
Adds: `frontend/src/screens/EvidencePanel.tsx` (conclusion + `<details>` disclosure over the six-state coverage table, garbage-gauge string cleanup); restyles `Detail.tsx`, `FeedConditions.tsx` (context sentence), `map/MapControls.tsx`.
Does NOT include: the feed card (Epic 049).

## Stories
### S1 — EvidencePanel (progressive disclosure)
**AC-1.1:** Conclusion first; the full sourced table lives behind a `<details>` disclosure.
**AC-1.2:** `cleanEvidenceBody` rewrites the raw gauge/permit strings to human copy.

### S2 — Detail + context + map
**AC-2.1:** Detail hero + metrics on the v0.2 roles.
**AC-2.2:** Context becomes a sentence; the "Adjust" word retires.
**AC-2.3:** Map controls use `Button`/`Chip` primitives.

## Definition of Done
- [x] `build` + `test:a11y` green.
- [x] Shipped via the combined `epic-049-050` assembly PR.

## Known follow-ups (tracked for Epic 054 assembly close-out)
- **EvidencePanel conclusion is a stub:** `deriveConclusion` returns hardcoded copy ("Two things to know…") instead of delegating to `summarizeConditions(…, 'detail')`, so the disclosed count is imprecise on flagged trails. Rewire to the shared summarizer.
- **Test-coverage regression:** `Detail.test.tsx` / `Home.test.tsx` were thinned by the delivering agent; restore behavioral coverage.
