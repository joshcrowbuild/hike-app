# Stage 7 — Evaluation Deep-Dive (design)

*Workplan Stage 7. Draft v0.1 — June 24, 2026. The hard, role-defining stage. Depends on Stages 4–6 (a real stochastic, personalized flow to evaluate). Feeds Phase 2 (regression gate for multiplayer) and the eval cross-cutting thread T4.*

> **Status: DESIGN.** Specifies the evaluation methodology for a stochastic multi-agent flow: scenario definition, N-run pass rates, regression across engine/provider versions, the deterministic-vs-judge split, the golden-trip ground-truth set and its bootstrap, precise metric definitions for *truthful* and *good recommendation*, and the full four-tier test strategy (unit / integration / eval-as-test / security+privacy). It **extends the existing `evals/truthfulness.py` harness** (Stage 4 §7) rather than replacing it. Decisions in §11. Honors rules #1 (source-or-silence), #2 (confidence never penalizes rank), #3 (graph holds slow data only), #4 (access at query layer), #5 (share conclusion not substrate), #6 (watch is enrichment), #7 (provenance on every belief), #9 (no training).

> **What this produces (per workplan):** the **eval methodology for stochastic multi-agent flows** (scenario definition · N-run pass rates · regression across versions · the LLM-judge for the soft half) · the **golden-trip ground-truth set** + bootstrap · the **full test strategy** (unit / integration / eval-as-test / security+privacy) · precise **metric definitions** for *truthful* and *good recommendation*.

> **Legend:** ✅ decided · 🔶 recommended, confirm · ❓ open question to resolve.

---

## 1. The framing — why this stage is hard, and the one idea that makes it tractable

The flow under test is **non-deterministic by construction**: Scout returns a corpus subset, the Verifier overlays live conditions that *genuinely change between runs* (weather at 10:00 ≠ weather at 10:10), and the Curator's taste ranking is an LLM call whose output varies even at fixed input. A single run tells you almost nothing — a green run can hide a 1-in-5 truthfulness violation, and a red run can be a transient API outage. **You cannot assert equality against a golden output, because there is no single correct output.** This is the exact problem the target role names (evals for stochastic multi-agent workflows); getting it right is the whole point of the stage.

**The idea that makes it tractable: separate *what must be invariant* from *what is allowed to vary*, and evaluate each with the right instrument.**

