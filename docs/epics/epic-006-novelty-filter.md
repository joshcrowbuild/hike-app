# Epic 006 — Novelty Filter in Curator

**Status:** DEFINED
**Phase:** 1 (Personal Intelligence)
**Spec refs:** `novelty-filter-spec.md` §1–7 (N-1…N-8) · `stage-5-personalization.md` §1–4 · decision-log §3, §7, §9, §28 (schema/migration/access-invariant), §29 (engine shape + shortlist-cap cost lever), §30 · Rules #1, #2, #4, #5, #7

---

## Capability statement

When ranking candidate trails for a logged-in viewer, the Curator gently discounts trails the viewer has hiked before — more for recent/frequent repeats, less as a trail ages — so the feed spends a little rank budget on the unfamiliar every time, without ever deleting a known-good trail and without confidence touching rank.

## Architectural context

**Builds on:** Epic 003 (context assembly — the per-candidate owner-scoped fetch pass and the `[PERSONAL CONTEXT]` block) · Stage 5 schema (`Belief`, `Episode`, `CanonicalTrail`) · the N-6 graph migration (the new trail-subject `been_on` belief shape) · **a `been_on` *write-path* epic that does not yet exist** (see dependency note below).

**Enables:** the Stage-7 memory eval (memory-on vs memory-off vs outcomes, S5 §7 / S5-14 — λ/half-life/repeat-factor tuning lives there); a future `prefers_novelty` preference belief that tunes λ per user (Epic 006+).

