# Epic 009 — Stage-7 Evaluation Harness Expansion

**Status:** DEFINED
**Phase:** 1→2 bridge (deep eval — Stage 7)
**Spec refs:** `docs/research/stage-7-eval-methodology.md` (source of truth) · Stage 4 §6 (Curator/guardrails) · §7 (T4 thin eval) · decision-log §17 (testing & data hygiene) · §28 (property-based access test + reserved `:CommonsObservation` label) · §29 (cost spike → bake-off; route-by-data-sensitivity) · §30 (capability ≠ preference) · §31 (Stage 6 watch + sensitivity routing) · §11 (multiplayer / grant-stop) · §12 (commons) · cross-cutting thread T4. **Audit corrections this epic must hold to:** `docs/research/decision-log-additions-proposed.md` §40 C1 (commons fork unbuilt), C2 (write-path unscoped), C3 (`viewer_id` unauthenticated), C4 (overlay can egress to cloud judge).

> **Legend:** ✅ decided (in the Stage-7 doc — build it) · 🔶 recommended, confirm during build · ❓ open, do not block on it.

This epic formalizes the wave-1 Stage-7 methodology into buildable stories. The methodology is **DESIGN-complete**; this epic is **build**. Every story is **additive** to `evals/truthfulness.py` (Stage-7 §9 ✅) — existing call sites (`tests/test_eval.py`, `evals/run_bakeoff.py`) keep passing. **Why additive, not a rewrite:** the harness already encodes the two load-bearing ideas — *stochastic ⇒ report a rate* (`CriterionResult.rate`) and *invariants are code predicates, quality is a judge* — so Stage 7 widens the criteria set, not the spine.

> **Build prerequisite (honest scope — read before sequencing).** Stage 7 depends on Stages 5–6 being built: a real personalized, watch-enriched flow to evaluate. Per `docs/epics/README.md`, Epic 001 is DONE but **002/003 are DEFINED-not-built, 004 is BACKLOG**, and the **Commons Fork epic does not exist yet** (proposed §40 C1 — the de-identified forked write that S3 promotion and the S7 severance invariant depend on is *designed, not built*). Therefore **only S1–S4, S6, S8 (replay-only), and the unit half of S7 are buildable now.** S5 judge-calibration (AC-5.6), the S7 sensitivity-routing eval-loop check (AC-7.3), the S7 commons-severance invariant (AC-7.2), and **all of S9** are blocked on those epics landing. This epic is *defined* in full so the access/eval seams are built test-first, but it **cannot reach DONE before those epics land** — the DoD reflects this.

> **Seam-name note (memory hygiene, CLAUDE.md "wrong memory is worse than none").** The decision log informally names the access wrapper **`scopedQuery(viewer)`** (§28/§29/§30) — but **no symbol literally named `scopedQuery` exists in code**; it is a design-name only. The sanctioned shapes are **`GraphClient.scoped_session(viewer_id, granted_ids=())` → `ScopedSession`** for **reads**, plus **hand-written `WHERE owner_id = $...` clauses** for owned-node **writes**. This epic uses the **code** names throughout (correct for a build epic). ⚠️ The read/write asymmetry is load-bearing for S7: per proposed §40 C2, owned-node **writes** (`belief_update.py`, `ingest_episode.py`) use a **raw unscoped runner** with hand-typed `owner_id` and do **not** pass through `ScopedSession` — so this epic must never claim writes are seam-scoped (see AC-7.1).

---

## Capability statement

The evaluation harness can score the full stochastic Scout→Verifier→Curator flow against a **golden-trip ground-truth set**, holding **safety/privacy invariants to zero-tolerance code predicates** and scoring **recommendation quality with a calibrated LLM-judge**, reporting **N-run pass rates with their spread**, in a **hermetic replay mode (CI gate) and a live mode (acceptance + cost spike)** — so a stochastic multi-agent flow's quality and safety can be shown trending across engine and provider versions, with merges blocked on any invariant regression.

## Architectural context

