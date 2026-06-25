# Epic 011 — Scoped-Write Seam

**Status:** DONE ✅ *(2026-06-24 — built on `claude/track-a-write-path`)*  
**Phase:** 1 (Personal Intelligence) — foundational, before Stage 8 multiplayer  
**Spec refs:** gap-audit C2 · decision-log-additions-proposed §40 (C2) · decision-log §28 (access-control T2, line 240: `scopedQuery(viewer)` = the only path to owned data — `scopedQuery` is the design-name; the implemented seam is `ScopedSession.run`) · Rules #4, #5, #7

---

## Capability statement

Every write that touches an **owned** node (Episode / Belief / PhysicalProfile / Outcome / PartyProfile) goes through a single seam that injects the viewer's identity and **refuses** an unscoped owned-label `MERGE`/`SET` — extending Rule #4's "single path to owned data" from **reads only** to **reads + writes**, so no writer can create or overwrite another owner's node by forgetting an inline `owner_id` clause.

## Architectural context

**Builds on:**
- `graph/client.py` — `ScopedSession` (the read choke point; `run()` injects `$viewer_id` / `$granted_ids`)
- `graph/queries.py` — `owner_scope(var)` helper (today used by exactly one read stub, `episodes_on_trail`)
- `graph/load.py` — `make_runner` (the unscoped runner that drains belief updates today)
- `orchestration/belief_update.py` — `Runner = Any` raw write path (`_update_pace`, `_update_maxima`, `_write_pace_belief`, `process_episode`)
- `ingestion/ingest_episode.py` — `create_episode` (hand-typed `owner_id = $owner`), `make_runner` drain at ingest
- `tests/test_graph_queries.py` — the existing **assertion-based** owner-scope read test (`test_personal_query_is_owner_scoped`: three plain asserts, no randomization), to be upgraded to a property/fuzz test here

**Enables:** Stage 8 multiplayer (shared Belief / PartyProfile writes — schema:314) safely; a single grants-change touchpoint; the Stage-7 §7 access-control invariant now coverable on the **write** side; closes gap-audit C2 and removes the wrong-memory risk in M8 (owner-scoped corroboration count, once the recount routes through a write builder).

