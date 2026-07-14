# Path to Complete — Adventure Planner

*The strategic sequencing layer above the tactical roadmap. North-star + ordering, not status.*

**Last verified:** 2026-07-13 · **Owner:** vision-PM

> **Read order.** This doc sits *one altitude above* `docs/process/roadmap.md`. The roadmap stays the **live status SSOT** (PM/planner-owned) — it says *what is built and what is next this week*. This doc says *what "complete" means and in what order we get there, and why that order*. **Do not duplicate status here**; when you want current build state, go to the roadmap. When you want the why-this-order, stay here.
>
> **Companion artifacts (same lane).** The north-star/thesis/pillars/refusals live in `docs/vision.md`; this doc operationalizes them into a buildable sequence. Design provenance for the `CDP-NN` items is `docs/research/cross-domain-pattern-library.md` + `docs/research/graph-architecture-patterns.md`; the field analysis is `docs/research/competitive-lateral-review.md`; the raw idea inbox is `docs/process/backlog-ideas.md` (B001–B009). Stage order is `docs/workplan.md`.
>
> **Grounding discipline.** Every current-state claim below was checked against `main` on 2026-07-13 (file:line where load-bearing). Where a claim is asserted-but-not-reproducible-from-`main` (the Aura corpus), it is marked as such. *Built* ≠ *defined* ≠ *aspirational*, and the three are never blurred.

---

## 1. Honest state-of-the-union snapshot

The truth is a **paradox of altitude: a beautifully-engineered engine, now live and serving real data, but still with no one personal at the wheel.** The hard part is genuinely built and faithful to the six product invariants the cross-domain research now frames as discovered law. The operational substrate is now live (hosted end-to-end, security-hardened). What is missing is what turns a faithful *live prototype* into a deeply useful *personal* application — a real intake (auth + episode creation), the correctness the product already advertises (corroboration wired but unsurfaced), and the table-stakes surface polish the UX reviews identified.

### Built (verified in code)

- **The engine.** A real code-orchestrated Scout→Verifier→Curator DAG (no agent framework): `engine.plan()` runs parse-intent → scoped-Cypher scout → drive-time isochrone prune → JIT verify → guardrail filter → context assembly → taste-rank → templated cards. Source-or-silence holds at the Verifier (None-as-absent; live readings never persisted; in-process TTLCache only). Confidence is **one** computed-on-read property (`authority × freshness × corroboration → floor + presentation + safety flag`) and is structurally **taste-blind** — `rank_ids()` takes no confidence input.
- **Corroboration wiring (CDP-01).** Corpus facts carry a real distinct-origin count: `_corpus_corroboration()` (`engine.py:320`) counts distinct `SourceRecord.source` per `SAME_AS` cluster, runs concurrently with the live-probe fan-out (`engine.py:427`), and feeds `corpus_confidence` (`engine.py:497`) — consumed by the Curator's corroboration-rescue pass (`engine.py:582`) and regression-tested in `evals/replay.py`. Live per-kind condition facts stay honestly pinned at `corroboration=1` (`engine.py:491`, `for_fact`'s default) — single-source-by-construction, not a gap (the CDP-01 spike settled this). **Not yet surfaced:** the card/API response doesn't render the corpus distinct-origin count to the user (`present.py`'s `FeedLine.sources` stays a 1-tuple for live facts).
- **The seams.** Clean swappable `ModelProvider` (LocalOpenAI + Anthropic, sensitivity-routed to force local on the private overlay) and a live-adapter seam (NWS, AirNow, FIRMS, USGS water, RIDB, Valhalla + echo), each with `from_config` self-drop on missing creds, health-driven failover, and `VerifiedFact` stamping `source + fetched_at + confidence_inputs + disclosures`.
- **Access control (the most rigorous layer).** `ScopedSession` injects `$viewer_id`/`$granted_ids` into every read; `run_write` calls `assert_scoped_write`, a boundary guard that rejects any owned-label write lacking `owner_id=$viewer_id` *before the DB*. CI proves owner isolation with **falsifiability** (an unscoped read leaks both owners) plus adversarial write fuzzing. Commons write fork is born-severed by construction.
- **Ingestion.** Config-driven `CorpusSource` seam (fail-loud on mis-declaration), three wired geometry sources (OSM/Overpass 3-mirror failover, NPS/ArcGIS, USFS bulk), a real conflation matcher with OSM-segment pre-consolidation, working 3DEP elevation (source-or-silence under 60% DEM coverage), idempotent MERGE loads.
- **API & frontend.** Four disciplined endpoints (`/health`, `/plan`, `/trail/{id}`, `/episode/{id}/outcome`); four screens (Home/Detail/Outcome/Tuning) over a swappable mock/HTTP seam with a full async envelope; the three honesty primitives (Confidence/Staleness/Signal) ship as tested, token-bound components; MapLibre topo + route + elevation profile, code-split off the feed path; 568 Python `test_` functions across 65 files (raw `def test_` count, not a `pytest --collect-only` figure — parametrization shifts the collected total); live-Neo4j CI on protected `main`.

### Defined-not-built (specced in docs, absent or inert in code)

- **Epic 006 novelty** — fully specced; `novelty_score()`/`apply_novelty_discount()` **do not exist**; self-blocked on a `been_on` producer (zero `.py` hits) and a missing `graph/migrations/` dir.
- **Epic 007 readiness** — **no epic file exists**; only a sensor seam feeding nothing; biggest remaining Phase-1 lever, safety-adjacent, solo-vs-party composition unspecified → needs a **design session before it can be DEFINED**.
- **Epic 009 eval harness** — **IN_PROGRESS**: the source-or-silence regression gate shipped (Wave 1, `evals/replay.py` + 5 golden scenarios + cassettes, hermetic, CI-gated); the deferred halves (LLM-judge, Brier hook, N-run tiers) remain unbuilt.
- **Dead/inert paths** — `intent.filters` (dog-friendly/max_length/difficulty) is parsed but consumed nowhere; water (USGS) and permits (RIDB) reach presentation only, never the guardrail. *(The outcome loop is now **closed**: Epic 002 shipped `POST /episode/{id}/outcome` with an authenticated caller; `upsert_episode` is exercised end-to-end.)*

### Aspirational / unverifiable-from-`main`

- The **Aura corpus** is now **live and verified** — the app is hosted end-to-end (Vercel → Render → Aura) and serving real data; `STATUS.md` (generated by `scripts/gen_state.py`) tracks live counts (currently ~2.2k trails, schema 0.2.0). The 2026-06-29 "cannot be confirmed from `main`" caveat is resolved by the live deployment + the `/status` endpoint.
- Stages 7/8/9/11 (deep eval, multiplayer/grants, commons read-half, native SwiftUI) are designed, none built. The two new research reviews (~260KB) are landed but **un-triaged into epics** — CDP-01..20 is design provenance, not yet metabolized.

### Doc-drift (the "wrong memory" the project forbids — fix these first, they're cheap)

