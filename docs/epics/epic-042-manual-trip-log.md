# Epic 042 — Manual Trip Log (Learning-Loop Fallback)

**Status:** REVIEW  
**Phase:** C (Real Intake)  
**Spec refs:** GLM IA review (gemini-ia-flow-review-2026-07.md §6.1) · vision.md §3 (private outcome-learned intelligence) · CLAUDE.md Rule #6 (watch data is enrichment, never dependency)

---

## Capability statement

A user can manually record that they completed a saved trip, triggering the Outcome flow and feeding the belief-update loop — without any watch integration, health-kit permission, or external webhook.

## Problem

The entire learning loop (Outcome → belief_update → improved curation) is currently gated on a future Garmin/Apple Health webhook firing to say a hike was completed. If that integration isn't built for Day 1, or a user denies health-data permission, the engine can never trigger the Outcome screen and therefore **never learns**. The `Outcome.tsx` screen exists but has no manual entry point — it relies on a `pending nod` that can only appear after an external telemetry event.

Rule #6 states: "Watch data is enrichment, never a dependency. Every use degrades-and-discloses. Built watch-free first." The current Outcome flow violates this rule by having no watch-free path.

## Architectural context

**Builds on:** Epic 002 (Outcome endpoint — DONE), Epic 001 (belief pipeline — DONE), Epic 004 (device seam — DONE)  
**Enables:** The learning loop for users without watch integration; unblocks the "real intake" requirement from vision.md §27  
**Does NOT include:** Automated watch-triggered outcomes (Epic 004 owns that), history import (GPX/Strava — separate epic), or the Explicit Hypothesis UI (a follow-up once the engine can articulate what it learned)

---

## Stories

### S1 — "I did this" action on a saved trail

**Given** the user has saved a trail (via the Save button on Detail)  
**When** they view their saved trails or the Detail screen for a saved trail  
**Then** a "Log this trip" action is available

**AC-1.1:** The action appears only on saved trails (not on unsaved feed cards)  
**AC-1.2:** Tapping the action navigates to the Outcome screen with the trail pre-filled  
**AC-1.3:** If the trail has already been logged today, the action reads "Logged today" and is disabled (idempotency — no accidental double-logs)

### S2 — Create an Episode from manual log

**Given** the user taps "Log this trip"  
**When** no Episode exists for this trail + user + today  
**Then** an Episode is created with `source: "manual"` and today's date

**AC-2.1:** The Episode is created via the existing `upsert_episode` path (Epic 002)  
**AC-2.2:** `Episode.source` is set to `"manual"` (distinct from `"watch"` or `"import"`)  
**AC-2.3:** Measured fields (moving_time, pace) are `null` — they degrade-and-disclose, never fabricated  
**AC-2.4:** The Outcome screen renders without measured stats (the "Measured" block is hidden, not shown as zeros)

### S3 — Manual outcomes feed the belief pipeline

**Given** the user has completed the Outcome flow from a manual log  
**When** they rate the trip (Good/Okay/Rough)  
**Then** the outcome triggers the same belief_update pipeline as a watch-triggered outcome

**AC-3.1:** The belief pipeline treats `source: "manual"` identically to `source: "watch"` for preference beliefs  
**AC-3.2:** Capability beliefs are NOT updated from manual logs (no measured pace/HR data — Rule #6: "the watch is a good capability sensor, a poor preference sensor"; the manual path is even weaker)  
**AC-3.3:** The belief node carries `provenance: "manual_outcome"` so it's traceable

---

## Out of scope

- **Date picker** ("I hiked this last Tuesday"): v1 logs for today only. History import (GPX/Strava) handles backfill.
- **Explicit Hypothesis UI** ("Noted — you seemed to struggle with the ascent"): requires the engine to articulate its learning, which is a separate design problem. This epic just closes the loop; the transparency comes later.
- **Saved trails list/screen**: if no saved-trails surface exists yet, the "Log this trip" action lives on the Detail screen only.

---

## Build notes (decisions the spec left open)

- **"Logged today" source of truth.** No server read exists for a viewer's episodes yet, so the UI reads a viewer-scoped, device-local record written when a log succeeds (`frontend/src/data/tripLog.ts`). It survives a reload but not cleared site data or a second device. The real idempotency is server-side: the `client_episode_id` is derived from trail + local day, so a repeat resolves to the same Episode through the existing idempotent MERGE. Replace the local record with a server read when an episode-list endpoint lands.
- **Detail only.** No saved-trails surface exists, so the action lives on Detail, for a saved trail and a signed-in viewer. Anonymous viewers do not see it.
- **Capability suppression (AC-3.2).** `UpdateTask.source == "manual"` makes `update_beliefs` skip every capability write, whatever measured values the Episode carries; `process_episode` reads the source from the Episode.
- **Provenance (AC-3.3).** `write_outcome` reads the Episode's `source` with its ownership check and stamps the stated preference belief with `provenance: "manual_outcome"`. The preference check enqueued after a positive outcome is still the Epic 002 marker (no consumer writes a preference belief from it yet), so today the only preference belief a manual outcome can yield is the stated one.