- **Invariants** (rules #1–#9 made testable) hold on *every* run, deterministically. A flash-flood trail surfacing is a hard fail, full stop, regardless of how good the rest of the feed is. These need **no judge** — they are code predicates over the typed `Feed`/`PlannedTrail` output, and they extend the two predicates the harness already has (`source_or_silence_ok`, `no_blocked_surfaced`).
- **Quality** (was this a *good* recommendation?) is inherently soft and run-varying. It needs an **LLM-judge** against a rubric and the golden set, and it is reported as a **distribution over N runs**, never a single number.

This is the same hard/soft split the project already commits to in the engine itself (Decision Log §9: constraint = Verifier filter, violation = bug; taste = Curator ranking, miss = soft loss). **The eval mirrors the architecture it evaluates** — the deterministic half tests the deterministic half, the judge tests the judged half. That symmetry is not cosmetic; it is why the metric definitions in §4 fall out cleanly.

**The unit of evaluation is the N-run *pass rate*, not the run.** ✅ The existing `CriterionResult.rate = passes / runs` is already this; Stage 7 widens what gets measured and how thresholds are read (§3).

---

## 2. Scenario definition — the contract for a reproducible-enough run

A **scenario** is the fixed left-hand side of the evaluation: everything we hold constant so that the only thing varying is what we are trying to measure (model sampling + genuinely-live conditions). The existing `Scenario(name, run)` is the seam; Stage 7 specifies what a principled `run` must pin down.

### 2.1 What a scenario fixes (the inputs)

| Input | How it's pinned | Why |
|---|---|---|
| **Origin + radius** | Literal lat/lon + radius_m (e.g. the Old Rag pilot point already in `run_bakeoff.py`) | Scout's spatial query is then deterministic given a frozen corpus |
| **Corpus snapshot** | A **pinned `ingest_version`** of the Shenandoah/GWJ graph (Stage 2 §versioning) | The corpus must not drift mid-eval; regression must isolate *engine* change from *data* change |
| **Query / intent** | Literal query string + (Stage 5) a fixed party + profile fixture | Holds the personalization context constant |
| **Viewer scope** | A fixed `viewer` passed to `GraphClient.scoped_session(viewer)` → `ScopedSession`, scoping on `owner_id` (rule #4) | Eval runs through the *same* access seam as production — never a privileged bypass |
| **Grant set** *(Stage-8-gated)* | A fixed grant fixture once grants land | Pinnable only after Stage 8; until then the viewer sees own-scope + world nodes |
| **Live data** | **Two modes — see §2.2** | The crux: live conditions are the irreducible source of run-to-run variance |
| **Provider config** | `(provider, model, tier)` from config, recorded in the report | Makes provider/version the regression axis (§5) |

### 2.2 The two live-data modes — the central methodological choice ✅

Live conditions are the one input we cannot freeze in the world, so the harness must offer two evaluation modes and use each for its purpose:

- **Replay mode (deterministic conditions).** The Verifier's adapters are backed by **captured fixtures** — a recorded NWS/USGS/FIRMS/AirNow/RIDB response set, timestamped, stored with the golden trip. In replay mode the *only* remaining variance is LLM sampling. **This is the mode that runs in CI** (eval-as-test, §8.3): it is hermetic, free (no live API calls; judge outputs cached, §8.3), fast, and reproducible. It is how regression across engine/provider versions is measured cleanly — same fixtures, different code/model, compare pass rates.
- **Live mode (real conditions).** The adapters hit the real APIs. This is the **acceptance / bake-off mode**, run on demand and on a schedule, not in PR CI. It is the only mode that catches adapter drift, real outages, and source-of-truth changes — and it is where the *truthful* metric earns its keep, because "matches the live data the adapter returned" (§4.1) is only meaningful against data that genuinely just came back. It is also the **only** mode that measures real token cost (§8.4) — replay/cached CI spends ~no tokens and so measures nothing about cost.

> **Why both, not one:** replay alone can't catch "the NWS schema changed and our adapter silently mis-parses it"; live alone can't give a stable regression signal because the world moved. The split is the same `corpus-vs-live` discipline the whole system is built on (Decision Log §4), applied to the eval. **Rule #3 holds:** the captured conditions bundle lives under `evals/scenarios/.../conditions/` as a fixture artifact — never as graph nodes — exactly as live data is JIT-overlaid in production, never persisted.

🔶 **Fixture capture is a first-class artifact.** Each golden trip (§3) ships with a captured adapter-response bundle (the "VCR cassette"). A nightly job re-captures fresh bundles so replay-mode conditions don't rot into implausibility, and a diff between an old and new bundle is itself an adapter-drift alarm.

### 2.3 Scenario taxonomy — what set of scenarios we need

A handful of scenarios, each targeting a distinct failure mode (not just "happy path × N"):

1. **Nominal** — benign conditions, several valid candidates. Baseline truthfulness + quality.
2. **Guardrail-trip** — fixtures inject a flash-flood alert / AQI ≥ 201 / closed permit on a *high-taste* trail. Asserts the hard filter fires (#2's "constraint = bug") *and* that a low-confidence-but-safe trail is **not** buried (the §4.2 anti-suppression metric).
3. **Sparse / cold** — an obscure trailhead with thin corpus facts and no crowd data. Asserts graceful degradation (Decision Log §3 axes) and that hedged phrasing fires, not silence-everywhere.
4. **Adapter-outage** — one or more fixtures return `None` / error. Asserts degrade-and-disclose (#6 analog for live data): the feed still renders, the missing fact is flagged, nothing is fabricated.
5. **Personalized (Stage 5/6)** — fixed party + belief fixtures. The base for the **memory-on vs memory-off** comparison (§6).
6. **Privacy-adversarial** — a viewer with no grants; a scenario crafted to *try* to surface another member's episode or raw biometrics. Asserts the security/privacy invariants (§7) inside the eval loop, not only in unit tests.

🔶 Start with scenarios 1–4 (Phase-0-shaped, single-user); add 5–6 as Stages 5/6/8 land. Scenarios live as fixtures under `evals/scenarios/`, each a directory: `intent.json` + `viewer.json` + `conditions/` (fixture bundle) + `expected.json` (the golden ground truth, §10).

---

## 3. N-run pass rates — scoring a flow whose output changes every run

The existing harness already runs `n` times and reports `passes/runs` per criterion. Stage 7 specifies **how thresholds are read per criterion class**, because a uniform `threshold=1.0` (the current default) is correct for invariants and *wrong* for quality.

### 3.1 Two threshold regimes ✅

- **Invariant criteria → pass rate must be 1.0 (zero tolerance).** Source-or-silence, no-blocked-surfaced, no-ungranted-node, no-person-link-in-commons. A single violation in N runs fails the criterion. These are safety/legality/privacy promises (rules #1, #4, #5); a 95% pass rate on "never surface a closed-by-flash-flood trail" is a failure, not a B+. The harness's current `passed(threshold=1.0)` is exactly right for this class — Stage 7 just labels these criteria as *invariant* so the report can hold them to 1.0 unconditionally.
- **Quality criteria → pass rate against a tuned floor + a stability bound.** "Good recommendation" (§4.2) is judged per run and passes the *scenario* if (a) the mean judge score clears a floor (🔶 start 0.7/1.0) **and** (b) the run-to-run variance is bounded (a flow that's brilliant half the time and incoherent the other half is a worse product than a steadily-good one). Report **mean, the floor-pass rate, and the spread** (p10/p90 or stdev), not a point estimate.

### 3.2 Choosing N, and reading the rate honestly 🔶

- **N is a confidence-interval decision, not a magic number.** A pass rate from N=5 (the current default) has a wide Wilson interval — fine for a fast PR smoke gate, useless for certifying an invariant. **Use a tiered N:** N≈5 in PR CI (cheap signal), N≈20–30 nightly, N≈50+ for a release-certification or provider-bake-off run. Report the rate *with its interval*, so "5/5" is never mistaken for "proven."
- **Invariant violations get escalated, not averaged.** Because invariants are zero-tolerance, the report should surface the **failing run's full trace** (which trail, which fact, which fixture) the moment a single failure occurs — a rate of 19/20 on an invariant is a P0 with a reproduction, not a number to watch trend down.
- **Seed what can be seeded.** Where the provider supports deterministic sampling (a temperature-0 / seeded mode), the eval records it so a quality regression can be reproduced. Where it can't (genuine sampling variance), N-runs *is* the instrument — that's the point.

> **Why pass *rate* and not best-of-N or worst-of-N:** best-of-N flatters a flaky flow; worst-of-N over-punishes benign variance. The *rate* (with its spread) is the honest summary of a stochastic system, and it's already the harness's native shape.

---

## 4. Metric definitions — precisely what *truthful* and *good recommendation* measure

This is the heart of the stage. The two halves map to the two threshold regimes (§3.1) and the two evaluation instruments (deterministic predicate vs LLM-judge).

### 4.1 TRUTHFUL — the hard half (deterministic, invariant, zero-tolerance)

*"Truthful"* is **fully decidable in code** against the typed output + the captured adapter bundle. No judge produces a truthfulness verdict for the invariant core (a judge only assists with the one fuzzy sub-check, §4.1d). Five sub-metrics, all rate-must-be-1.0:

a. **Source-stamped** *(extends `source_or_silence_ok`)* — every surfaced fact carries a non-empty `source` and a non-null `fetched_at`. Already implemented; unchanged.

b. **Fidelity (no drift between fact and source)** — every surfaced fact's *value* equals what the adapter actually returned for that run (replay: equals the fixture; live: equals the captured response). This catches the subtle failure the current harness leaves to the optional judge: the LLM **phrasing** a verified fact must not *alter* it ("creek low" when the gauge said high). **Where the fidelity check actually attaches:** assert it on `PlannedTrail.facts` (the raw `VerifiedFact`s, available pre-phrasing from `plan_from_origin`) against the adapter bundle — this is the clean, currently-available hook and it is a pure code assertion for numeric facts (flow, AQI, temp, distance), since `VerifiedFact.value` *is* the structured value. The *rendered-card* round-trip (back from a `FeedLine` to the structured claim) is **not** available today — `FeedCard` carries `lines: list[FeedLine]`, not the structured fact — so 🔶 a structured-claim field on the card is required before the card-level check exists, and it is only needed for the **LLM-phrasing** path (where templated `present.py` phrasing is already pre-verified). Until then, fidelity is asserted pre-card; the LLM-phrasing semantic-equivalence confirmation is the scoped-judge check in 4.1d.

c. **Guardrail integrity** *(extends `no_blocked_surfaced`)* — no trail with `verdict.blocked` reaches the feed; **and** every active hard-threshold condition (flash-flood/red-flag/AQI≥201) that *should* block, did. The current predicate only checks the first half (no blocked trail surfaced). The converse ("every condition that should block, did") cannot be derived by re-running engine code — that would test the guardrail with the guardrail (circular). **It depends on the golden `expected.json` carrying the must-be-blocked set** (§10.1), hand- or semi-auto-labeled from the fixture bundle. The check is then: rendered feed ∩ expected-blocked-set = ∅. This catches a guardrail that silently stopped firing.

d. **Disclosure completeness** — every fact whose `confidence_inputs` put it below the floor, or that carries adapter `disclosures` (nearest-gauge distance, FIRMS "thermal anomaly ≠ fire", AirNow "preliminary"), is rendered **with** its hedge/flag, not as a plain stated fact (rule #1's gradient; Decision Log §7). The *presence* of the disclosure string is a code check; whether the hedge *reads* honestly, and whether LLM-phrasing preserved a fact's meaning (4.1b), is the one place a **scoped LLM-judge** assists — but its failure is a quality issue, not an invariant.

e. **No-fabrication on absence** — when an adapter returns `None` (outage/sparse), the card shows no manufactured value for that fact. A code assertion that the set of rendered facts ⊆ the set of non-`None` adapter returns. This is source-or-silence's contrapositive and the adapter-outage scenario's (§2.3) acceptance check.

> **Why truthful is code, not judge:** truthfulness is the project's non-negotiable #1. A promise that critical must be tested by something that itself can't hallucinate. An LLM-judge is appropriate for *taste*; it is the wrong instrument for *"did we fabricate a fact,"* where we have the ground truth (the adapter bundle) sitting right there. The judge's role in the truthful half is confined to semantic-equivalence of *phrasing* (4.1b/d), never to deciding whether a fact is sourced.

### 4.2 GOOD RECOMMENDATION — the soft half (LLM-judge, quality regime)

*"Good recommendation"* is genuinely subjective and run-varying, so it is scored by an **LLM-judge** (judgment tier — Opus-class as the yardstick) against a **rubric + the golden trip's expected set**, and reported as a distribution (§3.1). Sub-metrics:

a. **Relevance / fit** — do the surfaced trails match the scenario's stated intent and constraints (radius, effort, dog, type)? Judge scores each card against `intent` + the golden trip's plausible-set. (Hard constraint *violation* is already a code fail in 4.1c; this measures soft fit above that floor.)

b. **Ranking sanity** — is the order defensible for this hiker/party? Judged against the golden set's expert ordering as a *reference, not a key* (a different-but-defensible order is not a miss).

c. **Anti-suppression (rule #2, made measurable)** — a deliberately-inverted check: does a **low-confidence-but-safe-and-relevant** trail appear at a rank justified by its merits, *not* buried for being uncertain? The judge is given two cards identical except for confidence and must confirm the low-confidence one is not down-ranked *for that reason*. **This is the metric that operationalizes the project's most distinctive non-negotiable** — confidence shapes *how honestly* a trail shows, never *whether* it ranks. It directly protects the lesser-traveled trails the product makes first-class (Decision Log §3).

d. **Calm-utility tone** — does the card read as a calm, hedged-where-appropriate utility, not engagement-bait or false confidence? Judge against a short rubric drawn from the product stance (Decision Log §19 / #non-negotiables).

e. **Personalization lift (Stage 5/6)** — see §6; the memory-on vs memory-off delta is itself a metric.

### 4.3 The judge, kept honest

- **Rubric-anchored, structured output.** The judge returns a per-criterion score + a one-line *justification* (the justification is the audit trail, mirroring the system's own "provenance on every belief" ethos — the judge's verdict is itself sourced). 🔶 Structured JSON scores, parsed defensively exactly as `curator._parse_ids` already does (graceful fallback on malformed output).
- **Provider-independent judging.** The judge config is separate from the engine's provider config, so we never grade a model with itself when that would flatter it; the bake-off (§5) can hold the judge fixed while varying the engine provider.
- **Judge calibration is itself evaluated.** Periodically score the judge against human labels on a slice of the golden set (§10.3); report judge↔human agreement (e.g. Cohen's κ). A judge that drifts from human taste is a measurement-instrument bug. 🔶 This is the "evals for the eval" guard the role cares about.
- **No training (#9).** The judge is prompted + rubric-anchored; we never fine-tune it on our outcomes. Pure orchestration.

---

## 5. Regression across engine/provider versions

Because replay mode (§2.2) freezes conditions and corpus, the **only** moving part between two eval runs is the thing we changed — engine code or provider config — which is exactly what makes regression legible.

- **The regression matrix:** scenarios (rows) × `(engine_version, provider, model, tier)` (columns), each cell an `EvalReport` (the existing type), run at the tier-appropriate N. The bake-off runner (`evals/run_bakeoff.py`) already walks configs and prints per-criterion bars; Stage 7 generalizes its `CONFIGS` from "three Anthropic model pairings" to "any `(provider, model, tier)` from the seam — including the **local-vs-cloud** axis the whole project is built around (Stage 4 §2). The **live-mode** runs of this matrix (§8.4) *are* the provider bake-off the cost spike needs; the replay-mode CI runs (§8.3) give the safety/quality regression signal but measure no cost.
- **What counts as a regression:**
  - **Invariant regression** (any invariant pass-rate drops below 1.0) → **hard CI fail, blocks merge.** Non-negotiable.
  - **Quality regression** (a quality metric's mean drops beyond a noise band, or its spread widens) → **warn + require human sign-off**, not an auto-block, because quality is noisy and a small mean dip can be sampling. 🔶 The noise band is calibrated from the baseline's own run-to-run spread.
- **Versioning the eval, not just the code.** Each report records `ingest_version` (corpus), `engine_version`, provider config, fixture-bundle hash, judge model + rubric version, and N. A regression is only interpretable if you can prove the *only* thing that changed is the axis under test. 🔶 Stamp these onto `EvalReport` as metadata fields (an additive extension, §9).
- **Baselines are stored, not recomputed.** Keep the last green report per scenario×config as the comparison baseline so a PR run compares against a committed reference, not against a flaky fresh re-run of `main`.

> **Why this is the role-defining artifact:** "I can show a stochastic multi-agent flow's quality and safety trending across model swaps and code changes, with safety held to zero-tolerance and quality held to a calibrated band" is precisely the platform-eval competence the project exists to demonstrate (Decision Log §1).

---

## 6. The memory-on vs memory-off eval (Stage 5/6 hook)

Decision Log §9 commits to "evals for the memory itself — if it doesn't help, turn it off." Stage 7 makes this a first-class comparison, not a one-off:

- **Same scenario, two runtimes:** identical origin/intent/conditions/corpus, with the personalization context (beliefs, party, episodes via `context_assembly`) **injected** vs **empty**. The delta in §4.2's quality metrics is the **personalization lift**.
- **Honest accounting of the downside (#6):** the explore/exploit concern (Decision Log §9 — "memory too good at predicting you makes you smaller") gets its own metric: a **novelty/diversity** measure on the feed. If memory-on raises fit but collapses diversity below a floor, that's a logged regression, not a win. Personalization must improve recommendations *without* shrinking the world. The watch is enrichment (#6) — its signal degrades-and-discloses and never becomes a dependency the feed can't render without.
- **Capability ≠ preference, tested (#7).** A targeted scenario asserts watch/FIT-derived signal only ever moves `capability` beliefs into ranking, never masquerades as a stated preference — the eval-level enforcement of the schema-level rule (Decision Log §30).

---

## 7. Security + privacy tests — the two hardest promises, as eval invariants

Rules #4 and #5 are the promises most dangerous to get wrong and most invisible when broken (a leak produces no error). Decision Log §17 already names these as required; Stage 7 specifies them as **deterministic, zero-tolerance invariants that run both as unit tests (§8.1) and inside the eval loop (scenario 6, §2.3)** — because a leak can be sampling-dependent, so it must be checked across N runs, not once.

- **No-ungranted-node (rule #4).** A property-based test (Decision Log §28 already calls for this) that *every* query path goes through `GraphClient.scoped_session(viewer)` (→ `ScopedSession`, scoping on `owner_id`) and that a viewer with scope S **never** receives a node outside S — fuzzed over random grant sets and random viewers. The eval-loop version asserts the same on the real feed output: the rendered `Feed` contains zero nodes the scenario's viewer wasn't granted. **Pass rate must be 1.0.**
- **Commons person-link severance (rule #5 / Decision Log §12).** Assert that no `:CommonsObservation` is ever edge-reachable to a `:Person` (Decision Log §28's reserved-label guarantee), that the forked write severs the link in the *same transaction* as the episode (Decision Log §31), and that **endpoint-trimming actually fires** (the 250m strip is present, the raw track is absent). These are the three concrete checks §17 enumerates; each is a code assertion, zero-tolerance.
- **Sensitivity-routing (Stage 6).** Assert that any flow touching the private overlay resolved its provider via `resolve(role, settings, touches_private_overlay=True)` and that the returned `Resolution.forced_local` is `True` (equivalently, the resolved provider is `local`), i.e. raw FIT/HR/GPS/biometric content never appears in a cloud-bound prompt. A test that inspects the captured prompt payloads + the resolution. (Decision Log §31's `route(sensitivity="private")` is the log's shorthand; the real seam is `resolve(..., touches_private_overlay=True)` — `orchestration/providers/registry.py`.) This protects the "personal data never leaves the machine" promise (Stage 4 §2 / Decision Log §31).
- **Grant-stop on provenance (rule #5).** When Stage 8 lands grants, assert that a grantee can traverse to a *derived conclusion* but **not** to the raw substrate behind the grant's stop-point (Decision Log §11). Deferred to Stage 8, but the invariant is specified now so the access layer is built test-first.

> **Why these belong in the eval, not only in unit tests:** unit tests prove the seam *can* scope; the eval-loop versions prove the *assembled, stochastic flow* never leaks in practice across N runs and across the judge/curator/verifier hops. A leak that only manifests when the Curator happens to pull a particular subgraph is exactly the kind of bug N-run eval catches and a single unit test misses.

---

## 8. The full test strategy — four tiers, one pyramid

Decision Log §17 lists the types; Stage 7 makes the pyramid and the boundaries explicit. The existing `tests/` tree (unit/integration) is the base; the eval harness is the apex.

### 8.1 Unit (fast, deterministic, no I/O) — the base
Extractors, taggers, conflation mergers, confidence computation, guardrail thresholds, `present.py` phrasing, the access-seam param-scoping, the commons-severance + endpoint-trim functions. Already populated (`test_curator.py`, `test_confidence.py`, `test_conflate.py`, …). **The security/privacy *unit* tests (§7) live here** as their first line of defense. Runs on every commit; must be sub-second-ish.

### 8.2 Integration (adapters with mocked/recorded responses)
Each live adapter against **mocked responses + outage/rate-limit handling** (NWS fair-use, AirNow 500/hr, FIRMS 5000/10min, RIDB ~50/min — Stage 4 §5; Decision Log §17). Asserts degrade-and-disclose, never-fabricate, never-block. **These mocked responses are the seed corpus for replay-mode fixtures (§2.2)** — capture once, reuse as both integration mocks and eval cassettes. Graph queries against an ephemeral test Neo4j (or the injectable `runner` fake the client already supports). No real network in CI.

### 8.3 Eval-as-test (the harness in CI) — the apex
The truthfulness + quality harness, **replay mode**, N≈5, on the golden set, **runnable in CI via `make eval`** (the Makefile target + `run_bakeoff.py` already exist). Gates: **invariant criteria block merge; quality criteria warn.** This is the eval-as-test the project committed to (T4 / Decision Log §17) — regression protection on every change without spending tokens on live calls (judge outputs cached for the CI tier; a fresh-judge run is the nightly tier). **The judge-output cache is keyed on `(fixture-hash, engine-output-hash, judge-model, rubric-version)`** so a rubric or judge-model change invalidates it — otherwise the CI gate would silently grade against a stale rubric while §5's report still stamps the new `rubric version`. 🔶

### 8.4 Eval-as-acceptance (live mode, scheduled) — above CI
Live-mode runs (real APIs, fresh judge), N≈20–30 nightly and N≈50+ at release, including the **provider bake-off** (local vs cloud, §5) and the **cost-per-session measurement** (the outstanding Stage-4 spike — Decision Log §29). **This live tier is the *only* place the cost spike is satisfied** — it is where real tokens are spent and real cost/quality/latency numbers come back; the replay CI tier (§8.3) deliberately spends ~no tokens and measures no cost. Not on the PR path (slow, costs tokens, needs secrets + live Neo4j). Produces the regression matrix (§5) and the cost/quality/latency numbers the cost model still owes.

```
        ╱ 8.4 live acceptance + bake-off (scheduled, real APIs, $$, the cost spike) ╲
       ╱  8.3 eval-as-test: replay harness, N≈5, CI gate (invariants block, quality warns) ╲
      ╱   8.2 integration: adapters w/ recorded responses (= cassettes) ╲
     ╱    8.1 unit: extractors · confidence · guardrails · access · commons ╲
```

---

## 9. How this extends `evals/truthfulness.py` (additive, not a rewrite) ✅

The existing harness is the right spine; Stage 7 grows it without breaking it. Everything below is **additive** — current call sites (`test_eval.py`, `run_bakeoff.py`) keep working.

- **Keep as-is:** `Scenario(name, run)`, the `Run` type alias, `CriterionResult` + its `.rate`, `EvalReport`, `evaluate(scenario, n, *, judge)`, `source_or_silence_ok`, `no_blocked_surfaced`. The N-runs-and-report-a-rate spine is exactly the stochastic instrument Stage 7 needs — it was built for this. (`Judge` is *not* in this list — it is generalized below.)
- **Generalize the criteria registry.** Today `evaluate` hardcodes two predicates + an optional judge into a `counts` dict. Replace the hardcoded set with a **list of registered criteria**, each tagged `INVARIANT` or `QUALITY` and carrying its own predicate-or-judge. `source_or_silence_ok` and `no_blocked_surfaced` register as the first two `INVARIANT` criteria — same behavior, now extensible. Add the §4.1 invariants (fidelity, disclosure-completeness, no-fabrication, guardrail-fired, no-ungranted-node, commons-severance) and the §4.2 quality criteria (relevance, ranking-sanity, anti-suppression, tone) as further registrations.
- **Retain the `fact_accuracy` criterion.** The current optional judge registers a single criterion literally named `fact_accuracy` (`truthfulness.py` L67–77), which `test_eval.py` asserts on by name. Stage 7 **keeps `fact_accuracy` as the name of the fidelity/semantic-equivalence judge criterion** (it *is* §4.1b/4.1d's phrasing check) so the existing test resolves unchanged; the new §4.2 quality criteria are *added alongside* it, not in place of it. The degenerate single-boolean `judge` path stays supported (below), so `fact_accuracy` continues to register and score exactly as today when only the boolean judge is supplied.
- **Make `EvalReport` threshold-aware per criterion class.** `passed()` currently takes one global `threshold`. Extend so **invariant criteria are held to 1.0 unconditionally** and **quality criteria to their tuned floor**, and add the spread/interval fields (§3) and the version-metadata stamp (§5) as additive fields. `passed(threshold=1.0)`'s existing call sites still resolve (invariants already want 1.0).
- **Replace the binary `Judge` with a scored, multi-criterion judge.** Current `Judge = Callable[[list[PlannedTrail]], bool]` collapses all quality to one boolean. Add a `ScoredJudge` returning per-criterion scores + justifications (§4.3), parsed defensively. The old boolean `judge` stays supported as a degenerate single-criterion case (registering `fact_accuracy`) so `test_eval.py` still passes.
- **Add the conditions-mode seam.** The harness already takes `run` as an opaque callable; Stage 7 standardizes a `run` builder that takes a **conditions backend** (replay-fixture vs live-adapter), so the *same* scenario runs in both modes (§2.2). The bake-off runner's `_make_scenario` is the template — generalize it to accept the backend.
- **Promote `run_bakeoff.py`'s `CONFIGS` to the full provider seam.** From three Anthropic pairings to any `(provider, model, tier)` including local — turning the bake-off into the local-vs-cloud regression matrix (§5) and the cost spike's instrument (live mode, §8.4).
- **New modules, same package:** `evals/scenarios/` (fixtures + cassettes + golden `expected.json`), `evals/judge.py` (rubric + `ScoredJudge`), `evals/regression.py` (matrix walk + baseline diff), `evals/security.py` (the §7 eval-loop invariants). `truthfulness.py` stays the thin core everything imports.

> **Why additive:** the harness already encodes the two hardest ideas — *stochastic ⇒ report a rate* and *invariants are code predicates, quality is a judge*. Stage 7 is not a redesign; it is widening the criteria set, splitting the threshold regime, scoring the judge, and adding the replay/live + regression machinery around an unchanged core.

---

## 10. The golden-trip ground-truth set & its bootstrap

The set is the reference both metrics lean on; it is the long-pole asset of the stage. Decision Log §17 names the open question ("where do known-outcome trips come from?") and the answer ("bootstrap from your own logged/watch trips").

### 10.1 What a golden trip contains ✅
A directory per trip under `evals/scenarios/`:
- **The scenario inputs** (§2.1): origin, radius, intent, viewer/party fixture, pinned `ingest_version`.
- **A captured conditions bundle** (§2.2): the recorded adapter responses, timestamped — the replay cassette.
- **`expected.json` — the ground truth, split to match the two metrics:**
  - **Hard expectations (for the truthful metric):** the exact source + value each surfaced fact *must* carry given the bundle; **the must-be-blocked trail set** (this is what makes the §4.1c guardrail-converse check non-circular — it is a label in the cassette, not a re-run of engine code); which disclosures *must* appear. The fact-value expectations are derivable from the bundle + the rules, so they're semi-auto-generated; the must-block set is hand- or semi-auto-labeled.
  - **Soft expectations (for the quality metric):** a **plausible-set** of acceptable trails (not a single answer — there is no single right feed), a *reference* ranking, hiker/party notes, and any "this trail should clearly be surfaced / clearly excluded" anchors. Hand-curated; the judge scores *against* these, treating them as reference not key (§4.2).

### 10.2 Bootstrap, in dependency order 🔶
1. **Phase 0 — hand-built pilot trips (now).** A handful (~5–10) of Shenandoah/GWJ trips with hand-verified expected facts (Stage 4 §7 already started this; `run_bakeoff.py`'s Old Rag point is trip #1). Conditions captured live once, frozen as cassettes. This is enough to stand up §8.3 immediately.
2. **Phase 1 — promote real watch trips (Stage 6 output).** Every FIT-parsed `Episode` (Decision Log §31) is a *real known-outcome trip with a measured result* — pace, stops, ascent, the post-hike `Outcome`. **This is the high-quality bootstrap the log points to:** an episode + its outcome is ground truth the system didn't invent. A promotion path turns selected episodes into golden trips (de-identified, scrubbed of biometrics per #5 before they enter the shared eval set). The watch closes the predict→go→outcome→eval loop (Decision Log §10) — measurement, not inference. Watch data is enrichment (#6): the golden set must stand without it.
3. **Phase 3 — commons-derived *quality* references (Stage 9).** Once the commons has volume, empirical pace/effort-topology (Decision Log §12) becomes a reference for the **quality** metric's plausible-set / reference-ranking ("does our predicted pace sit inside the aggregate band?") — **not** for the invariant *truthful* metric. The truthful metric is defined (§4.1) as zero-tolerance equality against the adapter bundle *that ran this run*; a slow, derived commons aggregate is a different kind of reference and cannot serve as a hard-equality truthful check without contradicting §4.1's own definition. It feeds soft expectations only, above the k-floor so it's both private-safe and trustworthy.
4. **Synthetic edge cases throughout.** Hand-authored fixture bundles for conditions you can't reliably catch in the wild (a flash-flood + a permit-closure + a smoke event at once) — these power the guardrail-trip and adversarial scenarios (§2.3) without waiting for the weather.

### 10.3 Keeping the golden set honest 🔶
- **Conditions cassettes are refreshed nightly** (§2.2) so replay-mode plausibility doesn't rot; a cassette diff is an adapter-drift alarm.
- **A human-labeled slice** is held back to calibrate the judge (§4.3) — the only place humans score directly, and the reference for judge↔human agreement.
- **Golden expectations are versioned with the corpus** (`ingest_version`): when the corpus refreshes monthly and a trail's geometry changes, its expected facts may legitimately change — a stale golden set is wrong memory (CLAUDE.md's "wrong memory is worse than none"), so golden trips carry an expiry/review stamp.

---

## 11. Open decisions (🔶/❓) & deferrals

**Recommended, confirm (🔶):**
- Quality-metric floor (start 0.7) and the regression noise band — **calibrate against the baseline's own spread**, don't pick by feel.
- N tiers (5 PR / 20–30 nightly / 50+ release) — confirm against CI time budget and token cost once live-mode token cost is measured.
- Endpoint-trim distance (250m, inherited from Stage 5/6) — the privacy test asserts *that* it fires; the *value* is tuned in Stage 9.
- Judge model + whether to hold it provider-fixed across the bake-off (recommend yes, to avoid self-grading flattery).
- The novelty/diversity floor for the memory-on downside (§6) — needs real episode volume to set.
- Judge-output cache key `(fixture-hash, engine-output-hash, judge-model, rubric-version)` (§8.3) — confirm the hashing is cheap enough for the CI tier.

**Open (❓):**
- Exact judge↔human agreement threshold (κ) below which the judge is "miscalibrated and must be re-prompted."
- Where the live-acceptance schedule runs once always-on infra exists (Stage 8 dependency) — nightly on the poller host is the natural home.
- Whether quality regressions ever auto-block (recommend warn-only) or always require human sign-off.

**Deferred (by dependency):**
- Grant-stop provenance privacy invariant (§7) — specified now, **implemented test-first in Stage 8** when grants land. The `granted_ids` scenario input (§2.1) is likewise Stage-8-gated.
- Party-merge quality metrics ("minimize the bigger disappointment") — Stage 8.
- Commons-derived quality references (§10.2.3) — Stage 9, gated by volume + the T6 consent/ODbL gate.

---

## 12. ◆ Stage-7 design checkpoint

The methodology is specified end-to-end: a **stochastic flow scored by N-run pass *rates*** over a **replay/live conditions split**; an **invariant half tested in code at zero tolerance** (truthful, security, privacy) and a **quality half scored by a calibrated, audited LLM-judge** against a **golden set bootstrapped from hand-built pilot trips → real watch episodes → commons-derived quality references**; **regression across engine/provider versions** (whose live-mode runs double as the outstanding cost spike, while the replay CI tier holds the safety/quality line for free); and a **four-tier test pyramid** with the eval-as-test apex gating merges on invariants and warning on quality. It **extends `evals/truthfulness.py` additively** — the harness's "report a rate, not a verdict" spine was already the right instrument; Stage 7 widens the criteria (keeping `fact_accuracy`), splits the threshold regime, scores the judge, and wraps it in the replay/regression/security machinery, naming the real seams (`scoped_session`/`owner_id`, `resolve(..., touches_private_overlay=True)`, `PlannedTrail.facts`). The next work is **build** (register the new criteria, capture the first cassettes, stand up the regression matrix), not more design — and it slots directly behind the Phase-0/Phase-1 builds it depends on (Stages 4–6).
