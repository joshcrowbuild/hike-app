# Epic 003 — Context Assembly in engine.plan()

**Status:** IN_PROGRESS  
**Phase:** 1 (Personal Intelligence)  
**Spec refs:** Stage 5 §4 (retrieval / context assembly) · decision-log §30

---

## Capability statement

When generating a plan for a logged-in user, the engine assembles a compact personal-context
block from active Beliefs and recent Episodes, and injects it into the Curator's taste-ranking
call — enabling capability-aware, history-aware recommendations without ever passing raw
biometric data or provisional beliefs to a model.

## Architectural context

**Builds on:** Epic 001 (Beliefs exist), Stage 5 schema (PhysicalProfile, Belief, Episode)  
**Enables:** Epic 006 (Novelty filter — uses `been_on` beliefs from here), Stage 7 eval
(memory-on vs. memory-off comparison requires this to exist)  
**Does NOT include:** watch-data readiness filter (Epic 007), preference belief promotion
(Epic 002), the full Novelty filter logic (Epic 006)

---

## Stories

### S1 — Fetch active beliefs for the viewer

**Given** a viewer with `member_id` in the graph  
**When** context assembly runs at query time  
**Then** up to 20 `Belief` nodes are fetched, ordered by recency, with decayed confidence
computed in Python (not Cypher — per Stage 5 §3)

**AC-1.1:** Only beliefs with `decayed_confidence(b) > CONFIDENCE_FLOOR (0.4)` are included  
**AC-1.2:** Provisional beliefs (`corroboration_n < 3`, `confidence = 0.3`) are excluded (they are below the floor after decay)  
**AC-1.3:** The query filters `b.owner_id = $viewer_id` (Rule #4 — no cross-user belief leakage)  
**AC-1.4:** At most 20 beliefs are returned (cap per Stage 5 §4)  
**AC-1.5:** If no active beliefs exist, an empty list is returned — `plan()` does not crash

### S2 — Fetch PhysicalProfile capability summary

**Given** a viewer with a `PhysicalProfile` node  
**When** context assembly runs  
**Then** the profile's pace, max_distance, max_ascent, and episode_count are returned

**AC-2.1:** Profile is fetched with `owner_id = $viewer_id` (Rule #4)  
**AC-2.2:** If no PhysicalProfile exists (first-time user), returns `None` — context assembly degrades gracefully  
**AC-2.3:** Raw HR time-series, VO2max, or watch-vendor fields are never read here

### S3 — Fetch relevant episodes for candidates

**Given** a set of candidate `canonical_id`s from Scout  
**When** context assembly runs  
**Then** episodes linked to those trails (or their area) in the last 18 months are returned

**AC-3.1:** Only episodes where `(p:Person)-[:DID]->(e:Episode)-[:ON]->(t:CanonicalTrail)` and `t.canonical_id IN $candidate_ids` are included  
**AC-3.2:** Episodes are capped to last 18 months (`e.date > date() - duration('P18M')`)  
**AC-3.3:** At most 10 episodes are returned  
**AC-3.4:** Episodes are owner-scoped (`e.owner_id = $viewer_id`)  
**AC-3.5:** If no prior episodes exist, returns `[]` — no crash, no hallucinated history

### S4 — Assemble compact context string

**Given** beliefs, profile, and relevant episodes  
**When** the context block is assembled  
**Then** a compact, structured string is produced ready for injection into the judge prompt

**AC-4.1:** The context block follows the format from Stage 5 §4:
```
[PERSONAL CONTEXT — private, not for disclosure]
Capability: pace ~{pace} min/km on moderate grade, max {max_dist}km, max {max_asc}m ascent.
Preferences (inferred, 3+ episodes): {preference_beliefs}
Prior visits: {trail_name} visited {date}.
[END PERSONAL CONTEXT]
```
**AC-4.2:** If all sections are empty (no profile, no beliefs, no episodes), the context block is an empty string — `plan()` proceeds without personal context  
**AC-4.3:** Raw biometric values (HR time series, VO2max, sleep data) are NEVER present in the context string  
**AC-4.4:** `stated` beliefs appear as facts; `inferred` beliefs appear as "inferred from past hikes"  
**AC-4.5:** The context string length is capped at 500 characters (prevent prompt bloat)

### S5 — Inject context into Curator taste-ranking call

**Given** a non-empty personal context string  
**When** `rank_ids()` is called in `engine.plan()`  
**Then** the context string is passed as the `profile` parameter to `rank_ids()`

**AC-5.1:** `rank_ids()` receives the assembled context as `profile` when it's non-empty  
**AC-5.2:** `rank_ids()` receives `profile=None` when context is empty (anonymous user or no data) — same behaviour as today  
**AC-5.3:** The context is injected AFTER guardrail filtering — no personal context is used to decide whether a trail is safe  
**AC-5.4:** The context is assembled once per `plan()` call and passed to a single `rank_ids()` call — not once per candidate

### S6 — Anonymous path is unaffected

**Given** `viewer_id = "anonymous"` (or any viewer with no graph nodes)  
**When** `plan()` is called  
**Then** context assembly returns empty context and `plan()` proceeds identically to today

**AC-6.1:** No Belief/PhysicalProfile/Episode queries fail with a 404 or raise exceptions for an unknown viewer_id  
**AC-6.2:** The returned feed is identical in structure whether or not personal context exists  
**AC-6.3:** The `"anonymous"` viewer never receives another user's context

---

## Definition of Done

- [ ] All ACs covered by at least one passing test
- [ ] `make check` green
- [ ] Targeted review: verify Rule #4 on all three fetch queries, no raw biometrics in context, anonymous path clean
- [ ] End-to-end: `plan()` with a seeded Josh profile produces a context-enriched Curator call
- [ ] Committed atomically: context fetcher separate from engine wiring separate from tests
- [ ] Pushed + epic status updated to DONE ✅

---

## Implementation notes

**New module:** `orchestration/context_assembly.py`  
Key functions:
- `fetch_beliefs(viewer_id, session) -> list[dict]` — Cypher query, Python-side decay filter
- `fetch_profile(viewer_id, session) -> dict | None`
- `fetch_relevant_episodes(viewer_id, candidate_ids, session) -> list[dict]`
- `assemble_context(beliefs, profile, episodes) -> str` — pure function, testable

**Engine wiring** in `engine.plan()`:
```python
# After Scout, before rank_plan
from orchestration.context_assembly import assemble_context, fetch_beliefs, fetch_profile, fetch_relevant_episodes
candidate_ids = [p.candidate.canonical_id for p in planned]
beliefs = fetch_beliefs(viewer_id, runtime.session)
profile = fetch_profile(viewer_id, runtime.session)
episodes = fetch_relevant_episodes(viewer_id, candidate_ids, runtime.session)
context = assemble_context(beliefs, profile, episodes)
if runtime.judge:
    planned = rank_plan(planned, runtime.judge[0], runtime.judge[1], profile=context or None)
```

**Decay helper:**
```python
from datetime import date

def decayed_confidence(belief: dict) -> float:
    if not belief.get("decays"):
        return belief.get("confidence", 0.0)
    age_days = (date.today() - belief["last_updated_at"].date()).days
    half_life = belief.get("decay_half_life_days", 90)
    return belief.get("confidence", 0.0) * (0.5 ** (age_days / half_life))
```
