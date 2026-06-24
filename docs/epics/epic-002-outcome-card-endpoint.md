# Epic 002 — Outcome Card Endpoint

**Status:** IN_PROGRESS  
**Phase:** 1 (Personal Intelligence)  
**Spec refs:** Stage 5 §1 (Outcome node) · decision-log §10 (sync UX) · decision-log §30

---

## Capability statement

After completing a hike, Josh can record a quick reflect-back (1–3 tap rating + optional
one-sentence delta) that is persisted as an `Outcome` node and triggers preference belief
promotion when enough corroborating outcomes accumulate.

## Architectural context

**Builds on:** Epic 001 (belief update queue), Stage 5 schema (Outcome, Belief nodes)  
**Enables:** Preference belief promotion (N=3 positive outcomes → `prefers_ridge_trail = true`),
Epic 003 context assembly (outcome quality signals feed the Curator)  
**Does NOT include:** UX (outcome card display is Stage 10), push notification trigger
(Stage 8), party detection toggle (out of scope for Phase 1 single-user)

---

## Stories

### S1 — Create an Outcome node

**Given** a `POST /episode/{id}/outcome` request with `{overall, delta_question, delta_answer, skipped}`  
**When** the episode exists and belongs to the authenticated viewer  
**Then** an `Outcome` node is created and linked to the Episode via `HAS_OUTCOME`

**AC-1.1:** `Outcome.episode_id` matches the path parameter `{id}`  
**AC-1.2:** `Outcome.owner_id` is set to the viewer's `member_id` — never inferred from request body  
**AC-1.3:** `Outcome.overall` is one of `{1, 2, 3}` or `None` when `skipped=true`  
**AC-1.4:** The endpoint returns 404 if the episode does not exist for the viewer (Rule #4 — no cross-user exposure)  
**AC-1.5:** The endpoint is idempotent: a second POST for the same episode updates `updated_at` only; it does not create a second `Outcome` node (MERGE keyed on `episode_id`)

### S2 — Wire Outcome to Episode

**Given** an Outcome is created  
**Then** `(episode)-[:HAS_OUTCOME]->(outcome)` edge exists

**AC-2.1:** `HAS_OUTCOME` edge is present after a successful POST  
**AC-2.2:** The episode node is reachable from the outcome via `(o)<-[:HAS_OUTCOME]-(e)`  
**AC-2.3:** No `HAS_OUTCOME` edge exists if the POST fails (atomicity — MERGE + relationship in same transaction)

### S3 — Skipped outcome is recorded

**Given** the request includes `skipped: true`  
**Then** the outcome is persisted with `skipped=true`, `overall=null`, `completed_at=null`

**AC-3.1:** Skipped outcomes still create the Outcome node (not silently dropped)  
**AC-3.2:** `Belief.corroboration_n` is NOT incremented for a skipped outcome  
**AC-3.3:** A subsequent non-skipped POST replaces the skipped outcome (idempotent MERGE, `skipped` overwritten)

### S4 — Preference belief check after non-skipped outcome

**Given** a non-skipped outcome with `overall >= 2` is saved  
**When** the episode is linked to a `CanonicalTrail` with known tags  
**Then** the belief update queue is notified to check if any preference beliefs have reached N=3 corroborating positive outcomes

**AC-4.1:** A preference belief check task is enqueued after each non-skipped outcome  
**AC-4.2:** A skipped outcome does NOT enqueue a preference belief check  
**AC-4.3:** The preference check does NOT run synchronously in the HTTP request path (must be queued, same as capability beliefs)  
**AC-4.4:** `overall=1` (negative outcome) does NOT count toward preference promotion (only overall >= 2 corroborates)

### S5 — Explicit delta_answer promotes a stated belief immediately

**Given** a non-skipped outcome with a non-empty `delta_answer`  
**When** the delta_answer contains a clear preference statement (non-empty string, no LLM classification required in Phase 1)  
**Then** a `Belief {type: "stated", axis: "preference", confirmed_by_user: true}` is written immediately with `confidence=1.0`

**AC-5.1:** A `stated` belief is written with `confidence=1.0` and `confirmed_by_user=true`  
**AC-5.2:** The belief key is `"stated_preference"` and value is the raw `delta_answer` text  
**AC-5.3:** Stated beliefs are written with `decays=false` (they never decay — user affirmed them)  
**AC-5.4:** An empty `delta_answer` (or `null`) does NOT write a belief  
**AC-5.5:** The stated belief is linked to the Episode via `DERIVED_FROM` and to the Person via `ABOUT` (same provenance pattern as capability beliefs)

---

## Definition of Done

- [ ] All ACs covered by at least one passing test
- [ ] `make check` green
- [ ] Targeted review agent run — check Rule #4 (owner scoping), belief mutation correctness, atomicity
- [ ] `POST /episode/{id}/outcome` live on the API
- [ ] Committed atomically: schema additions separate from API code separate from tests
- [ ] Pushed + epic status updated to DONE ✅

---

## Implementation notes

**Schema additions needed** (add to `graph/schema.cypher`):
```cypher
CREATE CONSTRAINT outcome_id IF NOT EXISTS FOR (o:Outcome) REQUIRE o.outcome_id IS UNIQUE;
```

**Outcome MERGE pattern:**
```cypher
MERGE (o:Outcome {episode_id: $episode_id, owner_id: $owner_id})
ON CREATE SET
    o.outcome_id   = randomUUID(),
    o.overall      = $overall,
    o.delta_question = $delta_question,
    o.delta_answer = $delta_answer,
    o.skipped      = $skipped,
    o.surfaces_at  = datetime(),
    o.completed_at = CASE WHEN NOT $skipped THEN datetime() ELSE null END,
    o.created_at   = datetime()
ON MATCH SET
    o.overall      = $overall,
    o.delta_answer = $delta_answer,
    o.skipped      = $skipped,
    o.updated_at   = datetime()
WITH o
MATCH (e:Episode {episode_id: $episode_id, owner_id: $owner_id})
MERGE (e)-[:HAS_OUTCOME]->(o)
```

**API endpoint:** `POST /episode/{episode_id}/outcome`  
Request body: `{overall: int|null, delta_question: str|null, delta_answer: str|null, skipped: bool}`  
Response: `{outcome_id, episode_id, skipped, overall}`
