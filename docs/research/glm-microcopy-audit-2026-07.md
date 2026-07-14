# GLM Microcopy & Voice Audit

**Date:** 2026-07
**Agent:** GLM
**Scope:** `frontend/src` literals against `docs/vision.md` guidelines.

## Audit Inventory

Ranked by severity: Honesty Violations, Tone Breaks, and Terminology Inconsistency.

| Severity | String | File:Line | Surface | When shown | Flag(s) | Proposed Exact Replacement |
|---|---|---|---|---|---|---|
| **Honesty** | `Conditions not checked — open to verify` | `frontend/src/screens/cardParts.tsx:309` | Card/Detail | `not-fetched` silence state | Asserts that opening Detail will verify the condition (a false promise since data is JIT but unfetched). | `Conditions not checked for this area` |
| **Honesty** | `Not checked yet` | `frontend/src/screens/cardParts.tsx:309` | Screen Reader | `not-fetched` sr-only announce | "yet" implies a future check is guaranteed, asserting more certainty than the absence of a check implies. | `Not checked` |
| **Honesty** | `... — carry what you need.` | `frontend/src/data/water.ts:75` | Detail | `none-nearby` water state | Tool commands the user rather than advising them ("the tool scores, the human decides"). | `No mapped water within {dist} of {basis}.` |
| **Tone** | `Sign in to log your hikes and keep what we learn.` | `frontend/src/screens/Outcome.tsx:104` | Outcome | Viewing outcome for mock/anonymous episode | "we learn" anthropomorphizes the app and implies the app is studying the user, violating "private-by-default personal overlay". | `Sign in to log your trips and sharpen your future answers.` |
| **Tone** | `How was it? →` | `frontend/src/screens/Home.tsx:120` | Home | Pending outcome nod button | Conversational, engagement-y push to log, with a directional arrow. | `Log outcome` |
| **Tone** | `Nothing holds under this frame right now.` | `frontend/src/screens/Home.tsx:361` | Home | Empty state | "holds under this frame" is robotic and exposes internal system terminology ("frame" and "holds"). | `Nothing matches your search right now.` |
| **Tone** | `One option really holds under this frame.` | `frontend/src/screens/Home.tsx:385` | Home | Sparse state (1 option) | Same robotic "holds under this frame" construction. | `One option matches your search.` |
| **Tone** | `Hide what today can’t support. Off unless you turn it on.` | `frontend/src/screens/Tuning.tsx:312` | Tuning | Readiness toggle description | "can't support" asserts absolute failure, violating readiness as a "hedged, capability-only effort floor". | `Hide options that exceed today's readiness. Off unless you turn it on.` |
| **Consistency** | `After the hike` | `frontend/src/screens/Outcome.tsx:97` | Outcome | Header for outcome | Drifts between "hike" and "trip". `vision.md` refers to the event as a "trip", while physical route is "trail". | `After the trip` |
| **Consistency** | `Sample hike — these measured facts...` | `frontend/src/screens/Outcome.tsx:121` | Outcome | Mock episode warning | "hike" instead of standard "trip". | `Sample trip — these measured facts...` |
| **Consistency** | `You hiked {pending.trailName}` | `frontend/src/screens/Home.tsx:119` | Home / Outcome | Pending outcome / Outcome header | Uses "hiked" when standardizing on "trip" would prefer "took this trip". | `You took this trip: {pending.trailName}` |
