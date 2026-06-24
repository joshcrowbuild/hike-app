# Epic 001 — Belief Update Pipeline

**Status:** DONE ✅  
**Phase:** 1 (Personal Intelligence)  
**Spec refs:** Stage 6 §4.1–4.3 · Stage 5 §2–3 · decision-log §30–31

---

## Capability statement

After every Episode is ingested, the system automatically updates the owner's
`PhysicalProfile` and associated capability `Belief` nodes — enabling the Curator
to make capability-aware recommendations.

## Architectural context

**Builds on:** `ingestion/ingest_episode.py` (Episode creation), Stage 5 schema
(PhysicalProfile + Belief nodes already in Neo4j v0.2.0)

**Enables:** Context assembly (Epic 003), Curator capability filtering, memory eval

**Does NOT include:** heat_response inference (S6 §4.4 — NWS historical unconfirmed),
preference/taste belief promotion (requires N=3 outcome data — Epic 002)

---

## Stories

### S1 — Enqueue update after episode creation

**Given** an Episode is created via `create_episode()`  
**When** the function completes successfully  
**Then** an `UpdateTask` containing `episode_id`, `owner_id`, `distance_m`,
`ascent_m`, and `pace_on_grade` is placed on the belief update queue

**AC-1.1:** `create_episode()` calls `queue.enqueue()` exactly once per successful write  
**AC-1.2:** The enqueued task contains the correct `owner_id` and `episode_id`  
**AC-1.3:** If `pace_on_grade` is None (e.g., no moving_time), the task is still enqueued

### S2 — EWMA pace update

**Given** the owner has a `PhysicalProfile` with `pace_on_grade = P`  
**When** an `UpdateTask` with `pace_on_grade = N` is processed  
**Then** `PhysicalProfile.pace_on_grade` is set to `0.3 * N + 0.7 * P`

**AC-2.1:** EWMA formula: `alpha * new + (1 - alpha) * current` with `alpha = 0.3`  
**AC-2.2:** First episode (no existing profile): result equals `new_pace` directly  
**AC-2.3:** `PhysicalProfile.episode_count` is incremented by 1  
**AC-2.4:** If `task.pace_on_grade` is `None`, pace is not updated (but maxima still run)

### S3 — Maximum distance and ascent update

**Given** the owner's `PhysicalProfile` has `max_distance_m = D` and `max_ascent_m = A`  
**When** an `UpdateTask` is processed with `distance_m = D2` and `ascent_m = A2`  
**Then** `max_distance_m = max(D, D2)` and `max_ascent_m = max(A, A2)`

**AC-3.1:** A new maximum replaces the stored value  
**AC-3.2:** A value below current maximum does not overwrite  
**AC-3.3:** `None` values in the task do not overwrite existing maxima

### S4 — Pace capability Belief node

**Given** an `UpdateTask` is processed with a non-None `pace_on_grade`  
**When** the belief update runs  
**Then** a `Belief {key: "pace_on_grade_moderate", axis: "capability", type: "inferred"}`
node exists linked to the `Person` via `ABOUT` and to the `Episode` via `DERIVED_FROM`

**AC-4.1:** `Belief.corroboration_n` is 1 after first episode, incremented on each subsequent  
**AC-4.2:** `Belief.value` reflects the current EWMA pace (to 1 decimal)  
**AC-4.3:** `Belief` is linked to `Person` via `-[:ABOUT]->` edge  
**AC-4.4:** `Belief` is linked to `Episode` via `-[:DERIVED_FROM]->` edge

### S5 — Provisional confidence below promotion threshold

**Given** a `Belief` node with `corroboration_n < 3`  
**Then** `Belief.confidence < 0.4` (provisional — not injected into Curator context per S5-4)

**Given** a `Belief` node with `corroboration_n >= 3`  
**Then** `Belief.confidence >= 0.4` (crosses the floor — eligible for context assembly)

**AC-5.1:** `confidence = 0.3` when `corroboration_n = 1`  
**AC-5.2:** `confidence = 0.3` when `corroboration_n = 2`  
**AC-5.3:** `confidence = 0.7` when `corroboration_n = 3`  
**AC-5.4:** `Belief.type` is always `"inferred"` (never `"stated"` from automatic update)

---

## Definition of Done

- [x] All ACs covered by at least one passing test (named per process doc) — 23 tests
- [x] `make check` green (ruff + pytest) — 106 tests passing
- [x] Targeted self-review agent run — 4 MODERATE found, all fixed
- [x] `create_episode()` in `ingest_episode.py` wires the queue
- [x] Committed and pushed

**Review findings fixed:**
- Rule #4: DERIVED_FROM MATCH added `owner_id` constraint
- Idempotency: corroboration_n now derived from actual DERIVED_FROM edge count (not stored counter)
- ON CREATE SET missing from _update_maxima (first-episode maxima were silently dropped)
- CLI path now instantiates BeliefUpdateQueue and drains after create_episode