**Does NOT include:**
- Authentication of `viewer_id` (gap-audit C3 — `viewer_id` is still client-supplied; `run_write` trusts its caller exactly as `run` does today). This epic hardens the *query/data layer*, not the auth boundary; treat an authenticated viewer as a precondition, never a fact.
- The commons forked write / `:CommonsObservation` (gap-audit C1 — a future Commons Fork epic, not yet defined). That write is *deliberately* person-severed and is **not** an owned-node write — it must not acquire an `owner_id` scope clause, and `:CommonsObservation` is **not** in `OWNED_LABELS`.
- The owned-label DB invariant / CI lint that every owned-label Cypher carries a scope clause (gap-audit M9 — a follow-on; this epic supplies the **runtime** refusal and the owned-label manifest that M9's lint will import).
- A real transaction wrapper across the multi-statement belief update (still per-statement `MERGE`; idempotency unchanged from Epic 001).
- An owned-scoping clause on `:Dependent` writes — `Dependent` is a household sub-node keyed on `dependent_id` with **no** `owner_id` property (schema:168–169, 205–208); it is **not** in `OWNED_LABELS` (see S1 note).

---

## Stories

### S1 — `ScopedSession.run_write` injects identity and refuses unscoped owned writes

**Given** a write query `(cypher, params)` whose Cypher `MERGE`s or `SET`s an **owned** label (Episode / Belief / PhysicalProfile / Outcome / PartyProfile)  
**When** it is submitted through `ScopedSession.run_write(query)`  
**Then** `$viewer_id` / `$granted_ids` are merged into params (as `run` does), and the write is **executed only if** the statement pins the owned node it creates or mutates to `$viewer_id` (or a granted id); a statement that writes an owned label **without** such a clause raises `UnscopedWriteError` at the boundary (fail loudly — Rule #4), and the runner is never called.

**AC-1.1:** `ScopedSession.run_write((cypher, params))` merges `viewer_id` and `granted_ids` into params before any execution, identically to `run()`.  
**AC-1.2:** A `MERGE`/`SET` on an owned label whose statement contains **no** owner-scoping clause raises `UnscopedWriteError` (a subclass of `ValueError`) and does **not** invoke the runner.  
**AC-1.3:** A `MERGE`/`SET` on an owned label that either carries `owner_scope(var)` (mutate path) or sets `owner_id = $viewer_id` on create passes the guard and reaches the runner exactly once.  
**AC-1.4:** A write touching **only** world/public labels (Area / CanonicalTrail / Trailhead / Segment / SourceRecord) passes through `run_write` without requiring a scope clause (world writes stay unowned — `graph/load.py` semantics preserved).  
**AC-1.5:** The set of owned labels is read from a single shared manifest (`graph.queries.OWNED_LABELS`) — `{Episode, Belief, PhysicalProfile, Outcome, PartyProfile}` — not hardcoded inline in the guard, so the same constant is importable by the M9 lint and the fuzz test. `:CommonsObservation` and `:Dependent` are **excluded** (person-severed by design / no `owner_id` property respectively).  
**AC-1.6:** Owned-label create/`MERGE` writes that pin `owner_id` to a param **other than** `$viewer_id` (e.g. a free `$owner`) do not satisfy the guard: the guard is satisfied only by `owner_scope(var)`'s exact clause **or** a create that binds `owner_id = $viewer_id`. (A builder must never accept a caller-supplied owner distinct from the viewer — enforced by the builder API in S3 and asserted in S4.)

### S2 — Route belief-update and episode-ingest writes through the seam

**Given** `belief_update.py` (`Runner = Any`) and `ingest_episode.py` (`make_runner` drain + `create_episode`'s direct `session.run`) write owned nodes via a raw, unscoped runner  
**When** this epic lands  
**Then** every owned-node write in those modules is issued through `ScopedSession.run_write` (or a thin scoped-runner adapter exposing the same guard), and the raw `Runner = Any` / `make_runner` paths no longer reach owned labels

**AC-2.1:** `orchestration/belief_update.py` no longer types its write callable as `Runner = Any`; owned-node writes (`_update_pace`, `_update_maxima`, `_write_pace_belief`) flow through the scoped-write seam. `process_episode`'s Episode **read** routes through `ScopedSession.run` (owner-scoped); its writes flow via `update_beliefs` through `run_write`.  
**AC-2.2:** `ingest_episode.create_episode` issues the Episode `MERGE` (carrying an owner-scoping clause), the `Person-[:DID]->Episode` wire, and the `Episode-[:ON]->CanonicalTrail` wire through the seam. The guard keys on the *written/MERGEd owned label*: the `MATCH (:Person {member_id: ...})` anchor (Person ∉ `OWNED_LABELS`, no `owner_id`) and the `MATCH (:CanonicalTrail {...})` anchor are world/identity matches, exempt from the scope demand; the Episode side of each wire is matched under owner scope.  
**AC-2.3:** `ingest_episode.ingest_episode` drains the belief queue through the scoped-write seam scoped to `owner_id`, replacing the bare `make_runner(neo_session)` drain.  
**AC-2.4:** The M8 corroboration recount (`size([(b)-[:DERIVED_FROM]->() | 1])`) is replaced by an owner-scoped count authored in `graph.queries` — `MATCH (b:Belief {belief_id: $bid}) MATCH (b)-[:DERIVED_FROM]->(e:Episode) WHERE <owner_scope('e')> WITH b, count(e) AS n SET b.corroboration_n = n, b.confidence = CASE WHEN n >= $threshold THEN 0.7 ELSE 0.3 END` — preserving the confidence-promotion `CASE` (the n≥threshold → 0.7 branch must survive the rewrite).  
**AC-2.5:** Epic-001's behavioural assertions hold unchanged: an end-to-end `ingest_episode → drain` over a fake runner produces the same final `PhysicalProfile` / `Belief` state (pace, maxima, `corroboration_n`, confidence) as Epic 001 did. Test *fixtures* are updated where the runner type changed (the runner is now a `ScopedSession`/scoped adapter, not a bare list-appender) — no exact unchanged test count is promised.

### S3 — `graph.queries` is the single author of owned-node Cypher (read **and** write)

**Given** owned-node Cypher is authored inline in `belief_update.py` and `ingest_episode.py` today, and `graph.queries` authors only reads  
**When** this epic lands  
**Then** every owned-node `MERGE`/`SET`/`MATCH` is produced by a builder in `graph/queries.py` that uses `owner_scope()` (mutate) or binds `owner_id = $viewer_id` (create), so all owned-node Cypher lives in one place — one fuzz test and one future grants change cover both directions

**AC-3.1:** New write builders in `graph/queries.py` return `(cypher, params)` for: Episode upsert, `Person-[:DID]->Episode`, `Episode-[:ON]->CanonicalTrail`, `PhysicalProfile` pace/maxima upserts, the pace `Belief` upsert, `DERIVED_FROM` / `ABOUT` wiring, and the owner-scoped corroboration recount.  
**AC-3.2:** Each write builder either carries an explicit `owner_scope(var)` clause or binds `owner_id = $viewer_id` on create such that it passes the S1 guard — verified by feeding every builder's output through the guard (the primary, structural check).  
**AC-3.3:** No owned-label `MERGE`/`SET` string literal remains inline in `belief_update.py` or `ingest_episode.py` — a supporting hygiene grep over both modules confirms the only call sites pass a `graph.queries` result; the structural AC-3.2 guard pass is the load-bearing assertion.  
**AC-3.4:** Builders are pure `(args) → (cypher, params)` functions with **no** driver/I/O, unit-testable without a database (mirrors the existing `graph.queries` read-builder contract). No builder accepts an owner param distinct from the viewer (upholds AC-1.6).

### S4 — A property/fuzz test over the write builders

**Given** the existing owner-scope read test is assertion-based (three asserts, no randomization) and does not exercise the write path  
**When** the write builders exist  
**Then** a property/fuzz test is **introduced** (via `hypothesis` as a dev dependency, or an explicit seeded-randomization loop) that **fuzzes viewer/owner ids**: for randomized `(viewer_id, owner_id, granted_ids)` triples, it asserts no writer can create or overwrite a node whose `owner_id` is neither the viewer nor in `granted_ids`

**AC-4.1:** A property test fuzzes `viewer_id`, target `owner_id`, and `granted_ids` (distinct, overlapping, and adversarial cases — e.g. `owner_id` ∉ `{viewer_id} ∪ granted_ids`).  
**AC-4.2:** For every write-builder output run through `ScopedSession.run_write` with a recording fake runner, **no** executed statement writes a node bound to an `owner_id` outside `{$viewer_id} ∪ $granted_ids` (cross-owner write is impossible, not merely unlikely).  
**AC-4.3:** A deliberately-malformed write builder (one that omits the scope clause) is asserted to raise `UnscopedWriteError` — proving the guard fails closed, so the test would catch a future writer that forgets the clause.  
**AC-4.4:** The test imports the **same** `OWNED_LABELS` manifest the guard uses (AC-1.5), so adding an owned label without a scoped builder makes the test go red (the manifest is the single source of truth coverage is measured against).  
**AC-4.5:** A world-node write builder (e.g. `load_canonical_trail`'s shape) is asserted to pass `run_write` for an `anonymous` viewer with empty grants — the seam does not over-block public writes.

---

## Definition of Done

- [x] All ACs covered by at least one passing test (named `test_s{story}_{ac}_{desc}` per process doc) — `tests/test_graph_queries.py` (guard + builders + seeded property/fuzz), `tests/test_belief_update.py` (routing + M8 + `process_episode`), `tests/test_ingest_episode.py` (create_episode + end-to-end drain)
- [x] `make check` green (ruff format + ruff + mypy + pytest) — 244 tests
- [x] `graph/client.py` docstring updated: ScopedSession is the choke point for **reads and writes** of owned nodes; states `viewer_id` is **unauthenticated** today (gap-audit C3, a separate spec decision)
- [x] `graph/load.py` docstring corrected: narrowed to **world/public** writes, which are correctly unowned
- [x] `graph/queries.py` module docstring updated: it is the single author of owned-node Cypher for read **and** write
- [x] `orchestration/belief_update.py` `Runner = Any` removed (→ `ScopedWriter` protocol); the `# Rule #4: episode scoped to owner` inline Cypher comment replaced by the structural guard + `owner_scope` builders
- [x] **Adversarial review run** (6 dimensions: guard soundness · cross-owner writes · M8 · behaviour regression · seam integrity · AC/test completeness → per-finding verification; 15 raw → 6 confirmed). **All 6 fixed before close:** composite owner MERGE keys (ownership-theft path closed — the seam now enforces ownership structurally, not via the id convention); viewer-only self-EWMA read (rule #5); AC-2.4 promotion-CASE test; `process_episode` read test; genuinely-adversarial fuzz loop. No live CRITICAL (the headline finding was latent — unreachable under the current per-owner-session trust model, and strictly weaker than the deferred C3 auth gap).
- [ ] ~~`docs/research/decision-log-additions-proposed.md` §40 (C2) flip~~ — **N/A on this track:** that proposed-corrections doc does not exist on `claude/track-a-write-path` (it lives on the parallel design branch). Recorded here so the cross-reference is honest rather than fabricated.
- [x] `docs/epics/README.md` row added (Epic 011, Phase 1, depends on Epic 001) with the note that **011 lands before Epic 003's context_assembly** routes its owner-scoped Cypher through `graph.queries` (gap-audit M9 redirect)
- [x] Committed and pushed

**Notes for the implementer (carried from the gap-audit, so they aren't re-discovered):**
- The guard is a **boundary** check (fail loudly), not a surface degrade — an unscoped owned write is a programming error, never a runtime "degrade and disclose."
- `:CommonsObservation` (gap-audit C1) is **person-severed by design** — it is *not* an owned label and must be excluded from `OWNED_LABELS`, or the guard will wrongly demand an `owner_id` scope on the one write that must not have one. The Commons Fork epic is not yet defined.
- `:Dependent` keys on `dependent_id` and carries **no** `owner_id` (schema:168–169, seed 205–208) — it is a household sub-node, not an owner-keyed overlay node. Exclude it from `OWNED_LABELS`; including it would make the guard demand a scope clause on a label with no `owner_id` to scope against. If Dependent is ever made owner-scoped, that is a separate schema change + story, not a silent fold.
- This epic does **not** make `viewer_id` trustworthy (gap-audit C3). `run_write` scopes to whatever viewer it is handed; a forged `viewer_id` is still a forged write. State this in `ScopedSession`'s docstring; the auth seam is a separate spec decision.
- The seam closes M8 for free **only if** the corroboration recount (AC-2.4) routes through a write builder that owner-scopes the `DERIVED_FROM` count and preserves the confidence `CASE` — otherwise the unscoped `size()` survives as the one clause the seam doesn't cover.