| Drift | Reality on `main` |
|---|---|
| ~~`roadmap.md` says `scripts/apply_schema.py` is "untracked / commit it"~~ | **Fixed** — it is tracked; `tests/test_apply_schema.py` exists. |
| ~~Epic index shows 016 DEFINED / 017 IN_PROGRESS~~ | **Fixed** — both DONE ✅; epic headers flipped, index regenerated. |
| ~~`docs/README.md` does not route `docs/runbooks/`~~ | **Fixed** — README routes `runbooks/deploy-api-render.md` in both the read-this-for-that table and the load-on-demand list. |
| ~~Epic 008 REVIEW in index~~ | **Fixed** (2026-07-13) — 008 shipped as PR #57; index row flipped to DONE ✅. |
| ~~Corroboration framed as "unwired," a constant 1 (`engine.py:172`)~~ | **Fixed** — wired: corpus facts carry a real `SAME_AS`-cluster distinct-origin count (`engine.py:320,427,497`); live per-kind facts are honestly pinned at 1 by design (`engine.py:491`). Card/API surfacing is still open (tracked in §1 Built above). |
| ~~`_build_canonical_id` slug-collision "unguarded" below 40 chars~~ | **Fixed** — the 8-char sha1 suffix now applies unconditionally and the kept prefix is `slug[:50]` (`ingestion/pipeline.py:130-145`, shipped in Epic 030). The historical 1643→1458 delta audit + any back-fill remain open, non-blocking follow-ups (`docs/process/roadmap.md`). |
| ~~Epic 026 missing from `docs/epics/README.md`~~ | **Fixed** — index row added; `epic-026-tag-classification.md` is DONE ✅. |
| ~~Epic 008 DONE in the index with no `epic-008-*.md` file~~ | **Fixed** — index now notes it shipped (PR #57) without a dedicated epic file. |

**The one-line snapshot:** the build quality is real and invariant-faithful; the sophisticated personal-intelligence machinery runs on **mock episodes for one seeded user** because the intake is empty (no real auth, no HTTP episode creation, no history import, no search); the loudest differentiator (independence-checked corroboration) is **wired end-to-end in the engine** — corpus facts carry the real `SAME_AS`-cluster distinct-origin count, live facts an honest pinned-1 — with only the card/API surfacing left; and the operational substrate is now **live** (hosted end-to-end, serving real data, security-hardened via #166).

---

## 2. Table-stakes baseline

The roadmap's job is "what's the next epic." This baseline's job is **"what turns a faithful prototype into an honestly-shippable, deeply-useful utility — and in what order."** One ordering principle governs: **risk-of-being-live-while-blind-and-ungated comes before new-feature-surface, and both come before the multi-user front door that everything personal depends on.** The calm/private/source-honest identity is the *selection filter for how* each item is built, never a thing bolted on after.

Status legend: **absent** (no code) · **partial** (substrate present, capability inert) · **present** (built & good, maintenance only). Severity: **blocker** (must clear before the next real exposure step) · **important** · **nice-to-have**.

| Capability | Category | Status | Severity | Phase |
|---|---|---|---|---|
| Per-IP rate limiting on public `/plan` + `/trail` | security | absent | blocker | B |
| Structured logging + error tracking (Sentry) + uptime/cost alerting | observability | partial | blocker | B |
| CI security scanning (pip-audit + bandit + secret-scan) | security | partial | important | B |
| Free-text query length cap on `/plan` | security | partial | important | B |
| Privacy Policy + Terms of Service + commons-consent UI | privacy/legal | absent | blocker | B |
| Backup / DR runbook for the personal overlay | reliability | partial | important | B |
| Managed auth provider decision + real accounts | accounts/auth | absent | blocker | C |
| Sessions binding `viewer_id` to a verified token **at the query layer** | accounts/auth | partial | blocker | C |
| Password reset / social login / recovery | accounts/auth | absent | important | C |
| Preserve anonymous browsing as a first-class product through auth | accounts/auth | present | important | C |
| Authenticated episode-creation HTTP path (over `upsert_episode`) | intake | absent | blocker | C |
| Calm 3-question onboarding / first-run (writes initial profile) | onboarding | absent | important | C |
| Persisted settings + "what we believe about you" surface | settings | partial | important | C |
| Data export + deletion (GDPR/CCPA) | data-rights | absent | blocker | B→C |
| Place/destination search + geocoder seam (free input, not a 3-town enum) | search | partial | important | E |
| Interim offline / PWA (service worker + manifest, cache last plan) | offline | absent | important | E |
| In-app "report this fact / feedback" affordance | support | partial | important | E |
| Timezone / local-wall-clock correctness (the verdict names times — DST-sensitive, safety-adjacent) | correctness | absent | important | D |
| Transactional-email delivery substrate (auth recovery + data-rights both depend on it) | notifications | absent | important | B→C |
| Notifications infra — *engagement* push (deliberately none) | notifications | absent | nice-to-have | deferred |
| Privacy-respecting analytics (aggregate-only, or absent) | analytics | absent | nice-to-have | deferred |
| Monetization posture (state now, build later) | monetization | absent | nice-to-have | G |
| Performance budgets (bundle-size CI gate + `/plan` latency SLO) | performance | partial | nice-to-have | G |
| Automated a11y check (axe in the test run) | accessibility | present | nice-to-have | B (gate) |
| Maintain present strengths (validation, secrets, error/sparse states) | quality | present | nice-to-have | all phases |

**Rationale.** Four of these are *blockers* precisely because the app is **already live**: a public anonymous `/plan` endpoint fans out to **paid live APIs + LLM inference with zero rate-limiting and zero telemetry** (verified: no `slowapi`/limiter anywhere in `api/`; only `getLogger(__name__)` module loggers, no logging config / Sentry / metrics). The unmeasured R5 cost spike is unmeasured *because nothing measures it*. ToS/privacy is a **hard gate on accepting a real user's health-adjacent data**, not a nicety. Everything personal then hinges on **one decision** — the managed auth provider — which must ship recovery + social out of the box so those never become separate builds, and must **preserve anonymous browsing** (auth gates only the private overlay; the open world + live conditions stays a real un-gated product). The deferred items are deferred *with a stated posture*: their absence is partly the calm/anti-engagement identity made visible (no engagement notifications, no behavioral analytics, no ad funding). One distinction the matrix now makes explicit: **transactional-email delivery is *not* a deferrable nicety** — auth password-reset/recovery and the data-rights export both physically depend on it, so it lands as the substrate under Phase B/C, while *engagement* push is the thing we deliberately never build.

---

## 3. The integrated path

Seven phases. Each names a **goal**, **what good looks like**, **what it includes** (epics + `CDP-NN` + table-stakes), **dependencies**, and **exit criteria**. Two named milestones break the long runway into real go/no-go points. *Live status of any item lives in the roadmap; this is the why-this-order.*

### CDP disposition ledger (all 20 placed — none silently dropped)

The cross-domain register has 20 adopt-queue items. The project forbids "wrong memory," so every one is placed in a phase or explicitly deferred with a reason — no item is shipped or shelved silently.

| CDP | One-line | Phase |
|---|---|---|
| **01** | Independence-checked corroboration (walk to distinct origins) | A *(spike ✅ DONE, engine wiring ✅ DONE — `engine.py:320,427,497`; card/API surfacing still open)* |
| **02** | Three/four fact-states with loud silence | A (start) → D (finish) |
| **03** | Capture-at-boundary provenance bundle | A |
| **04** | Advisory GO/MARGINAL/NO-GO verdict, one binding constraint | D |
| **05** | Criticality as a machine field → visual weight + flags budget | D |
| **06** | Worst-rolls-up (MIN) weakest-link fusion | A |
| **07** | Two-axis trust grade (authority separate from corroboration) | A (start) → D (surface) |
| **08** | Per-data-type freshness windows, stale-while-revalidate | A (start) → E (offline-aware) |
| **09** | Capability floor buffered above the hard line | D (Epic 007) |
| **10** | Non-compensatory SCREEN then compensatory RANK + ruled-out tray | D |
| **11** | Perishable-safety watch (solo half D, party half F) | D + F |
| **12** | Permission-scoped traversal choke-point; grant-on-edge | C (auth shape) → F (grants) |
| **13** | Transitive staleness propagation | F |
| **14** | Persona/conclusion two-tier conflation; additive/reversible merges | A |
| **15** | Earn-the-right-to-interrupt (cause+consequence+time+verb) | D |
| **16** | Append-only override ledger + immutable decision-snapshot (replay) | D |
| **17** | Hedging-as-credibility / show-your-work re-derivability | D |
| **18** | Confidence-weighted implicit feedback; two-channel preference | C (Epic 006) |
| **19** | k-anonymity-gated commons aggregation | G |
| **20** | Topology-integrity gate (sourced "no route") + HMM snap | C (snap) + E (routing gate) |

*Nothing is deferred-with-no-home or rejected; if a future pass cuts one, it must say so here with a reason.*

### Phase A — Stop the lies in the substrate *(correctness & trust floor)*

**Goal.** Make every claim the engine **already renders** actually true before widening the door. Corroboration wiring has shipped (corpus facts carry a real distinct-origin count; live facts honestly pinned at 1 — `engine.py:320,491,497`), and the short-slug collision is now guarded unconditionally (Epic 030, `ingestion/pipeline.py:130-145`) — but the historical 1643→1458 delta is still un-audited row-by-row, three owned reads are guarded only by convention, and the confidence math averages instead of taking the weakest link. Fix the remaining substrate the moat stands on.

**What good looks like.** A fact confirmed by two genuinely independent origins reads "confirmed by 2 independent sources"; a single tier-1 source reads as 1 and is visibly distinguished. The 1643→1458 conflation delta is audited row-by-row with zero silent same-name merges. The three inline owned reads move into `graph/queries.py` or are covered by a CI lint. The engine emits MIN-fused (weakest-link) confidence, never an averaged middle.

**Includes.**
- **CDP-01 independence-checked corroboration — spike ✅ DONE, engine wiring ✅ DONE** ([`../research/cdp-01-corroboration-feasibility-spike.md`](../research/cdp-01-corroboration-feasibility-spike.md): moat real, locus = corpus `SAME_AS` layer). `_corpus_corroboration()` (`engine.py:320`, run concurrently with the probe fan-out at `engine.py:427`) counts distinct `SourceRecord.source` per `SAME_AS` cluster and feeds `corpus_confidence` (`engine.py:497`); live per-kind facts stay honestly pinned at `corroboration=1` (`engine.py:491`) since they're single-source-by-construction, never merged into the corpus count. The Curator's corroboration-rescue pass (`engine.py:582`) and `evals/replay.py` both exercise the real count. **Remaining:** surface the corpus distinct-origin count on the card/API — it's computed and used internally but not yet rendered to the user. AirNow remains the one genuinely-hard aggregator case (no distinct origin to recover).
- **CDP-06 weakest-link MIN fusion** — a single critical hazard caps the safety verdict; a recent ground-truth report overrides a model forecast; never averaged into a comfortable middle.
- **Slug-collision guard — ✅ DONE (Epic 030).** `_build_canonical_id` (`ingestion/pipeline.py:130-145`) now applies the 8-char sha1 suffix unconditionally (not gated on `len(slug) > 40`) and keeps `slug[:50]`, closing both collision modes for every future ingest — **(a)** short identical slugs and **(b)** long shared-prefix truncation; an in-memory same-name/same-source flag (S5) catches the genuinely-indistinguishable case the guard alone can't. **Still open, explicitly out of Epic 030's scope:** the historical **1643→1458 conflation delta** (~185 collapsed `canonical_id`s, predating the guard) is un-audited row-by-row against the live Aura corpus (the re-runnable audit script `scripts/audit_canonical_id.py` exists but hasn't been run against it), and any needed `canonical_id` back-fill for already-loaded trails is unscoped — both tracked as a non-blocking ingest follow-up (`docs/process/roadmap.md`). Every merge stays additive/reversible/degree-guarded (**CDP-14**); flag-on-ambiguous-merge.
- **M9 owned-Cypher CI lint** — move/cover the three convention-only owned reads (`context_assembly.py:71,96`; `outcome.py:88`) so an unscoped owned-label read reds the build.
- **CDP-02/08 freshness substrate (start)** + **CDP-03** capture-at-boundary provenance bundle `{source, timestamp, digest, role}` stamped by the fetch wrapper.
- **Re-runnable ingest verification (pulled up from Phase E)** — the 1643→1458 audit cannot run against the live Aura-only corpus (unverifiable from `main`), so the re-runnable ingest must land *here* to give the audit reproducible data. **And: gated on the audit outcome, a corpus re-ingest / `canonical_id` back-fill** — correcting `_build_canonical_id` *changes the `canonical_id`s of already-loaded trails*, which can orphan any `Episode`/`Belief`/grant edge keyed on the old id; the back-fill re-keys those edges (or the audit confirms no real fusion occurred and no re-key is needed). This is **not** code-only.
- **Doc-drift fixes** (cheap, load-bearing) — apply_schema "untracked" and epic-index vs roadmap on 016/017 are already fixed (see the Doc-drift table above); this pass adds the missing Epic 026 index row and notes Epic 008 shipped without a dedicated file (both `docs/epics/README.md`).

**Dependencies.** None — this is the foundation. The CDP-01 spike is **resolved** (moat real, locus = corpus `SAME_AS` layer), so corroboration ships at full strength: the wiring is done (see above); no further investigation needed. **One internal ordering:** the slug-collision audit's *data* (the live Aura corpus) isn't reproducible from `main`, so the re-runnable ingest verification (formerly a Phase-E item) must ship *first within this phase* before the audit can run and the back-fill can be scoped. *(Note: correcting `_build_canonical_id` and wiring `SAME_AS`-cluster corroboration touch the same conflation substrate — sequence the audit/back-fill before reading origin counts so corroboration counts post-corrected clusters.)*

**Exit criteria.** Corroboration is a real distinct-origin count end-to-end — corpus facts carry the `SAME_AS`-cluster origin count, live single-source facts read "single authoritative source (counts as 1)" with their origin id captured; the ingest is re-runnable from `main` and the slug-collision audit (both collision modes) passes with **zero silent same-source merges** — with any required `canonical_id` back-fill applied so no `Episode`/`Belief`/grant edge is orphaned; an unscoped owned read fails CI; MIN-fusion is the confidence math in code; the doc drifts are corrected.

### Phase B — Defend the claim & make it safe to be public *(regression gate + operational substrate)*

**Goal.** The spine invariant (source-or-silence) has **no automated regression gate against the real engine**, and the app is already deployed publicly with an unthrottled `/plan` that fans out to paid live APIs + LLM. Build the gate that defends the central claim on every PR, plus the minimum operational substrate a live, health-adjacent, multi-user utility legally and financially requires — **before any real user's data lands**.

**What good looks like.** Every PR runs golden trips + cassettes through the *real* engine and reds the build if source-or-silence breaks; `/plan` and `/health` have happy-path assertions; the frontend Vitest suite runs in CI. The public endpoint is rate-limited; cost is **measured** (R5 quantified, not hypothetical); a ToS/privacy/consent surface and data export/deletion exist; the deployed surface renders no sample data as real.

**Includes.**
- **Epic 008 (WRITE THE FILE)** — happy-path `/plan` + `/health` assertions via FastAPI `TestClient`, wired into CI.
- **Epic 009** — golden-trip set + cassettes/VCR fixtures + N-run regression gate + LLM-judge, in CI against the *real* engine; plus a **Brier/reliability calibration hook** (a 0.8 true ~80% of the time), which needs CDP-01's real corroboration to be meaningful — and now has it: the spike resolved positive, so the hook calibrates the full authority + freshness + corroboration triple against Phase A's wired distinct-origin counts.
- Wire the **frontend Vitest suite** (18 files) into CI + coverage measurement.
- **Rate-limiting on `/plan`** (slowapi) to bound the R5 cost+abuse vector; free-text query length cap folded into Pydantic validation.
- **Observability + cost metrics** — logging config, error tracking (Sentry), uptime alerting; stop the catch-all handler leaking `str(exc)`; scrub `viewer_id`/personal-overlay from logs. **Scope the R5 cost measurement to include the *standing* cost of an always-on poller host**, not just per-`/plan` request cost — because Phase D commits the solo conditions-watch, whose 24/7 re-verification cost must be a measured number *before* that commitment, not discovered after.
- **ToS / privacy / consent + data export/deletion**; `commons_opt_in` gets a real consent UI.
- **CI security scanning** — bandit + pip-audit + secret-scan.
- **Kill dummy messaging on the live deploy** — confirm `VITE_USE_MOCK` on the deployed frontend; dev-gate the sample store so the Hawksbill/Stony Man sample episodes can never reach production.
- **a11y baseline** — name WCAG-AA on the safety-relevant surface and gate it in CI (Storybook axe addon present).
- **Backup/DR runbook stub** for the irreplaceable personal overlay before real overlay data accrues.

**Dependencies.** Builds on Phase A (golden trips assert the now-correct corroboration + fused confidence). Epic 009's calibration hook needs CDP-01.

**Exit criteria.** A PR that breaks source-or-silence against the real engine reds CI; `/plan` + `/health` + frontend tests run in CI; the public endpoint is rate-limited and **cost is measured** against a real corpus + Anthropic path; a ToS/privacy/consent + data-rights surface exists. **We can now safely accept a real user's data.**

### Phase C — Fill the empty intake *(auth + episodes + history import: make it real for ONE real user)*

**Goal.** Replace the shared dev-secret with managed per-user auth, open an **authenticated HTTP path to create episodes** (today creation exists only as a batch FIT-ingest stub over `queries.upsert_episode`; no authed endpoint), and import history (GPX/Strava/Garmin) as the `been_on` producer that pre-warms taste and **unblocks novelty**. This is the pivot that makes the value prop demonstrable on real, non-mock data.

**What good looks like.** A real person signs in with managed auth (not a free-text `viewer_id` behind one shared secret), logs a trip over HTTP that creates a real Episode, imports history that produces `been_on` beliefs and pre-warms taste from day one. The belief/context/novelty/outcome loop runs on **real data for at least one real user**. Anonymous browsing stays a first-class un-gated product. The reward for logging is a better answer, never a streak.

**Includes.**
- **Managed auth (R3 / B004)** replacing the shared dev-secret — provider chosen in the [decision brief](../research/auth-provider-decision-brief.md) (**recommend Supabase Auth**, pending PO sign-off): verify the per-user JWT against JWKS, map the stable `sub` → `viewer_id` at `_authorize_viewer` (`api/app.py:96`), and `ScopedSession` stops trusting `viewer_id` verbatim. The **CDP-12** shape (Zanzibar tuple + userset-rewrite + consistency-token) so a future revoke takes effect on next VIEW is a property of the **grant layer**, built here on top of the verified id — *not* something the IdP supplies.
- **Preserve anonymous browsing** — auth gates *only* the private overlay; the auth epic's DoD must assert anonymous `/plan` still works unauthenticated.
- **Authenticated episode-creation HTTP path** — wire `queries.upsert_episode` (today batch-only) behind an authed endpoint so a planned/completed trip becomes a real Episode node; close the outcome loop end-to-end.
- **Epic 006 novelty (now UNBLOCKED)** — build `novelty_score()`/`apply_novelty_discount()`, the `graph/migrations/` dir it needs, and the `been_on` producer it was self-blocked on; include the **Matthew-effect guard** from day one (degree-cap + a separate labeled "popular" lane + a degree-correlation eval).
- **History import (B003)** — GPX/Strava/Garmin as the `been_on` producer; pre-warms taste, unblocks Epic 006 and the Stage-7 memory eval; strip residual metadata on any future emit (the Strava privacy-zone leak is the cautionary tale).
- **Map-matching is a first-class sub-task / risk on history import (B003's "Hard sub-problem").** A raw GPX track must bind to specific corpus trail nodes to produce a `been_on` edge — and snapping noisy tracks to the trail graph is non-trivial. If this isn't resolved, history import can run and produce **zero** `been_on` beliefs, leaving Epic 006 still blocked after the phase "completes." Carry B003's stated fallback (**store as free-floating episodes with geometry, match opportunistically**) so the import is never blocked on perfect matching; the rigorous version is **CDP-20's Newson-Krumm HMM snap-to-network**, which records the match as a probabilistic inference carrying its own confidence (source-or-silence for the binding: a low-confidence snap reads "likely *Cascade Pass* — low confidence, GPS sparse"). See Open Decision #10.
- **CDP-18 two-channel preference model (the taste core, not an extra)** — a save/completion is a noisy low-confidence *positive*; a non-interaction is **near-neutral, never a negative**; keep stated and revealed preference as separate provenance-tagged channels and honor the stated self at **full weight at cold-start**, never silently overwriting it; require a multivariate, pool-controlled contradiction before even hedging. Tuning shows "what you told us" separately from a quiet "what we've noticed." This is the formal spine of Epic 006's taste work, not optional. *(Beli-style pairwise cold-start, below, is its bootstrap fragment.)*
- **Beli-style pairwise cold-start bootstrap** for taste so a brand-new user isn't cold.
- **Calm 3-question onboarding/first-run** writing the initial `PhysicalProfile`/`PartyProfile` (replaces `App.tsx:13` hardcoded `defaultState`).
- **Persisted settings + a "what we believe about you" transparency surface** (Beliefs are write-only today); doubles as the data-rights read surface.

**Dependencies.** Auth must land before history import. **Phase B's ToS + data export/deletion (a *blocker*, not a nicety — you cannot claim a GDPR/CCPA-grade posture while importing health-adjacent history with no deletion right) + rate-limiting must precede accepting real personal data** — the deletion right is a hard precondition of history import, in this phase. Epic 006 unblocks only once the `been_on` producer (history import) exists.

**Exit criteria — MILESTONE 1: "the loop is real."** A real user signs in, logs a trip that creates a real Episode, imports history that produces `been_on` beliefs (or, if map-matching is unresolved, a free-floating-episode fallback that still records the visit — see Open Decision #10), and gets an honestly-personalized answer from their **own** data. Novelty is live with the Matthew-effect guard. `upsert_episode` is reachable behind an authed HTTP endpoint (not just batch ingest). *(This milestone is independent of the corroboration moat — it tests the intake loop, not corroboration.)*

### Phase D — The honest verdict surface *(CDP-04 verdict + readiness + the calm cockpit)*

**Goal.** Deliver the north-star user moment: **one** legible go/marginal/no-go read naming a single binding constraint as a tap-through live source, non-actionable facts collapsed into a muted tray, a safety overlay always in the top slot, readiness as a hedged capability floor that never reorders by desirability. This is where the discipline — **refusal** — becomes the visible product.

**What good looks like.** The top card reads "Marginal — go if you start before noon"; one tap shows the binding constraint (NWS thunderstorms, named + timestamped), the creek-ford streamflow as "single authoritative source (USGS gauge)" and the trail itself "confirmed by 2 independent sources" (NPS + USFS corpus origins); a ruled-out trip sits in a "Ruled out (1)" tray naming exactly why (fire closure, NPS source); structural distance is quietly marked un-reverified, not dressed as live. Readiness is a hedged capability band that tightens the effort floor but never reorders. The whole answer is readable in under a minute and the success state is **the user leaving**. *(Post-spike correction: the ford streamflow is a **live single-source** fact, so it honestly reads "single authoritative source (USGS gauge)" — *not* because of a degrade but because each live kind is structurally one government source; the "confirmed by 2 independent sources" line belongs to **corpus** facts the trail's existence/geometry carries across NPS + USFS `SourceRecord`s. The verdict, the named binding constraint, the ruled-out tray, and the four silence states are all unaffected.)*

**Includes.**
- **Epic 007 readiness (DESIGN SESSION FIRST, then WRITE THE FILE — no spec exists, safety-adjacent)** — adopt **CDP-10/09**: non-compensatory capability/safety SCREEN then compensatory taste RANK; readiness as a transient tightening factor buffered *above* the hard line, never a preference veto; party = weakest-link with per-member disclosure; readiness **never** a score/ring/streak.
- **CDP-04 advisory GO/MARGINAL/NO-GO verdict** naming one binding constraint as a live-source link, always overridable (today only a binary `GuardrailVerdict`); an override is recorded as preference signal; the verdict is not an oracle.
- **CDP-02/07 finish** — three fact-states with LOUD silence (no-data / no-hazard / not-fetched / stale-degraded, visibly distinct) + two-axis trust grade (authority separate from corroboration).
- **CDP-10 ruled-out tray** — the non-compensatory screen surfaces every ruled-out trip with its binding cutoff + source, never silent deletion.
- **Wire the dead/inert paths into the verdict** — `intent.filters` (dog-friendly/max_length/difficulty), water (USGS), permits (RIDB) into the guardrail so "constraints as hard filters" means more than weather/AQI/fire.
- **CDP-05 criticality as a machine field** driving visual weight + an enforced actionable-flags budget (median ≤1, hard ceiling ≤2) so the critical fact is never buried.
- **CDP-17 hedging-as-credibility / show-your-work** — every verdict re-derivable from the work it shows.
- **CDP-16 append-only override ledger + immutable decision-snapshot** — the *mechanism* behind "every verdict re-derivable from its shown work": sensed/live facts are immutable, a user override becomes a NEW annotated edge over the original (never an in-place overwrite), and an immutable hashed **snapshot of the decision substrate** is persisted so a *past* verdict can be replayed as-evaluated ("Verdict as evaluated 2026-06-12 14:30") *without* persisting ephemera as live nodes. This is the substrate Epic 009's replay test reconstructs against, and it ties the show-your-work claim to a concrete schema invariant.
- **CDP-15 earn-the-right-to-interrupt** — notifications fire only with cause + consequence + time + a corrective verb; N buzzes collapse into one consolidated push (transactional-only delivery substrate chosen here).
- **Timezone / local-wall-clock correctness** — the verdict literally names wall-clock times ("go if you start before noon"), so the region's local time and DST must be computed correctly, not the server's; this is safety-adjacent (a verdict that names the wrong hour is a confidently-wrong safety claim), so it lands with the verdict, not later.
- **Minimal "near me now" proximity** (substrate-ready on Valhalla) so the north-star moment is reproducible at exit; full place-name search stays in Phase E.
- **Single-user saved-trip conditions-watch (CDP-11 solo half)** — safety-is-perishable for one user, with pre-set triggers + a forward-framed "best call from here" recall. This **forces the always-on poller host (R7) decision earlier** — so its standing cost is folded into Phase B's R5 measurement (above), and this commitment is made against measured numbers. *(Fallback if the R5 number doesn't justify a 24/7 host yet: demote to **pull-on-open re-verification** — re-run the verdict when the user opens a saved trip, no always-on host — and defer the true always-on poller to Phase F where multiplayer already requires it. See Open Decision #7.)*

**Dependencies.** CDP-04 needs Phase A's correct corroboration + this phase's screen-then-rank to name a *true* binding constraint. Epic 007 needs its design session before it can be DEFINED. Builds on the Confidence-v2 primitive.

**Exit criteria.** The north-star moment is reproducible end-to-end on real data: one verdict, one named binding constraint as a tap-through source, a ruled-out tray, four distinct silence states, readiness as a non-ranking hedged floor, `intent.filters` + water + permits actually screening candidates. **Median actionable flags-per-trip ≤1 (hard ceiling ≤2); a safety overlay takes the top slot 100% of the time.**

### Phase E — Table-stakes reach *(search, more regions, onboarding/settings, offline-aware)*

**Goal.** Turn a one-region curated-feed demo into a real app a stranger can use: find any trail (near me now / dreaming from home), trust more than one verifiable region, get onboarded, change settings, read honestly under intermittent connectivity.

**What good looks like.** A user searches a place name or "near me now" and gets verified candidates; at least a second verifiable region is loaded (and the path to more is decided); a first-run onboarding explains the honesty model without nagging; settings let the user control units/home/consent/data; an offline-aware surface shows freshness honestly instead of serving stale-as-fresh.

**Includes.**
- **Search / geocoding — destination + full proximity (B001)** — "dreaming from home" place-name search + geocoder seam (origins are 3 hardcoded towns today, `frontend/src/data/origins.ts`); search is a finite tool curated *through* the engine, never an infinite-scroll raw list; **WRITE THE EPIC**.
- **Continental coverage decision + a second verifiable region (B002)** — make the unmade R7 DB-tier call (lazy-load-on-search vs paid tier + bulk ingest); fix the O(N·M) all-pairs conflation with 38N-hardcoded geometry (intractable continentally, latently wrong off-latitude); at minimum load + honestly verify a **second** region.
- **CDP-20 topology-integrity gate (routing's source-or-silence)** — a pre-routing integrity gate enumerates isolated / dead-end / gap segments so **"no route" renders as a SOURCED empty-state** ("no connected trail path in our data between A and B; segment X isolated; last ingested USFS 2026-05 — we won't guess"), never a silent blank; geometry stays immutable while overlays + effort floor are query-time cost terms; and the same HMM snap-to-network that binds imported tracks (Phase C) carries its confidence here. This is the correctness substrate B001/B005 routing rests on.
- **Trailhead-linkage data quality** — 15/24 pilot-region trailheads are unlinked (OSM sparsity — *this figure derives from the same un-re-runnable Aura ingest; treat as asserted, not proven until the Phase-A re-runnable ingest confirms it*); link them or surface the gap as accepted-degradation, never silently route from a wrong/absent trailhead.
- **Route-drawing groundwork (B005)** — scope the planning-vs-recording split (recording overlaps B003's import; planning shares the spatial-graph substrate with search); full planning build can defer to G. **Exit criterion for the groundwork line:** the planning/recording split decision (Open Decision #11) is *made*, and the spatial-graph substrate query that both halves share is identified and reused (not re-built) — so neither half is silently pulled forward unscoped.
- **Onboarding** explaining source-or-silence / confidence / the calm contract, no engagement hooks.
- **Settings** — units, home location, notification preferences, consent toggles, data export/deletion entry point.
- **Offline-aware / PWA freshness** — stale-while-revalidate then LOUD silence; make the decoratively-inert Staleness primitive real (no screen sets `stale=true` today).
  *(Re-runnable ingest verification — formerly listed here — moved **up to Phase A**: the slug-collision audit needs reproducible-from-`main` corpus data to run at all, so it can't wait until Phase E.)*

**Dependencies.** Search needs the corpus + Valhalla (built) but benefits from Phase A's audit. Continental coverage forces the R7 cost decision, informed by Phase B's measured cost. Onboarding/settings ride on Phase C's real auth.

**Exit criteria.** A stranger can sign in, search for a specific trail or "near me now", get a verified honest answer in **at least two verifiable regions**, complete onboarding, and adjust settings; the DB-tier/coverage decision (R7) is **made, not deferred**; Staleness is live. The app is genuinely usable by someone who isn't Josh.

### Phase F — Multiplayer & perishable safety *(household grants + saved-trip watch)*

**Goal.** The product is "real" the moment a **second** real household member gets an honestly-personalized answer from their own logged history and can share a derived conclusion without leaking the raw substrate. Add the grant system and the party-aware continuous-safety watch the invariants were always designed for.

**What good looks like.** Alex shares a trip with Josh showing "Shared by Alex (derived recommendation)" with **zero path back to Alex's private substrate**; a revoked grant takes effect on Josh's next view; a saved trip carries a live conditions-watch with pre-set triggers and a forward-framed "best call from here" recall — never a silent auto-cancel, never a stale release served as fresh.

**Includes.**
- **Stage 8 multiplayer / grants / party-merge** — the grant-creation system (`granted_ids` seam exists but is always `()` in practice); grant = a revocable, time-boxed, no-re-share stop-point on a provenance edge; share the derived **conclusion**, never the substrate (**CDP-12**).
- **CDP-13 transitive staleness propagation** — a changed source flags every conclusion that depended on it, along the provenance edges.
- **CDP-11 perishable-safety watch (party-aware half)** — per-member trigger points + a grant-scoped forward-framed recall across two real users, extending the solo watch's poller host from Phase D.
- **Party-fit composition (from Epic 007)** — solo-vs-party weakest-link with per-member capability disclosure, now exercised with two real users.
- **Per-identity write verification** — close the forged-id hole completely now that real auth (Phase C) exists.

**Dependencies.** Hard-depends on Phase C real auth (no grants without real identities). The party-aware watch extends the solo watch's poller host (R7), stood up in Phase D. Builds on Phase D's verdict (the watch re-runs it).

**Exit criteria — MILESTONE 2: "the product is provably real."** A second real household member gets an honestly-personalized answer from their own history; a derived conclusion is shared with **zero substrate leakage** (CI-proven, extending the existing falsifiability tests); a revoke takes effect on next view; a saved trip's safety watch re-establishes state continuously and recalls forward.

### Phase G — The commons & native polish *(the give-back + the long tail)*

**Goal.** Close the loop the architecture promised: a born-severed, de-identified commons that aggregates only above the k-anonymity floor, plus native iOS and the deferred polish. The moat compounding — corpus and commons accrete — and the surface reaching its final calm form.

**What good looks like.** The commons READ half serves aggregate truth **only above the k-floor** (never below), born-severed and de-identified with no model training and no data sale; the licensing/consent gate is in place; native iOS (SwiftUI) delivers the calm surface at platform quality; the long-tail polish is done.

**Includes.**
- **Stage 9 commons read-half + k-anonymity floor** (**CDP-19**: k-plus-deferred-DP, known-incomplete) + licensing/consent gate (R1/T6).
- **Stage 11 native iOS (SwiftUI)** — the calm surface at native quality.
- **Backup/DR runbook** for the irreplaceable personal overlay (full version; stub landed in Phase B).
- **Guardrail robustness** — replace hand-tuned keyword/threshold substring matches with logic tested against real NWS alert-vocabulary breadth.
- **Conflation threshold calibration** against real data at scale; fix the off-latitude geometry bug surfaced in Phase E.
- **Monetization posture made concrete** (flat subscription or self-host, never ad/engagement-funded); privacy-respecting aggregate-only analytics if any; performance budgets (bundle-size CI gate + `/plan` latency SLO once Phase-B observability gives metrics).

**Dependencies.** Commons read-half needs the write-half (built, born-severed) + a real multi-user population (Phase F) to clear the k-floor. Native iOS rides on a stable verdict/honesty surface (Phase D) and reach (Phase E). Genuinely *Later* — substrate and surface must be trustworthy first.

**Exit criteria.** The commons read-half serves only above the k-floor with the consent/licensing gate live; native iOS ships the calm surface; the personal overlay has a documented backup/DR path; guardrails are tested against real alert vocabulary.

---

## 4. Now / Next / Later

> *Status of any single item lives in the roadmap. This is the shape of the runway, not a task tracker.*

### Now (Phase A — substrate before surface)
- **CDP-01 feasibility spike — ✅ DONE** ([`../research/cdp-01-corroboration-feasibility-spike.md`](../research/cdp-01-corroboration-feasibility-spike.md)): moat real and recoverable, locus = corpus `SAME_AS` layer; live single-source `1` is honest, not the feed-counting sin. No more investigation gates this — proceed to the wiring.
- **Corroboration wiring — ✅ DONE** (`engine.py:320,427,491,497`; see Phase A above). Remaining under this CDP: MIN/weakest-link fusion (CDP-06) is not yet the confidence math in code, and the corpus distinct-origin count isn't yet surfaced on the card/API.
- **Slug-collision guard — ✅ DONE (Epic 030,** `ingestion/pipeline.py:130-145`**)**; the historical 1643→1458 delta audit + any back-fill remain open, non-blocking follow-ups (`docs/process/roadmap.md`).
- **Doc-drift fixes** — apply_schema/016/017 already fixed; this pass adds the missing Epic 026 index row and notes Epic 008 shipped without a dedicated file (`docs/epics/README.md`); the whole vision must stand on fresh memory.
- **M9 owned-Cypher CI lint** — close the asymmetric-guard gap (`context_assembly.py:71,96` + `outcome.py:88`).

### Next (Phase B → C — defend-and-secure, then fill the intake)
- **Epic 008 (WRITE THE FILE)** — happy-path `/plan` + `/health` tests in CI; wire the frontend Vitest suite into CI.
- **Epic 009 eval harness in CI against the REAL engine** — golden trips + cassettes + N-run + LLM-judge + Brier/calibration hook. This is source-or-silence's defense.
- **Rate-limit `/plan` + basic observability/cost metrics** — it fans out to live APIs + LLM unthrottled on a live deploy (R5).
- **ToS/privacy/consent + data export/deletion** — required before a second real user's health-adjacent data lands.
- **Managed auth (R3)** — pick a provider, issue real sessions, stop `ScopedSession` trusting `viewer_id` verbatim; design the boundary for CDP-12 revoke-on-next-view.
- **Authenticated episode-creation HTTP path** — expose `queries.upsert_episode` (today batch-only) behind an authed endpoint so a real trip becomes a real Episode.
- **History import (B003)** as the `been_on` producer → unblocks Epic 006 novelty (build it *with* the Matthew-effect guard); calm onboarding + settings/transparency surface ride on real auth.

### Later (Phase D → G)
- **CDP-04 GO/MARGINAL/NO-GO verdict** naming one binding constraint as a tap-through source + CDP-02/07 four silence states + two-axis trust grade.
- **Epic 007 readiness (DESIGN SESSION FIRST)** — screen-then-rank, capability floor buffered above the hard line, never a score/ring/streak; solo saved-trip safety watch (CDP-11 solo half) + the earlier R7 poller-host decision.
- **Wire the dead/inert paths** — `intent.filters` + water + permits into the guardrail.
- **Search/geocoding (B001), continental coverage + R7 DB-tier decision + a second verifiable region (B002), onboarding, settings, offline-aware PWA freshness.**
- **Stage 8 multiplayer/grants/party-merge (CDP-12/13) + CDP-11 perishable-safety watch (party-aware)** — needs the always-on poller host.
- **Stage 9 commons read-half + k-anonymity floor + licensing/consent gate (CDP-19); Stage 11 native iOS; backup/DR runbook; guardrail vocabulary tested against real NWS alert breadth.**

---

## 5. Critical path + sequencing rationale

### The single longest dependency chain to a complete, deeply-useful app

1. **CDP-01 corroboration feasibility spike** *[✅ DONE — moat real, locus = corpus `SAME_AS` layer]* →
2. **`SAME_AS`-cluster corroboration wiring — ✅ DONE; MIN weakest-link fusion still open** *[the corroboration half makes the headline claim TRUE (`engine.py:320,491,497`); MIN-fusion (CDP-06) is the remaining confidence-math correction]* →
3. **Slug-collision guard — ✅ DONE; historical delta audit still open** *[the guard (Epic 030) prevents new fusions; the 1643→1458 delta audit + back-fill remain to make the existing data provably clean]* →
4. **Epic 009 eval harness in CI** *[DEFENDS the claim on every PR]* →
5. **Managed auth (R3)** *[gives the machinery a real identity to attach data to]* →
6. **Authenticated episode-creation HTTP path over `upsert_episode` + history import / `been_on` producer** *[FILLS the empty intake → Epic 006 unblocks]* →
7. **CDP-04 verdict layer + Epic 007 readiness** *[delivers the north-star moment on real data]* →
8. **Search + a second verifiable region** *[makes it a usable app, not a one-region demo]* →
9. **Stage 8 grants + a SECOND real household user** *[the moment the product is provably real]*.

**Auth (step 5) is the pivot:** everything before it *hardens what exists*; everything after it *depends on a real per-user identity*. **Rate-limiting + ToS/data-rights are OFF-path but BLOCKING gates** that must clear before step 5 accepts real personal data on a live deploy. Two named proof points break the long C→F runway into a real go/no-go rather than an all-or-nothing finale: **Milestone 1 "the loop is real"** (Phase C exit) and **Milestone 2 "the product is provably real"** (Phase F exit).

### Three ordering rules (each grounded in the research, verified against the repo)

1. **Substrate before surface — fix what's false before building what's new.** Corroboration wiring has shipped (corpus facts carry a real `SAME_AS`-cluster distinct-origin count; `engine.py:320,491,497`) — but it sits over a corpus that may have silently fused real trails before the slug-collision guard landed (the unaudited 1643→1458 delta). A beautiful verdict layer built over a possibly-corrupted substrate is **confidently-wrong safety at a larger blast radius**, so Phase A precedes Phase D. The honesty primitives *are* the product; making them true is non-negotiable Phase 1.

2. **Defend-and-secure before intake.** The spine invariant has no automated regression gate against the real engine, and the live endpoint is unthrottled (no `slowapi` anywhere in `api/`) with no ToS and no observability. You cannot responsibly invite a real user's health-adjacent data onto a deploy you can't regression-test, can't afford (R5 unmeasured because nothing measures it), and have no privacy surface for — so Phase B precedes Phase C. This also front-loads the cheap-but-load-bearing doc-drift fixes, because the project's own rule is *"wrong memory is worse than none."*

3. **Table-stakes before scale, and the moat when feasible.** The deepest finding is that the sophisticated personal-intelligence machinery has **no intake** (no auth, no HTTP episode creation, no `been_on` producer — all mock for one seeded user). So auth + episodes + history (Phase C) is the pivot that makes the value prop demonstrable on real data, and it gates everything multi-user. Only after one real user works do we add reach (Phase E), then the second-user moat (Phase F), then the give-back (Phase G). The CDP-01 spike was deliberately the very first action precisely because it was that load-bearing — and it resolved positive: the moat is real, its locus is the corpus `SAME_AS` layer, and the origins we already hold are now wired into confidence (`engine.py:320,491,497`) — not "honestly disclose a limit."

Throughout, the **anti-engagement spine is treated as a correctness constraint, not a style choice:** every phase forbids streaks/scores/leaderboards because they poison the very taste signal the recommender needs.

---

## 6. Open strategic decisions

These are decided *above* the roadmap because each reshapes a phase or the differentiator itself.

1. ~~**CDP-01 origin-metadata feasibility — the moat-or-relabel fork.**~~ **✅ DONE** ([spike](../research/cdp-01-corroboration-feasibility-spike.md)). The moat is **real and recoverable** — but its locus is the **corpus/`SAME_AS` layer**, not the live adapters. Distinct-origin metadata is fully present in the corpus (every `SourceRecord` names its origin) and recoverable for the point-based live sources (USGS gauge gold; NWS office+grid and FIRMS satellite recoverable at the boundary). The only genuinely-shared case is AirNow (an aggregator) → honestly "single aggregated source, counts as 1." No corroboration-substrate investment needed; the wiring shipped in Phase A (above), not recovery.
2. ~~**Corroboration honesty when unimplementable.**~~ **✅ DONE** ([spike](../research/cdp-01-corroboration-feasibility-spike.md)). Resolution: **KEEP the axis and exercise it on corpus facts**, where it's true. Live single-source conditions read "single authoritative source (counts as 1)"; corpus facts read the real distinct-origin count. The axis stops being dead weight and never advertises an unexercised capability — neither the "remove it" nor the "advertise-but-fake" failure mode applies.
3. **R7 DB-tier + coverage strategy.** Aura Free's node ceiling cannot hold a continental corpus. Lazy-load-on-search (cheap, complex, first-touch latency) vs a paid tier with bulk continental ingest (simple, costs money, forces the O(N·M)/38N-hardcoded conflation rewrite). Gates Phase E; informed by Phase B's measured cost.
4. **Managed auth provider (Supabase vs Clerk vs Auth0 vs roll-your-own).** **🔶 BRIEF PRODUCED — awaiting PO sign-off** ([decision brief](../research/auth-provider-decision-brief.md)). Recommendation: **Supabase Auth** — satisfies all four hard requirements (replace dev-secret · preserve anonymous browsing · transactional email · clean grant-layer coupling), is the only managed option whose Apache-2.0 self-host posture matches the local-first/private-by-default ethos, and its one weakness (dev-only built-in email) is neutralized because Phase B already commits to an external ESP regardless. *Correction the brief makes explicit:* the IdP supplies **only a verified `viewer_id`** — **revoke-on-next-view is a property of the grant layer we already built** (`ScopedSession` re-reads `granted_ids` per request), **not** an IdP feature, so providers are *not* graded on it (the earlier "must support consistency-token/revoke" framing was a category error). **Decide before Phase C.**
5. **Un-paywalled-live-truth economics (R5).** The moat is "never gate safety/freshness behind a tier" but live API + LLM calls cost money. Once Phase B measures real cost-per-session, decide the sustainable position (JIT cache windows + per-data-type refresh + region pilots + rate-limit tiers) — and confirm the no-paywall-on-safety stance survives contact with the actual bill.
6. **Readiness composition for parties (Epic 007 has NO spec).** Solo readiness is a hedged capability floor, but party = weakest-link with per-member disclosure is unspecified and safety-adjacent. Needs a dedicated design session before Epic 007 can even be DEFINED — and it gates the Phase F party-merge.
7. **Watch-poller always-on host (R7).** The CDP-11 perishable-safety watch needs an always-on polling host. Because the *solo* saved-trip watch is now scheduled in Phase D (safety-is-perishable applies to one user, not just a party), this decision moves **earlier** than the multiplayer endgame. Two branches, gated on Phase B's measured cost: **(a)** if the standing 24/7 cost is justified, stand the host up in Phase D against that measured number (R5 scope now *includes* the standing poller cost); **(b)** if not yet, ship the Phase-D solo watch as **pull-on-open re-verification** (no always-on host) and defer the true always-on poller to Phase F, where multiplayer already requires it. Decide the branch before Phase D commits the solo continuous-safety promise.
8. **Commons k-anonymity + DP posture (CDP-19).** The commons read-half is "k-plus-deferred-DP, known-incomplete." Decide whether Phase G ships with k-floor-only (simpler, weaker privacy) or invests in differential privacy now, and where the licensing/consent gate (R1/T6) draws the line on what a born-severed observation may contain.
9. **Monetization posture (state now, build in G).** No billing exists and `render.yaml` is free-plan; live API + LLM costs accrue per request with no revenue model. **State the posture now** — flat subscription or self-host, never ad/engagement-funded — so R5 cost decisions have a frame and the calm-private-utility identity stays coherent.
10. **GPX→trail-node binding (map-matching) for history import.** Does Phase C's history import bind tracks to corpus trail nodes via CDP-20's HMM snap (rigorous, carries confidence, but more build), or ship the **free-floating-episode fallback** first (geometry stored, matched opportunistically) and add snap later? This gates whether history import actually produces `been_on` edges — i.e. whether Epic 006 truly unblocks in Phase C. **Decide at Phase C build start.**
11. **B005 planning-vs-recording split.** Route-drawing is two features: *recording* ("trace what I did," overlaps B003's import — could ride Phase C) and *planning* ("build the route I'll hike," the larger net-new build, shares the spatial substrate with Phase E search, can defer to G). The split decision determines **when each half lands**; decide it before the Phase E route-drawing groundwork so a piece of B005 isn't implicitly pulled forward unsequenced.

---

## 7. Doc-organization plan

**The fresh structure is staged in the working tree, not yet committed** (2026-06-29): `docs/vision.md` and this `docs/strategy/path-to-complete.md` are **untracked** (`git status` shows `?? docs/vision.md`, `?? docs/strategy/`), and the `docs/README.md` vision/strategy router rows + the design-system §9.2 freshness fix are **modified-but-unstaged** edits. So until this branch is committed, a reader pulling `main` sees neither doc nor the routing to them. This pass is therefore **reconcile-and-cleanup-then-commit**, not a build. Lane discipline: every PM-owned doc edit is a **proposal needing confirmation** (marked ⚠ below); only mechanical build/docs-lane moves are marked safe. Several rows below are already applied in the working tree (marked **DONE (working tree)**) and remain listed only so the cleanup pass is auditable.

### The relationship (one line)

`vision.md` (north star, always-load) → **`strategy/path-to-complete.md`** (this doc: the integrated route incl. table-stakes) → `workplan.md` (stage order) + `process/roadmap.md` (tactical SSOT, this-week) → `epics/` (committed work) → `research/` (design provenance). **Vision/strategy never restate live status** — both open by linking down to the roadmap.

### Keep / supersede / archive / merge actions

| Action | Doc | Risk | Owner |
|---|---|---|---|
| **Keep** (as-is) | `docs/vision.md`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/decision-log.md`, `docs/research/**` (incl. the two new reviews), `docs/runbooks/deploy-api-render.md` | safe | — |
| **Keep** (this doc) | `docs/strategy/path-to-complete.md` | ⚠ needs-confirmation | PM |
| **Done (de-rot)** — the stale "commit untracked `apply_schema.py`" follow-up is dropped; `roadmap.md` now notes it's tracked (`tests/test_apply_schema.py` exists) | `docs/process/roadmap.md` | ✅ done | PM |
| **Done (drift fix)** — `Status:` headers flipped to DONE; the epic index reconciles with the roadmap | `docs/epics/epic-016-maps-and-terrain.md`, `docs/epics/epic-017-terrain-elevation-enrichment.md` | ✅ done | PM |
| **Update (freshness)** — refresh "Last updated June 18" header + add a one-line pointer to this doc | `docs/workplan.md` | ⚠ needs-confirmation | PM |
| **DONE (working tree)** — `docs/runbooks/` router row added (read-this-for-that table + load-on-demand list) so the deploy runbook is findable | `docs/README.md` | safe | docs |
| **Archive** → `docs/research/archive/` — stale 2026-06-23 readiness snapshot; its live content (006/007 underdefined) is now in the epic index + this doc | `docs/process/plan-analysis.md` | ⚠ needs-confirmation | PM |
| **Update (fix dangling ref) — gated on the plan-analysis archive** — two backtick code-span pointers to `plan-analysis.md` will go stale on the move and are **invisible to the CI doc-lint** (`scripts/doc_lint.py` `LINK_RE` only matches `[text](path)`, not backtick spans): `CLAUDE.md:18` (always-loaded — highest-risk stale pointer) and `docs/research/novelty-filter-spec.md:3`. Repoint both to `docs/research/archive/plan-analysis.md` (or drop the CLAUDE.md line, since its live content now lives in the epic index + this doc); verify with a repo-wide grep for `plan-analysis` after the move | `CLAUDE.md`, `docs/research/novelty-filter-spec.md` | ⚠ needs-confirmation | PM/docs |
| **Archive** → `docs/research/archive/` — self-marked CLOSED but misfiled in `process/` (all 7 other closed audits live in `archive/`) | `docs/process/parallel-integration-runbook.md` | safe | build |
| **Update (index)** — append the two archived docs to the archive table | `docs/research/archive/README.md` | safe | docs |
| **DONE (working tree)** — §9.2 already states all three honesty primitives ship with tests + stories (verified 2026-06-29); the "remain to be built" string no longer exists. Listed for audit only; no further edit | `docs/research/design-system-v0.1.md` | safe | docs |
| **DONE (working tree)** — vision/strategy router rows + SSOT entries already added | `docs/README.md` | safe | docs |
| **No hand-edit** — auto-generated; self-corrects once 016/017 `Status:` flips | `docs/epics/README.md` | safe | build |

**Lane hand-off (load-bearing, not optional).** The remaining ⚠-marked rows — the workplan freshness header and the plan-analysis archive — are **PM/PO-lane tasks**, *filed* from here but **never executed from the vision lane**. The vision-PM proposes; the PM/PO disposes. (The epic-016/017 `Status:` flips and the roadmap apply_schema de-rot are done — see above.) The safe (docs/build-lane) rows — the `docs/runbooks/` router add, the parallel-integration-runbook archive move, the archive-index append — may proceed in this pass.

**Net change still to apply (vs the working tree, not `main`):** commit the two new docs + the README (vision/strategy + runbooks router) and design-system edits already in the working tree; archive 1 (plan-analysis) + repoint its 2 dangling backtick refs (`CLAUDE.md:18`, `novelty-filter-spec.md:3`); move 1 (parallel-integration-runbook); refresh the workplan header (PM-lane); append 2 rows to the archive index. (The 2 epic `Status:` flips and the roadmap apply_schema de-rot are already done.) Fewer, clearer docs; **nothing abandoned**; the memory the vision stands on is made fresh.

---

> **Where to go next:** for *what's being built this week* → `docs/process/roadmap.md`. For *the north star and the refusals* → `docs/vision.md`. For *the stage dependency order* → `docs/workplan.md`. For *the committed unit of work* → `docs/epics/`.