**Builds on:** `evals/truthfulness.py` (the thin spine: `Scenario`/`evaluate`/`CriterionResult.rate`/`EvalReport`, `source_or_silence_ok`, `no_blocked_surfaced`), `evals/run_bakeoff.py` (`_make_scenario` + `CONFIGS`), `orchestration/engine.py` (`PlannedTrail.facts` carrying raw `VerifiedFact`s pre-phrasing from `plan_from_origin`; `Feed`/`FeedCard`), `orchestration/curator.py` (`_parse_ids` = the defensive-JSON template), `graph/client.py` (`scoped_session(viewer_id, granted_ids=())` → `ScopedSession`, the rule-#4 **read** choke point — `granted_ids` plumbing **already exists**), `orchestration/providers/registry.py` (the sensitivity-routing resolution).

**Enables:** the Phase-2 multiplayer regression gate, the outstanding Stage-4 cost spike (decision-log §29) via the live-mode bake-off, the memory-on vs memory-off comparison (Stage 5/6), and the test-first access layer for grant-stop privacy (Stage 8).

**Does NOT include:** grant-stop-on-provenance privacy invariant (Stage-7 §7 / §11 — specified, implemented **test-first in Stage 8** when grant *enforcement semantics* land; note the `granted_ids` *parameter* exists today and is used now by AC-2.7/AC-7.1) · party-merge quality metrics (Stage 8) · commons-derived quality references (Stage 9, gated by k-anonymity volume + the consent/ODbL gate **and** the unbuilt Commons Fork write, proposed §40 C1) · the rendered-card structured-claim round-trip (`FeedCard` carries `lines: list[FeedLine]`, not a structured claim — S4 scopes fidelity to the pre-card `PlannedTrail.facts` hook that exists today) · `heat_response` and other Stage-6 belief-derived scenarios beyond the memory-on/off hook · **building** the commons forked write itself (that is the pending Commons Fork epic — this epic only writes the *test* that gates it, fail-if-absent).

---

## Stories

Build order is dependency-ordered: **S1 (criteria registry) → S2 (fixtures) → S3 (golden set) → S4 (invariant criteria) → S5 (judge) → S6 (N-run reporting) → S7 (security/privacy) → S8 (regression matrix) → S9 (memory hook).** S1 unblocks everything; S2+S3 are the long-pole assets; S4–S7 register criteria onto the S1 registry; S8 wraps them. (Buildability gating per the prerequisite note above.)

### S1 — Generalize the criteria registry (the additive seam)

**Given** `evaluate()` today hardcodes two predicates + an optional judge into a `counts` dict (`truthfulness.py` L66–78)
**When** the registry is generalized
**Then** criteria become a **list of registered criteria**, each tagged `INVARIANT` or `QUALITY`, each carrying its own predicate-or-judge, with `source_or_silence_ok` and `no_blocked_surfaced` registered as the first two `INVARIANT` criteria — same behavior, now extensible.

**Why:** every later story (S4 invariants, S5 quality, S7 security) registers *onto* this seam. Doing it first means each subsequent criterion is a registration, not an edit to `evaluate()`.

**AC-1.1:** A criterion carries `name`, `kind` (`INVARIANT` | `QUALITY`), and a callable; `evaluate()` iterates the registered list rather than a literal `counts` dict.
**AC-1.2:** `source_or_silence` and `no_blocked_surfaced` register as `INVARIANT` and produce **byte-identical `CriterionResult`s** to today for the same input — regression-locked by the **existing** `tests/test_eval.py` (`test_clean_run_passes_all`, `test_missing_source_fails_source_or_silence`, `test_blocked_trail_fails_integrity`).
**AC-1.3:** `tests/test_eval.py::test_clean_run_passes_all` passes unchanged — the criteria-name set for a no-judge run is still exactly `{"source_or_silence", "no_blocked_surfaced"}`.
**AC-1.4:** The degenerate boolean `judge` path (S5) still registers a criterion **literally named `fact_accuracy`** so the existing `tests/test_eval.py::test_judge_criterion_added_and_scored` resolves it by name and reads `rate == 0.0` for a `lambda planned: False` judge — unchanged.
**AC-1.5:** A new criterion can be registered without modifying `evaluate()`'s body (verified by registering a throwaway test criterion).
**AC-1.6:** `Scenario(name, run)`, `Run`, `CriterionResult` (+ `.rate`), and `EvalReport` are **unchanged in signature** (Stage-7 §9 "keep as-is" ✅).

### S2 — Scenario fixtures + the two-mode conditions seam

**Given** live conditions are the irreducible run-to-run variance (Stage-7 §2.2 ✅)
**When** a scenario is built
**Then** it runs against a **conditions backend** that is either a **replay-fixture bundle** (captured adapter responses, hermetic) or the **live adapters**, selected by mode — the *same* scenario runs in both.

**Why:** replay alone can't catch "NWS changed its schema and our adapter silently mis-parses"; live alone can't give a stable regression signal because the world moved. The split is the corpus-vs-live discipline (decision-log §4/§28) applied to the eval.

**AC-2.1:** A scenario lives as a directory under `evals/scenarios/<name>/`: `intent.json` + `viewer.json` + `conditions/` (the captured bundle) + `expected.json` (S3).
**AC-2.2:** Replay mode reads `conditions/` and the engine run makes **zero network calls** (asserted by a no-network guard); the only remaining variance is LLM sampling. **Net-new work, not a generalization:** `run_bakeoff.py` today opens a live `GraphClient`/Neo4j and calls `build_probes(settings)` for live network, and `main()` hard-exits (`raise SystemExit(1)`) when `ANTHROPIC_API_KEY` is unset. The replay backend + the no-network guard + an API-key-optional path are **new code** this story must add; no such path exists today.
**AC-2.3:** The captured conditions bundle is a **fixture artifact under `evals/scenarios/.../conditions/`, never a graph node** (rule #3 — live data is JIT-overlaid, never persisted). A test asserts no `conditions/` content reaches the graph.
**AC-2.4:** Live mode hits the real adapters via `build_probes(settings)`; same `Scenario`, backend swapped. This generalizes `run_bakeoff.py::_make_scenario` to accept the backend (Stage-7 §9 ✅) **and** cleans up its current redundancy — `_make_scenario` calls both `plan(...)` (discarded) and `plan_from_origin(...)` (returned); the generalized form runs the pipeline once.
**AC-2.5:** Each scenario records `(provider, model, tier)` and the conditions **mode** in its report so mode and provider are legible regression axes (S8).
**AC-2.6:** The four Phase-0-shaped scenarios exist as fixtures: **nominal**, **guardrail-trip** (fixture injects flash-flood / AQI≥201 / closed permit on a *high-taste* trail), **sparse/cold** (thin corpus, no crowd data), **adapter-outage** (one+ fixture returns `None`/error). 🔶 Scenarios 5 (personalized) and 6 (privacy-adversarial) are stubbed here but only fully populated when Stages 5/6/8 land.
**AC-2.7:** The viewer in every scenario flows through `GraphClient.scoped_session(viewer_id, granted_ids)` → `ScopedSession` (rule #4, **read** path) — the eval uses the **same read access seam as production, never a privileged bypass**. The `granted_ids` parameter exists today, so grant-bearing scenarios pass real grant sets through it now (only the grant-*stop* enforcement semantics in AC-7.5 are Stage-8-deferred). **Precondition (proposed §40 C3):** `viewer_id` is client-supplied and unauthenticated today; the scenario fixture supplies it as if already authenticated — the eval tests the scoping layer, not identity. A forged `viewer_id` defeats scoping regardless of this eval; production must derive `viewer_id` from an authenticated session.

### S3 — The golden-trip ground-truth set + `expected.json`

**Given** both metrics lean on a reference set, the stage's long-pole asset (Stage-7 §10)
**When** a golden trip is authored
**Then** its `expected.json` splits ground truth to match the two metrics — **hard expectations** (for *truthful*) and **soft expectations** (for *good recommendation*).

**Why:** there is no single correct feed, so soft expectations are a *plausible-set + reference ranking*, treated as reference not key; but truthfulness *is* decidable against the captured bundle, so hard expectations are exact values + a must-be-blocked set.

**AC-3.1:** `expected.json` hard section carries, per fact: the exact `source` + `value` the fact must equal **given the bundle** (semi-auto-generated from `conditions/` + the guardrail rules), the **must-be-blocked trail set** (hand- or semi-auto-labeled), and which `disclosures` must appear (Stage-7 §10.1 ✅).
**AC-3.2:** The **must-be-blocked set is a label in the cassette, not a re-run of engine code** — this is what makes the §4.1c guardrail-converse check non-circular (you cannot test the guardrail with the guardrail).
**AC-3.3:** `expected.json` soft section carries a **plausible-set** of acceptable trails (not a single answer), a *reference* ranking, and explicit "clearly-surface / clearly-exclude" anchors. Hand-curated.
**AC-3.4:** ~5–10 hand-built Shenandoah/GWJ pilot trips exist (Phase-0 bootstrap, Stage-7 §10.2 ✅); `run_bakeoff.py`'s Old Rag point (38.5707, −78.2861) is trip #1. This is enough to stand up the CI eval (S6) immediately.
**AC-3.5:** Synthetic edge-case bundles are hand-authored for conditions you can't reliably catch live (flash-flood + permit-closure + smoke at once) — these power the guardrail-trip and adversarial scenarios without waiting for weather.
**AC-3.6:** Each golden trip carries a pinned `ingest_version` and an **expiry/review stamp** — golden expectations are versioned with the corpus; a stale golden set is wrong memory (CLAUDE.md: "wrong memory is worse than none").
**AC-3.7:** 🔶 A **human-labeled slice** is held back, used only to calibrate the judge (S5) — the one place humans score directly (Stage-7 §10.3).
**AC-3.8:** A `promote_episode()` path is **stubbed and documented** (real watch-episode promotion is Stage 6, §10.2): selected `Episode`s become golden trips **de-identified, scrubbed of biometrics per rule #5 before entering the shared eval set**. ⚠️ **Precondition (proposed §40 C1):** de-identified promotion presumes the **forked-write / de-identification path**, which is **🔶 designed, not built — the Commons Fork epic is pending** (`create_episode()` writes no `:CommonsObservation`; `grep` for `CommonsObservation|writer_hash|capability_band|sever` over `ingestion/`/`orchestration/` returns nothing). So the stub must encode the de-id contract but **must not assume a forked-write source exists**; full population is blocked on that epic landing. The golden set must in any case stand **without** watch data (rule #6 — watch is enrichment).

### S4 — Register the TRUTHFUL invariant criteria (deterministic, zero-tolerance)

**Given** truthfulness is rule #1, the non-negotiable promise (Stage-7 §4.1)
**When** the invariant criteria register onto S1
**Then** five sub-metrics (§4.1a–e), **all rate-must-be-1.0**, decide truthfulness **in code** against the typed output + the captured bundle — no judge produces the invariant verdict.

**Why:** truthfulness must be tested by something that itself can't hallucinate. We have the ground truth (the adapter bundle) sitting right there; an LLM-judge is the wrong instrument for "did we fabricate a fact."

**AC-4.1 (§4.1a source-stamped):** `source_or_silence_ok` is re-used unchanged — every surfaced fact carries a non-empty `source` + non-null `fetched_at` (already implemented).
**AC-4.2 (§4.1b fidelity):** A new criterion asserts every fact's *value* equals what the adapter returned — `PlannedTrail.facts` (the raw `VerifiedFact`s, available **pre-phrasing** from `plan_from_origin`) equals the bundle in replay / the captured response in live. Pure code assertion for numeric facts (flow, AQI, temp, distance), since `VerifiedFact.value` *is* the structured value. 🔶 The rendered-card round-trip is **out of scope** — `FeedCard` carries `lines: list[FeedLine]`, not the structured claim; that check needs a structured-claim field on the card first (deferred). Fidelity is asserted pre-card here.
**AC-4.3 (§4.1c guardrail integrity):** Extends `no_blocked_surfaced`: (a) no `verdict.blocked` trail reaches the feed [existing], **and** (b) the rendered feed ∩ `expected.json` must-be-blocked-set = ∅ — every condition that *should* block, did. (b) reads the cassette label (AC-3.2), never re-runs the guardrail.
**AC-4.4 (§4.1d disclosure completeness):** Every fact below the confidence floor (rule #2 / decision-log §7 presentation-hedge), or carrying adapter `disclosures` (nearest-gauge distance, FIRMS "thermal anomaly ≠ fire", AirNow "preliminary"), renders **with** its hedge/flag — the *presence* of the disclosure string is a code check (whether it *reads* honestly is the scoped judge, S5).
**AC-4.5 (§4.1e no-fabrication on absence):** When an adapter returns `None`, the card shows no manufactured value — rendered facts ⊆ non-`None` adapter returns. This is source-or-silence's contrapositive and the adapter-outage scenario's acceptance check.
**AC-4.6:** All five register as `INVARIANT`; a single failure in N runs fails the criterion (a 19/20 on an invariant is a P0 with a reproduction, **not** a B+).

### S5 — The LLM-judge for the soft half (`evals/judge.py`)

**Given** "good recommendation" is genuinely subjective and run-varying (Stage-7 §4.2–4.3)
**When** the judge scores a run
**Then** a **`ScoredJudge`** returns per-criterion scores + a one-line justification against a rubric + the golden trip's soft expectations, parsed defensively, with the old boolean `Judge` retained as a degenerate single-criterion (`fact_accuracy`) case.

**Why:** the judge's verdict is **itself sourced** (the justification is its provenance) — mirroring the system's own "provenance on every belief" ethos (rule #7). The judge assists with taste; it is *not* the instrument for the truthful invariants.

**AC-5.1:** `evals/judge.py` defines `ScoredJudge` returning structured per-criterion JSON scores + one-line justifications, parsed **defensively exactly as `curator._parse_ids`** does (strip fences, keep-known, fall back to neutral on garbage) (Stage-7 §4.3 🔶).
**AC-5.2:** Quality criteria register as `QUALITY`: **relevance/fit** (cards match `intent` + plausible-set), **ranking-sanity** (order defensible vs the reference ranking *as reference, not key*), **anti-suppression**, **calm-utility tone** (rubric from the product stance, decision-log §19).
**AC-5.3 (anti-suppression — the distinctive one):** The judge is given two cards identical except for confidence and must confirm the **low-confidence-but-safe-and-relevant** card is **not down-ranked for being uncertain**. This operationalizes rule #2 (confidence shapes *how honestly* a trail shows, never *whether* it ranks) and protects the lesser-traveled trails the product makes first-class (decision-log §3).
**AC-5.4:** The boolean `Judge` path still registers `fact_accuracy` and scores exactly as today (the existing `tests/test_eval.py::test_judge_criterion_added_and_scored` passes unchanged); the new quality criteria are **added alongside** `fact_accuracy`, never in place of it (Stage-7 §9 ✅).
**AC-5.5 (provider-independent judging):** The judge's `(provider, model)` config is **separate** from the engine's — we never grade a model with itself when that flatters it. The bake-off (S8) can hold the judge fixed while varying the engine provider.
**AC-5.6 (judge calibration — BLOCKED on a real personalized flow + human-labeled volume):** A periodic check scores the judge against the held-back human-labeled slice (AC-3.7) and reports judge↔human agreement (Cohen's κ). A judge that drifts from human taste is a measurement-instrument bug (the "evals for the eval" guard). ❓ The κ threshold below which the judge is "miscalibrated, re-prompt" is open — report κ, don't gate on it yet.
**AC-5.7 (no training, rule #9):** The judge is prompted + rubric-anchored; never fine-tuned on our outcomes. Pure orchestration.

### S6 — N-run pass-rate reporting + threshold regimes

**Given** a single run tells you almost nothing about a stochastic flow (Stage-7 §3)
**When** a report is read
**Then** **invariant criteria are held to 1.0 unconditionally** and **quality criteria to a tuned floor + a stability bound**, with the rate reported **with its spread/interval**, never as a bare point estimate.

**Why:** a uniform `threshold=1.0` (today's default) is correct for invariants and *wrong* for quality. A 95% pass rate on "never surface a closed-by-flash-flood trail" is a failure, not a B+; meanwhile a quality flow that's brilliant half the time and incoherent the other half is a worse product than a steadily-good one.

**AC-6.1:** `EvalReport.passed()` becomes threshold-aware per criterion class: `INVARIANT` → 1.0 unconditionally; `QUALITY` → its tuned floor. Existing `passed(threshold=1.0)` call sites still resolve (invariants already want 1.0).
**AC-6.2:** A quality criterion passes its scenario iff (a) the mean judge score clears a floor (🔶 start **0.7/1.0**) **and** (b) run-to-run variance is bounded. The report carries **mean, floor-pass rate, and spread (p10/p90 or stdev)** — additive fields, not a point estimate.
**AC-6.3 (tiered N):** N is a confidence-interval decision: **N≈5 in PR CI** (cheap signal), **N≈20–30 nightly**, **N≈50+ release/bake-off** (Stage-7 §3.2 🔶). The rate is reported **with its Wilson interval** so "5/5" is never mistaken for "proven."
**AC-6.4 (escalate invariant failures):** The *moment* a single invariant run fails, the report surfaces that run's **full trace** (which trail, which fact, which fixture) — a reproduction, not a number to watch trend down.
**AC-6.5 (seed what can be seeded):** Where the provider supports deterministic/seeded sampling, the run records the seed so a quality regression reproduces; where it can't, N-runs *is* the instrument.
**AC-6.6:** The harness reports pass **rate** (with spread), **not** best-of-N (flatters a flaky flow) or worst-of-N (over-punishes benign variance).

### S7 — Security + privacy eval-loop invariants (`evals/security.py`)

**Given** rules #4 and #5 are the promises most dangerous to break and most invisible when broken — a leak produces no error (Stage-7 §7, decision-log §17/§28)
**When** the security criteria run
**Then** they run **both as unit tests (the base of the pyramid) and inside the eval loop across N runs** — because a leak can be sampling-dependent and must be checked across runs, not once — every one a **zero-tolerance `INVARIANT`**.

**Why:** unit tests prove the seam *can* scope; the eval-loop versions prove the *assembled, stochastic flow* never leaks in practice across the verifier/curator/judge hops. A leak that only manifests when the Curator happens to pull a particular subgraph is exactly what N-run eval catches and a single unit test misses.

**AC-7.1 (no-ungranted-node, rule #4 — READ paths only):** A property-based test (decision-log §28) fuzzes random grant sets × random viewers, asserting **every READ query path** goes through `GraphClient.scoped_session(viewer_id, granted_ids)` and a viewer with scope S **never** receives a node outside S. Uses the real `granted_ids` parameter (exists today). The eval-loop version asserts the rendered `Feed` contains **zero** nodes the scenario's viewer wasn't granted. **Pass rate must be 1.0.** ⚠️ **Scope + precondition (proposed §40 C2):** this AC covers **reads** only. Owned-node **writes** (`belief_update.py`, `ingest_episode.py`) use a raw unscoped runner with hand-typed `owner_id` and **bypass `ScopedSession`** — the fuzz test **cannot see the write path** today. Write-path fuzz coverage is a **precondition**: it requires a `run_write` on `ScopedSession` (proposed §40 C2 action) routing both writers through the seam. Until that lands, this AC must **not** claim writes are scoped; it asserts the read seam only.
**AC-7.2 (commons person-link severance, rule #5 — BLOCKED on the pending Commons Fork epic):** Three code assertions (decision-log §28 reserved-label + no-`:Person`-edge guarantee · §30 capability≠preference; status governed by proposed §40 C1): no `:CommonsObservation` is edge-reachable to a `:Person`; the forked write **severs the link in the same transaction** as the episode; **endpoint-trimming fires** (the 250m strip present, the raw track absent). Zero-tolerance. ⚠️ **Precondition (proposed §40 C1):** the commons forked write is **🔶 designed, not yet built** — `create_episode()` writes no `:CommonsObservation`, so a severance/endpoint-trim test would **vacuously pass against absent code** (a false guarantee — exactly what the gap-audit warns against). This invariant is **BLOCKED on the Commons Fork epic landing.** The test **must be written to fail-if-absent** (assert the forked-write path *exists* and produces a `:CommonsObservation`, not silently pass on an empty store). 🔶 The 250m *value* is tuned in Stage 9; this test asserts *that* it fires once the write exists.
**AC-7.3 (sensitivity-routing — BLOCKED on Stage 6 watch build):** Any flow touching the private overlay must route via the provider seam's sensitivity resolution (decision-log §29 "route by data sensitivity" + §31), forcing a **local** provider — raw FIT/HR/GPS/biometric content **never** appears in a cloud-bound prompt. A test inspects the captured prompt payloads + the resolution. ⚠️ **Precondition (proposed §40 C4):** today `engine.build_runtime` calls `resolve("extract")` / `resolve("curate")` with **no `touches_private_overlay` flag** (`engine.py:161-162`), so the overlay stays local **only under the local-first default, not structurally** — the moment a cloud curate/judge tier is configured, overlay context egresses with no error and no test failure. So the curate/judge call site that carries overlay data **must first be wired with `touches_private_overlay=True`** (the Epic 003 AC per proposed §40 C4) before this invariant can pass; otherwise the test asserts a guarantee the one overlay-carrying call site doesn't request.
**AC-7.4 (privacy-adversarial scenario):** Scenario 6 — a viewer with **no grants** (`granted_ids=()`), crafted to *try* to surface another member's episode or raw biometrics — runs the above invariants inside the eval loop across N runs, not only in unit tests. **Precondition (proposed §40 C3):** in production this invariant assumes an **authenticated** `viewer_id` — a forged `viewer_id` defeats scoping regardless of the eval, since `viewer_id` is client-supplied and unauthenticated today.
**AC-7.5 (grant-stop, Stage-8-deferred):** The grant-stop-on-provenance invariant (a grantee traverses to a *derived conclusion* but **not** the raw substrate behind the grant's stop-point, decision-log §11) is **specified here and implemented test-first in Stage 8** when grant *enforcement semantics* land. The `granted_ids` parameter already exists (used by AC-2.7/AC-7.1); only the stop-point traversal semantics are deferred. Named here so the access layer is built test-first.

### S8 — Regression matrix across engine/provider versions (`evals/regression.py`)

**Given** replay mode freezes conditions + corpus, so the **only** moving part between two runs is the thing we changed (Stage-7 §5)
**When** the regression runner walks the matrix
**Then** it produces **scenarios (rows) × `(engine_version, provider, model, tier)` (columns)**, each cell an `EvalReport` at the tier-appropriate N, with **invariant regressions as hard CI fails and quality regressions as warn-only**.

**Why:** "I can show a stochastic multi-agent flow's quality and safety trending across model swaps and code changes, with safety held to zero-tolerance and quality to a calibrated band" is precisely the platform-eval competence the project exists to demonstrate (decision-log §1).

**AC-8.1:** `run_bakeoff.py`'s `CONFIGS` is generalized from three Anthropic pairings to **any `(provider, model, tier)` from the seam — including the local-vs-cloud axis** (Stage 4 §2). The bake-off *is* the regression matrix.
**AC-8.2 (invariant regression):** Any invariant pass-rate dropping below 1.0 → **hard CI fail, blocks merge.** Non-negotiable.
**AC-8.3 (quality regression):** A quality mean dropping beyond a noise band, or its spread widening → **warn + require human sign-off**, not an auto-block (quality is noisy; a small dip can be sampling). 🔶 The noise band is **calibrated from the baseline's own run-to-run spread**, not picked by feel. ❓ Whether quality ever auto-blocks is open — recommend warn-only.
**AC-8.4 (version the eval, not just the code):** Each `EvalReport` stamps `ingest_version` (corpus), `engine_version`, provider config, **fixture-bundle hash**, judge model + **rubric version**, and N — additive metadata fields. A regression is only interpretable if the *only* thing that changed is the axis under test.
**AC-8.5 (stored baselines):** The last green report per scenario×config is committed as the comparison baseline; a PR run compares against a committed reference, **not** a flaky fresh re-run of `main`.
**AC-8.6 (the four-tier pyramid wired, Stage-7 §8):**
- **§8.3 eval-as-test:** replay harness, N≈5, `make eval` in CI; **invariants block merge, quality warns.** Judge outputs **cached, keyed on `(fixture-hash, engine-output-hash, judge-model, rubric-version)`** so a rubric/judge-model change invalidates the cache (else CI grades against a stale rubric while AC-8.4 stamps the new version). 🔶 confirm the hashing is cheap enough for the CI tier. **Net-new CI wiring:** the `make eval` target must be rewired to the replay backend with **no live `ANTHROPIC_API_KEY` and no live Neo4j** — `run_bakeoff.py` today requires both; this is new code, not a config flip.
- **§8.4 eval-as-acceptance:** **live mode**, real APIs, fresh judge, N≈20–30 nightly / N≈50+ release, the provider bake-off, **and the cost-per-session measurement** (the outstanding Stage-4 spike, decision-log §29). This live tier is the **only** place the cost spike is satisfied — replay CI deliberately spends ~no tokens and measures no cost. Not on the PR path (slow, costs tokens, needs secrets + live Neo4j).
**AC-8.7:** New modules land in the same package: `evals/scenarios/`, `evals/judge.py`, `evals/regression.py`, `evals/security.py`; `truthfulness.py` stays the thin core everything imports.

### S9 — Memory-on vs memory-off comparison hook (Stage 5/6) — BLOCKED on Epics 002/003/004

**Given** decision-log §9 commits to "evals for the memory itself — if it doesn't help, turn it off" (Stage-7 §6)
**When** the same scenario runs with personalization context injected vs empty
**Then** the delta in quality metrics is the **personalization lift**, and a **novelty/diversity** measure guards the downside.

**Why:** personalization must improve recommendations *without shrinking the world* — "memory too good at predicting you makes you smaller" (decision-log §9). The watch is enrichment (rule #6); its signal degrades-and-discloses and never becomes a dependency the feed can't render without.

**AC-9.1:** Identical origin/intent/conditions/corpus run twice — context (beliefs, party, episodes via context assembly, Epic 003) **injected** vs **empty**; the quality-metric delta is reported as personalization lift.
**AC-9.2 (honest downside):** A **novelty/diversity** measure on the feed is reported. If memory-on raises fit but collapses diversity below a floor, that is a **logged regression, not a win.** 🔶 The diversity floor needs real episode volume to set — report it, gate later.
**AC-9.3 (capability ≠ preference, rule #7):** A targeted scenario asserts watch/FIT-derived signal **only ever moves `capability` beliefs into ranking, never masquerades as a stated preference** — the eval-level enforcement of the schema-level rule (decision-log §30).
**AC-9.4:** This story is **gated on Stage 5/6 build** — Epics 001 (belief store, DONE) + 002/003 (outcome card + context assembly, DEFINED-not-built) + 004 (Garmin poller, BACKLOG). When personalized context carries overlay data into the curate/judge call, AC-7.3's `touches_private_overlay=True` precondition (proposed §40 C4) must hold or memory-on scenarios would egress the overlay. The hook + scenario-5 fixture are scaffolded in this epic; full population follows those epics. The golden set must stand **without** memory (AC-3.8).

---

## Definition of Done

- [ ] All buildable-now ACs (S1–S4, S6, S8 replay-only, S7 unit half excluding AC-7.2/AC-7.3) covered by at least one passing test; the **existing** `tests/test_eval.py` passes unchanged (additive guarantee, S1)
- [ ] `make check` green (ruff + mypy + pytest)
- [ ] `make eval` rewired to the replay-mode backend (no live `ANTHROPIC_API_KEY`, no live Neo4j) and runs in CI: **invariant criteria block, quality criteria warn**
- [ ] Targeted review: verify rule #4 on every eval **read** query path (no privileged bypass; real `scoped_session(viewer_id, granted_ids)`), rule #1 invariants are code-not-judge, the judge is provider-independent, no `conditions/` fixture reaches the graph (rule #3), and `truthfulness.py`'s spine is unchanged in signature
- [ ] ~5–10 hand-built Shenandoah/GWJ golden trips committed with their cassettes + `expected.json`; Old Rag is trip #1
- [ ] Live-mode acceptance run documented (the path that satisfies the Stage-4 cost spike); **not** on the PR path
- [ ] **Blocked ACs explicitly tracked:** AC-5.6 (judge calibration), AC-7.2 (commons severance — BLOCKED on the pending Commons Fork epic, proposed §40 C1), AC-7.3 (sensitivity-routing eval-loop — BLOCKED on the §40 C4 `touches_private_overlay` wiring), and all of S9 are checked off only after the dependency epics (Commons Fork, 002/003/004) land — this epic **cannot reach DONE before them**
- [ ] AC-7.2's severance test is written **fail-if-absent** (asserts the forked write exists), never a vacuous pass against an empty store
- [ ] Committed atomically: registry seam (S1) → fixtures+golden set (S2/S3) → criteria (S4/S5/S7) → reporting (S6) → regression matrix (S8) separately
- [ ] Pushed; epic status updated; index row added to `docs/epics/README.md` for **Epic 009** (no 009 row exists there today)

---

## Implementation notes

**Epic numbering:** the **canonical epic number is 009**, and the file is `docs/epics/epic-009-eval-harness-expansion.md`. 006 (Novelty filter), 007 (Readiness filter), and 008 (API tests) are already taken in `docs/epics/README.md` — an earlier draft mis-filed this as 007, which collides with Readiness. The H1, README row, and all cross-refs use **009**.

**Citation precision (memory hygiene):** every `decision-log §N` cite in this epic is to N ≤ §31, which is the committed `docs/decision-log.md`. All **§40 / C1–C4** references are to the **proposal file** `docs/research/decision-log-additions-proposed.md` (the committed log ends at §31) — cited as "proposed §40 Cn", never as if already in the committed log. Engine shape / cost lever / provider seam = §29; schema / migration / access-invariant = §28 — not swapped.

**New modules (same `evals/` package, Stage-7 §9 ✅):**
- `evals/scenarios/<name>/` — `intent.json` + `viewer.json` + `conditions/` (replay cassette) + `expected.json` (golden ground truth). The integration-tier mocked adapter responses (decision-log §17/§29) are the **seed corpus** for these cassettes — capture once, reuse as both integration mock and eval cassette.
- `evals/judge.py` — the rubric + `ScoredJudge` (defensive parse modeled on `curator._parse_ids`).
- `evals/regression.py` — the matrix walk + committed-baseline diff + version stamping.
- `evals/security.py` — the §7 eval-loop invariants (no-ungranted-node **read**-path, commons-severance fail-if-absent, sensitivity-routing).

**`truthfulness.py` changes (all additive):** the criteria registry (S1), `ScoredJudge` alongside the retained boolean `Judge`, per-class threshold-aware `passed()` + spread/interval/version-metadata fields on `EvalReport`, and the conditions-backend builder generalized from `run_bakeoff.py::_make_scenario` (dropping its redundant double `plan`/`plan_from_origin` call). The `fact_accuracy` criterion name is preserved.

**Open decisions to resolve during build (do not block):** quality floor (start 0.7) + regression noise band — calibrate against the baseline's own spread · N tiers — confirm against CI time + measured live token cost · judge model + hold-it-fixed-across-bake-off (recommend yes) · judge-cache key hashing cost · κ miscalibration threshold (❓) · diversity floor (needs episode volume).

**Deferred by dependency (specified, not built here):** the **commons forked write itself** (the pending Commons Fork epic, proposed §40 C1 — this epic only writes the fail-if-absent test that gates it) · owned-node **write-path** scoping (`run_write` on `ScopedSession`, proposed §40 C2 — precondition for write-side fuzz coverage) · authenticated `viewer_id` (proposed §40 C3 — precondition for the privacy-adversarial guarantee in production) · the `touches_private_overlay=True` wiring at the curate/judge call site (proposed §40 C4 — precondition for AC-7.3) · grant-stop provenance traversal semantics (Stage 8 — note `granted_ids` *parameter* exists today) · party-merge quality metrics (Stage 8) · commons-derived quality references (Stage 9) · rendered-card structured-claim fidelity round-trip (needs a `FeedCard` structured-claim field first).