**Does NOT include:**
- **`been_on` belief *creation/update*** — writing `last_visit_date` / `visit_count` / `value` / `source_episode_ids` + the `DERIVED_FROM` edge on episode ingest is the belief-write path's job, **not** this filter's. This epic *reads and consumes* `been_on`; it assumes the beliefs are populated. **⚠ Dependency gap (must close before build):** Epic 001 is DONE but only writes `pace_on_grade_moderate` capability beliefs — it has **no** `been_on` logic — and no DEFINED/BACKLOG epic in `README.md` (001–008) owns `been_on` writes. The `plan-analysis.md` chain (context assembly → novelty) silently assumes a producer that is not yet scheduled. **Resolution required at build start:** either (a) a new epic "`been_on` belief write path (extends Epic 001's pipeline)" is created, set `DEFINED`, and added to this epic's `Depends on` column in `README.md`; **or** (b) a minimal `been_on`-write story is pulled into *this* epic. The orphaned producer is named here rather than laundered away — every read story below (S2, S5, the E2E DoD item) is blocked until it lands.
- **`prefers_novelty` per-user λ tuning** (N-8 — deferred, gated behind stated/confirmed preference; capability ≠ preference, Rule #7).
- **`heat_response` / readiness / any watch-derived lever** (Epic 007).
- **Empirical tuning of λ, half-life, repeat penalty** — spec defaults ship here; the Stage-7 eval closes them (N-2, N-5 are 🔶).

> **⚠ Precondition (auth — architecture-gap-audit §C3):** `PlanRequest.viewer_id` is a client-supplied request field with **zero authentication today** (defaults to `"anonymous"`; `api/app.py` passes it through verbatim). S2's owner-scoping and AC-2.5's cross-user isolation (Rule #4) are only as strong as the trust in `viewer_id` — which is currently *unestablished*. This epic does **not** claim auth exists; it lists it as an explicit precondition. AC-2.5's guarantee holds only once viewer identity is authenticated (a forged `viewer_id` would still scope to the named owner's overlay). **Flag, do not assume.** The auth-seam decision is upstream (gap-audit §C3 action), not this epic's to build.

> **Legend:** ✅ decided · 🔶 recommended, confirm · ❓ open. Stories tagged 🔶 carry a default that ships now and is confirmed/tuned later; their ACs test the *mechanism*, not the tuned constant.

> **Index bookkeeping (do this when this definition lands):** `README.md` line 12 currently lists Epic 006 as `BACKLOG`. Per the index's own "Adding a new epic" rule, moving `BACKLOG → DEFINED` requires flipping that row **now** — not only `→ DONE` at the end. Also update the `Depends on` cell to include the `been_on`-writer epic once resolved per the gap above (currently "Epic 003").

---

## Access-pattern note (read before S2 / S7) — `scopedQuery` is a design-name, not a callable

The spec (§2.2, line 47) and schema.cypher's §5 comment (line 145) write `scopedQuery(viewer).run(...)` as the access seam; decision-log §28 (line 240) names the wrapper in prose ("a single `scopedQuery(viewer)` wrapper as the only path to owned data") and §29 (line 250) repeats it ("Scout = scoped Cypher via `scopedQuery(viewer)`"). **There is no such wrapper in any `.py` module** — `scopedQuery` appears *only* as an **illustrative design-name in docs** (`schema.cypher` §5, `schema_stage5.md`, and decision-log §28/§29); `grep scopedQuery **/*.py` returns **zero** matches. The sanctioned shape in shipped code is literally a hand-written `WHERE b.owner_id = $viewer_id` clause (architecture-gap-audit §C2): the `ScopedSession` read path plus inline owner-scoping clauses, **not** a callable `scopedQuery` symbol.

**C2 scope — reads only.** Per the gap audit (§C2), `ScopedSession` / `owner_scope` and decision-log §240's "only path to owned data" cover the **read** path; owned-node *writes* (`belief_update.py`, `ingest_episode.py`) use a raw unscoped runner with a hand-typed `owner_id`. The novelty fetch (S2) is a **read**, so its hand-written `WHERE b.owner_id = $viewer_id` is the sanctioned shape for exactly this access — no reader should infer from it that writes are scoped (they are not).

Both shipped sibling epics honor Rule #4 the same way: Epic 003 (AC-1.3, AC-2.1, AC-3.4) and Epic 001 (review fix: "DERIVED_FROM MATCH added `owner_id` constraint") **hand-write the `owner_id` filter**. This epic mirrors that established pattern — **the novelty query carries an explicit `WHERE b.owner_id = $viewer_id`** — rather than asserting a non-existent wrapper or an inverted "no literal `owner_id`" invariant. Building the `scopedQuery` wrapper (and migrating Epic 003's queries onto it, plus extending it to cover the write path per §C2) is a real, decided seam (§28) but a cross-cutting refactor that does **not** belong silently inside the novelty epic; if undertaken, it is its own story.

---

## Stories

### S1 — N-6 migration: the `been_on` belief shape

**Given** the committed `graph/schema.cypher` only ever instantiates `(:Belief)-[:ABOUT]->(:Person)` (line 190, 293) and has no trail-subject `been_on` shape, and **no `graph/migrations/` directory exists yet**
**When** the first forward-only migration is authored and applied
**Then** `been_on` beliefs can carry `last_visit_date` (Date) + `visit_count` (Integer) and link `ABOUT->(:CanonicalTrail)`, additively — no existing belief shape changes.

> Why: novelty recency must be exact and computed in deterministic Python (N-6 / §2.1), and the artifact does not support this shape today, so the migration is not a no-op. `:CanonicalTrail` is already a valid `ABOUT` target per S5 §1, so this is additive, not a shape conflict.

**AC-1.1:** The `graph/migrations/` directory is **created** (it is absent today) along with its versioning convention — forward-only, versioned filename scheme (decision-log §28 decides the convention; this epic *instantiates* it as the first migration). The shape is added there, never edited retroactively into `schema.cypher`.
**AC-1.2:** After migration, a `Belief {subject_type:"trail", key:"been_on", axis:"constraint", decays:false}` with `ABOUT->(:CanonicalTrail)`, `last_visit_date`, and `visit_count` validates against the constraints/indexes without error.
**AC-1.3:** The migration is idempotent — applying it twice leaves the graph in the same state (no duplicate constraints/indexes, no error), consistent with the schema's MERGE/`IF NOT EXISTS` posture.
**AC-1.4:** Pre-existing `ABOUT->(:Person)` beliefs are unaffected — a regression query confirms their shape and count are unchanged.

### S2 — Surface `been_on` in the Curator subgraph (owner-scoped, shortlist-bounded)

**Given** a viewer and a Scout shortlist of `candidate_ids` (capped at K — decision-log §29 cost lever)
**When** the novelty lookup runs inside the Epic 003 context-assembly pass (S5 §4 item 5)
**Then** for each candidate the viewer has hiked, a row `(trail_id, last_visit_date, visit_count)` is returned, owner-scoped, and a candidate with no row is treated as fully novel.

> Why: owned data is reachable only with the viewer's `owner_id` bound into the query (Rule #4), mirroring Epic 003's three fetch queries. Restricting the join to the shortlist (never corpus-wide) honors the §29 cost lever and keeps the injected block bounded.

**AC-2.1:** The novelty query filters `b.owner_id = $viewer_id` (Rule #4 — no cross-user belief leakage), exactly as Epic 003 AC-1.3 / AC-3.4 do. *(This mirrors the established hand-written-`owner_id` pattern — see the access-pattern note above; it does not assert the non-existent `scopedQuery` wrapper.)*
**AC-2.2:** The `MATCH` is restricted to `ct.canonical_id IN $candidate_ids` — never corpus-wide (decision-log §29).
**AC-2.3:** A candidate with no `been_on` row yields `novelty = 1.0` and raises no error — absence of memory is the high-novelty case, never a failure (Rule #1: no-memory = novel, not fabricated).
**AC-2.4:** The query keys recency off `last_visit_date`, never `last_updated_at` or `created_at` (N-6 / §6.2 — a re-hike bumps `last_updated_at` and the year-month `value` in place, so keying off it would conflate "visited" with "belief edited").
**AC-2.5:** A second viewer's `been_on` beliefs are never returned for the first viewer (Rule #4 cross-user isolation — same property-test posture as the access-layer invariant; mirrors Epic 003 AC-6.3). *(Precondition: this isolation holds against a **trusted** `viewer_id`; per gap-audit §C3 `viewer_id` is unauthenticated today, so the test proves the query scopes correctly — not that the caller is who they claim. Auth is upstream.)*
**AC-2.6:** Episode count / number of candidates does not change the number of Cypher round-trips: novelty is fetched in one shortlist-bounded pass, not once per candidate (consistent with Epic 003 AC-5.4).

### S3 — Deterministic `novelty_score()` (Rule #2 by construction)

**Given** a candidate's `(last_visit, visit_count)` and `today`
**When** `novelty_score(last_visit, visit_count, today)` is called
**Then** it returns a float in `[0,1]` — `1.0` when never hiked, falling toward `0` for recent/frequent repeats, re-rising as the last visit ages.

> Why: novelty is a **Curator-only** lever, computed in deterministic Python *before* the judge sees it (N-1, N-4), so the lever is auditable and the judgment-tier LLM never improvises recency math (§2.3). The signature takes only `(last_visit, visit_count, today)` so confidence/freshness/authority are **structurally** unable to enter (Rule #2).

**AC-3.1:** `last_visit is None` → returns exactly `1.0` (never been — fully novel).
**AC-3.2:** Recency term `1 - 0.5**(months/HALF_LIFE_M)` is `~0` at a just-completed visit and `→1` as months grow; result is `clamp(recency * repeat_penalty, 0.0, 1.0)`.
**AC-3.3:** `repeat_penalty = 0.85**(visit_count - 1)`: at equal recency, a higher `visit_count` scores strictly lower (a constantly-revisited trail is the least surprising), and the penalty floors gently — never to zero for finite `visit_count`.
**AC-3.4:** `HALF_LIFE_M` default is `9` months (🔶 N-5 — a trail hiked ~9 months ago is "half fresh again"); the constant is named and overridable, not a magic literal, so the Stage-7 eval can tune it. *(This is novelty re-rise, distinct from the belief-confidence decay half-lives in S5 §3 — the two are not anchored to each other.)*
**AC-3.5 (Rule #2 — load-bearing):** the function signature accepts **no** confidence, freshness, authority, or `corroboration_n` parameter; a test asserts the function is structurally incapable of reading any confidence component (N-7b — proves the §2.1 field separation is physical, not cosmetic).
**AC-3.6:** The function is pure (no I/O, no graph access) and deterministic for fixed inputs.

### S4 — Bounded multiplicative discount, applied after the Curator's merit score

**Given** the Curator's per-candidate taste/fit score `S ∈ [0,1]` and the candidate's `novelty`
**When** the rank score is finalized
**Then** `adjusted = S * (1 - λ * (1 - novelty))` with `λ = 0.25` default — novelty discounts repetition but never boosts above merit and never eliminates.

> Why multiplicative-*after*-`S`, not a term inside `S` (§4.2): `S` and `adjusted` sit side-by-side in a trace so the novelty effect is exact and auditable, and a high-merit favorite (`S` near 1) absorbs the discount and still ranks — the "your favorite ridge, and today the smoke has cleared" case survives (§3.1). λ is the explore/exploit dial (decision-log §9).

**AC-4.1:** `novelty = 1.0` → `adjusted == S` exactly (novelty never boosts above merit — sibling to Rule #2's "confidence shapes presentation, not rank").
**AC-4.2:** `novelty = 0.0` → `adjusted == S * (1 - λ)` = `0.75·S` at λ=0.25 — a **25% maximum** haircut, never `0`; a hiked trail is discounted, never deleted (N-2).
**AC-4.3:** `λ` default is `0.25` (🔶 N-5), named and overridable; `λ=0` reduces to pure exploit (`adjusted == S`), confirming λ is the only explore knob.
**AC-4.4:** `adjusted` is monotonic non-decreasing in `novelty` for fixed `S`, and non-decreasing in `S` for fixed `novelty` (the discount reorders only near-ties, never inverts merit wholesale).
**AC-4.5 (worked check, §4.3):** with the spec's table inputs — Old Rag `(S=0.95, nov=0.55)→0.84`, Riprap `(0.80, 1.00)→0.80`, Whiteoak `(0.92, 0.78)→0.87`, Old Rag-last-week `(0.95, 0.10)→0.74` — a great repeat beats a mediocre new trail, a near-tie breaks toward the novel option, and the just-hiked repeat is discounted but not deleted.

### S5 — Inject the precomputed novelty scalar into the Curator prompt

**Given** per-candidate novelty scalars computed in S3 and the bounded shortlist (K)
**When** the `[PERSONAL CONTEXT]` block is assembled (extending Epic 003 / S5 §4)
**Then** the Curator receives novelty as a **per-candidate scalar already computed**, with a human-legible last-visit annotation, never as raw belief text to reason over.

> Why: handing the judge a precomputed scalar keeps the lever deterministic and stops the LLM improvising its own math (§2.3); the block is shortlist-bounded so it never grows the judgment-tier prompt corpus-wide (decision-log §29).

**AC-5.1:** The injected block matches the §2.3 shape — header line `Novelty (1.0 = never hiked, 0.0 = hiked this month, repeatedly):` followed by one line per shortlisted candidate with the scalar and a `(last hiked YYYY-MM, N visits)` / `(new to you)` annotation.
**AC-5.2:** The novelty block lives **inside** the `[PERSONAL CONTEXT — private, not for disclosure]` fences and is consumed by the Curator via the existing `profile` parameter — one assembly per `plan()` call, not per candidate (consistent with Epic 003 AC-5.4).
**AC-5.3:** The block contains the **scalar**, not raw `been_on` belief text or full visit history — the judge does not re-derive recency.
**AC-5.4 (Rule #5):** the Curator's emitted rationale may say *"you've hiked this before — surfacing it because conditions are unusually good"* but a test confirms the **feed card never dumps raw visit dates/counts** — share the derived conclusion, not the substrate.
**AC-5.5:** An anonymous viewer or a viewer with no `been_on` rows produces a `[PERSONAL CONTEXT]` block with no novelty section (or an empty one), and `plan()` proceeds identically (degrade-and-disclose; consistent with Epic 003 S6 / AC-4.2).

### S6 — The sole hard gate is a user-stated session intent ("somewhere new")

**Given** a viewer who has explicitly set a session intent like *"somewhere new"* (a query-time filter)
**When** the per-session novelty gate runs for **that session only**
**Then** candidates with `novelty < θ_new` are dropped before the Curator ranks, exactly as a typed constraint — and with **no** such intent, novelty is a soft discount only and nothing is gated.

> Why: a repeat is not a violation (§1.2), so novelty is never a default guardrail (N-1). The single exception is *user-stated, not inferred* — identical in spirit to "no dogs-required trails when Ruby's along" (N-3).
>
> **Ordering reconciliation (S6 vs the Epic-003 pipeline).** The spec (§3.2) calls this a "Scout/guardrail" gate, but `novelty_score` is computed in the **context-assembly pass**, which Epic 003 runs *after* Scout/guardrail filtering and *before* the Curator (Epic 003 AC-5.3: "context is injected AFTER guardrail filtering"). At literal guardrail time the score does not exist yet. This epic therefore places the `θ_new` drop as a **post-context-assembly, pre-Curator filter** — semantically a guardrail (deterministic, typed, drops candidates before ranking) but executed at the point in `plan()` where novelty is known. The "Scout/guardrail" language in §3.2 describes its *category* (a hard, user-stated constraint), not a claim that it runs inside the literal Scout step.

**AC-6.1:** With no session intent set, **no** candidate is dropped for novelty — every shortlisted trail reaches the Curator and is only soft-discounted (N-2 default path).
**AC-6.2:** With the "somewhere new" intent set, candidates with `novelty < θ_new` are filtered **after context assembly, before the Curator ranks** — not by the Curator's judge and not inside `novelty_score()`'s consumer math.
**AC-6.3:** `θ_new` default is `0.5` (🔶 N-3), named and overridable.
**AC-6.4:** The hard gate is **never** triggered by an inferred belief — only by an explicit, typed session intent; a test confirms that a viewer with many low-novelty trails but no stated intent has nothing filtered (capability ≠ preference, Rule #7).
**AC-6.5:** The session intent does not persist — it gates that session only; a subsequent intent-free `plan()` for the same viewer hard-filters nothing.

### S7 — Confidence-never-penalizes-rank invariant (Rule #2 / decision-log §7) as a first-class property test

**Given** the full rank pipeline (novelty fetch → `novelty_score` → `adjusted`)
**When** a candidate's confidence-axis inputs are varied while its visit history is held fixed
**Then** the candidate's `adjusted` rank score is **identical** — confidence cannot reach rank through the novelty path.

> Why: this is the load-bearing constraint (§5, decision-log §7). It sits alongside the decision-log §28 "does the access layer ever emit an ungranted node?" property test as a first-class invariant, because the back-door it forecloses (one field feeding both confidence *and* rank) is subtle and only a test makes the §2.1 field separation provable.
>
> **⚠ Reconcile with Epic 001's `corroboration_n` derivation (load-bearing for this test to be true).** Epic 001's review fix made `corroboration_n` **derived from the actual `DERIVED_FROM` edge count** ("not stored counter"). N-6 (§2.1, Rule #7 provenance) requires `been_on` to append a `DERIVED_FROM` edge **per re-hike**. The two together mean `been_on` will *mechanically accrue* a non-zero, edge-count-derived `corroboration_n` — so the spec's "`been_on`'s `corroboration_n` is not created/maintained/read" is **not automatically true** under the shared derivation rule; the provenance edges N-6 mandates would back-door a `corroboration_n` value. This epic's resolution: provenance edges exist (Rule #7) but **novelty must never read an edge-count-derived `corroboration_n`** for `been_on` — recency/repetition come *only* from the dedicated `visit_count` property. The S7 property test is precisely what proves the divorce holds despite the edges (AC-7.2 below).

**AC-7.1 (N-7a):** Holding `(last_visit, visit_count)` fixed and varying a candidate's confidence / freshness / authority inputs yields a **bit-identical** `adjusted` score.
**AC-7.2 (N-7b — the assertion that catches the Epic-001 back-door):** Varying `corroboration_n` on a `been_on` belief — including the `corroboration_n` that the shared edge-count derivation produces from its `DERIVED_FROM` provenance edges — yields an **identical** `novelty_score` **and** identical `adjusted`. This proves `visit_count`, not `corroboration_n`, drives novelty: the test would fail if novelty ever rode on the derived corroboration count.
**AC-7.3 (Rule #4 corollary, decision-log §3):** a lesser-traveled / low-corroboration novel trail (`novelty = 1.0`) is **never** rank-penalized for its low confidence — it ranks at `adjusted == S`, reinforcing "lesser-traveled trails are first-class" (decision-log §3), not threatening it.
**AC-7.4:** AC-7.1 and AC-7.2 are registered as a **named property test** in the suite (mirroring the access-layer invariant test's standing), not an incidental unit test — so a future refactor that reintroduces the back-door fails CI.

---

## Definition of Done

- [ ] `README.md` row flipped `BACKLOG → DEFINED` (and `Depends on` updated to name the `been_on`-writer epic once resolved) — done when *this* definition lands, not at the end
- [ ] The `been_on`-writer dependency closed: either a new `DEFINED` epic exists and is in this epic's `Depends on`, or a minimal `been_on`-write story was pulled in — **no novelty story builds until `been_on` has a producer**
- [ ] All ACs covered by at least one passing test
- [ ] `make check` green (ruff + mypy + pytest)
- [ ] N-6 forward-only migration created in the new `graph/migrations/` dir, applied to local Neo4j via `make schema`; idempotent on re-apply
- [ ] Targeted review agent run; CRITICALs fixed — review **must** verify: (a) Rule #4 — novelty Cypher hand-writes `WHERE b.owner_id = $viewer_id` like Epic 003, with shortlist restriction; (b) Rule #2 — `novelty_score()` admits no confidence input and the S7 property test (incl. AC-7.2's `corroboration_n` case) passes; (c) Rule #5 — no raw visit history reaches the feed card; (d) N-3 hard gate fires only on stated intent, at the post-context-assembly point
- [ ] End-to-end: `plan()` for a seeded multi-episode Josh profile produces a Curator call whose `[PERSONAL CONTEXT]` carries precomputed novelty scalars, and the worked-check ordering (AC-4.5) holds against the seeded data
- [ ] Committed atomically: migration · `novelty_score` + discount (pure functions) · context-assembly wiring · tests, as separate commits
- [ ] Pushed + `README.md` status updated to DONE ✅

---

## Implementation notes

**Pure functions** (new, fully unit-testable — no graph access):
- `novelty_score(last_visit: date | None, visit_count: int, today: date) -> float` — §4.1; signature is the Rule #2 enforcement point.
- `apply_novelty_discount(S: float, novelty: float, lam: float = 0.25) -> float` — §4.2, `S * (1 - lam * (1 - novelty))`.
- Constants `HALF_LIFE_M = 9`, `REPEAT_FACTOR = 0.85`, `LAMBDA = 0.25`, `THETA_NEW = 0.5` — all named, all 🔶, all overridable for the Stage-7 eval.

**Novelty fetch** (extends the Epic 003 context-assembly pass; `orchestration/context_assembly.py`):
- `fetch_novelty(viewer_id, candidate_ids, session) -> dict[str, tuple[date, int]]` — hand-writes `WHERE b.owner_id = $viewer_id` (Rule #4, mirroring Epic 003's `fetch_*` functions), `MATCH (b:Belief {subject_type:"trail", key:"been_on"})-[:ABOUT]->(ct:CanonicalTrail) WHERE b.owner_id = $viewer_id AND ct.canonical_id IN $candidate_ids`, returns `last_visit_date` + `visit_count`. Missing candidate → caller defaults to `novelty = 1.0`. **Does not** read `corroboration_n` (see S7 reconciliation).

**Migration** (`graph/migrations/` — new dir, forward-only, N-6): adds the trail-subject `been_on` shape (`ABOUT->(:CanonicalTrail)`, `last_visit_date`, `visit_count`) additively; does not touch existing `ABOUT->(:Person)` beliefs; idempotent.

**Open / deferred (per legend):**
- 🔶 **N-2 / N-5 empirical tuning** — λ, `HALF_LIFE_M`, repeat factor ship at the spec defaults and are confirmed/tuned in the Stage-7 memory eval (S5 §7 / S5-14). This epic tests the *mechanism*; the eval closes the *constants*.
- ✅ deferred **N-8** — `prefers_novelty` per-user λ tuning is explicitly out of scope (gated behind stated/confirmed preference; capability ≠ preference). A future Epic 006+ extension, not a gap here.
- ⚠ **`been_on` write path** — an unscheduled producer (see Architectural context). Not deferred *within* this epic's value but *upstream* of it; must be resolved before build, not after.
