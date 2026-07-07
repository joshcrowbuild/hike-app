# Epic 037 — Open-Meteo weather availability-failover (reshaped: NO corroboration)

**Status:** DONE ✅
**Phase:** Spike (docs-only; downstream build BLOCKED on a commercial-license PO decision)
**Spec refs:** `docs/research/open-meteo-failover.md` · `docs/research/source-seams-corpus-and-live.md` (SS-6/SS-11) · vision.md principle 9 (line 74) · Epic 013 (LiveAdapter seam) · Epic 018 (live conditions on the card) · C6 (NWS-outage = no weather, no swap)

---

## Capability statement
The project has an adjudicated, written record proving that Open-Meteo **cannot** be counted as a second corroborating weather origin (it is a NOAA/NBM echo), and a fully-specified — but not-yet-built — **availability-failover** adapter design (secondary to NWS, disclosed non-authoritative, corroboration pinned at 1) that closes C6's "NWS outage → no weather, no swap path," gated behind a surfaced commercial-license blocker.

## Architectural context
Builds on:
- The LiveAdapter seam (Epic 013 — `orchestration/adapters/base.py`, kind-keyed primary→fallback registry `orchestration/adapters/registry.py`).
- The CDP-01 corroboration wiring now LIVE in `orchestration/engine.py` — corpus `SAME_AS` distinct-origin count is the **only** source of `corroboration>1`; every live fact is pinned at `corroboration=1` (`engine.py:341`).
- SS-11's already-named, license-pending weather fallback slot for the `weather` kind.

Enables (all DOCS-ONLY this epic; no product code):
- A PO decision on the Open-Meteo commercial-license blocker (free tier is non-commercial only).
- A future BACKLOG build of the failover adapter + multi-model spread-as-disclosure, if and only if the license clears.

Does NOT include (BINDING SCOPE FENCE):
- **NO adapter code.** No `orchestration/adapters/open_meteo.py`.
- **NO config/registry wiring.** No new entry in `ADAPTER_FACTORIES` (`registry.py:42-50`), no change to `ADVENTURE_LIVE_ADAPTERS`, no `config.py` field.
- **NO corroboration-path change.** `engine.py:341` (`for_fact(fact, corroboration=1)`) and `_corpus_corroboration` (`engine.py:204-230`) are untouched.
- **NO training, NO new dependency, NO vendored/ported Open-Meteo source code** (their server is AGPLv3 — hosted HTTP only, never in-repo).

---

## The load-bearing output — the ECHO SIN, documented in full

This is the reason the chartered premise ("Open-Meteo = the first second-corroborating live-weather origin") **must not be built as charted**. The corroboration path stays exactly as it is.

**The provenance chain, both sides, verified against current code:**
- **Our NWS side.** `orchestration/adapters/nws.py:47-49` reads `api.weather.gov/points/{lat},{lon}` → the office **gridpoint** forecast (`nws.py:61-65`). That endpoint serves **NDFD**, and **NDFD is derived from the NBM (National Blend of Models)** — NOAA's own words: "a blend of both NWS and non-NWS numerical weather prediction model data and post-processed guidance … the starting point for NDFD." So NWS is already a human-edited multi-model blend of **GFS + HRRR + ECMWF + GEM**.
- **Open-Meteo US side.** For US points `best_match` and the explicit high-res US models are all NOAA: `ncep_gfs_*`, `ncep_hrrr_usl`, and **`ncep_nbm_usl`** — which **IS the exact NBM** that feeds NWS's own forecast. Default US Open-Meteo re-serves the same NOAA numerical guidance NWS is built on.

**Why counting it = feed-counting (forbidden):** vision.md principle 9 (line 74): *"Corroboration is the engine, but independence is the governor — count distinct **origin** nodes, not feeds, and never re-ingest our own output as external evidence."* Two readings of the same NBM = one origin counted twice.

**Even pinned to a non-NOAA model, it still fails:** ECMWF-IFS / DWD-ICON-Global / GEM / ARPEGE are servable over US coords, but (1) **ECMWF and GEM are already inside NBM**, so they partially echo what NWS already blends; and (2) it is **model-vs-model** (two forecasts), not observation-vs-observation — both share the **same WMO GTS observation substrate** (radiosondes, satellite radiances, buoys). "Two models agree" is categorically weaker than the corpus `SAME_AS` count, where NPS and USFS **independently surveyed the same trail** — two real attestations of a structural fact. Model agreement is not what this product means by corroboration.

**Conclusion:** `engine.py:341` pinning every live fact at `corroboration=1` is **correct-by-construction, not a gap to close.** The corpus `SAME_AS` layer stays the only honest source of `corroboration>1`.

**The honest remainder** (what a future build *may* salvage): (a) **failover-availability** — a secondary adapter so an NWS outage still yields weather, disclosed non-authoritative, **corroboration STAYS 1**; and (b) at most **multi-model SPREAD as an uncertainty DISCLOSURE** that only ever WIDENS the hedge, never a count — the inverse of the echo sin.

---

## Stories

### S1 — Record the corroboration refusal (echo sin) as the primary decision

**Given** the charter asked for Open-Meteo as a second corroborating live-weather origin,
**When** the spike evaluates it against vision.md principle 9's independence governor,
**Then** the research doc records — with the full verified provenance chain — that the premise fails the independence test and must not be built, and no code touches the corroboration path.

**AC-1.1:** `docs/research/open-meteo-failover.md` exists and contains a section titled to the effect of "The echo sin" that states: NWS gridpoint = NDFD derived from NBM; Open-Meteo `best_match`/`ncep_nbm_usl` = that same NBM; therefore counting Open-Meteo as a distinct origin is feed-counting.
**AC-1.2:** The doc explicitly cites vision.md principle 9 (line 74, "count distinct origin nodes, not feeds") as the governing invariant that the corroboration premise violates.
**AC-1.3:** The doc states that even a pinned non-NOAA model (ECMWF/ICON/GEM) fails, giving both reasons: (a) ECMWF+GEM already inside NBM; (b) model-vs-model shares one WMO observation substrate, categorically weaker than the corpus `SAME_AS` survey count.
**AC-1.4:** The doc states that `engine.py:341` (`for_fact(fact, corroboration=1)`) pinning every live fact at 1 is correct-by-construction, not a gap, and that the corpus `SAME_AS` layer stays the only source of `corroboration>1`.

### S2 — Spec the availability-failover adapter (secondary to NWS, non-authoritative, corroboration stays 1)

**Given** SS-11 named an illustrative license-pending weather fallback and SS-6's primary→fallback registry is already built,
**When** the spike specifies the honest salvageable value,
**Then** the failover adapter is fully specified as a future one-file build that closes C6, disclosed non-authoritative, taking zero corroboration credit.

**AC-2.1:** The doc specifies an `OpenMeteoAdapter` modeled on `nws.py:98-134` — `kind=ConditionKind.weather`, `is_keyless=True`, `supports_region` = global (NOT just `{"US"}`, contrast `nws.py:122`), TTL matching NWS `ttl_seconds=3600` (`nws.py:106`).
**AC-2.2:** The spec requires the adapter to emit `confidence_inputs={"authority": <tier2/derived, NOT "tier1_gov">, ...}` — verified against the authority weights in `orchestration/confidence.py:22-32` (`tier1_gov=1.0`, `tier2=0.6`, `derived=0.7`) — so a failover reading presents as honestly less authoritative than NWS.
**AC-2.3:** The spec requires the adapter to carry a `disclosures` entry (the `disclosures` tuple exists at `base.py:42`) naming it a non-authoritative secondary/failover source.
**AC-2.4:** The spec states the wiring is exactly one `ADAPTER_FACTORIES` entry (`registry.py:42-50`) + one `ADVENTURE_LIVE_ADAPTERS` position placed **after** `nws` (fallback position, ordered by `probes_for`, `registry.py:78-87`) — and that **none of this is done in this epic**.
**AC-2.5:** The spec states the failover reading MUST be constructed with `corroboration=1` (never routed through `_corpus_corroboration`), consistent with `engine.py:338-341`'s honest count-as-1 for single-source live facts.

### S3 — Spec multi-model SPREAD as an uncertainty DISCLOSURE (widens hedge, never a count)

**Given** the two-axis discipline (pillar 4: refuse to fuse the two axes) and pillar 1's honesty primitives,
**When** NWS(NBM) and a pinned non-NOAA model disagree,
**Then** the disagreement is specified as a `disclosure` that WIDENS the hedge — the inverse of the echo sin — and is proven to never touch the `corroboration=` argument.

**AC-3.1:** The doc specifies spread-as-disclosure: model disagreement (e.g. afternoon-storm PoP) attaches to `VerifiedFact.disclosures` (`base.py:42`), never to the `corroboration=` argument of `for_fact`/`compute` (`confidence.py:52-79`).
**AC-3.2:** The doc states the asymmetry explicitly: agreement NEVER inflates confidence/corroboration; only disagreement lowers presentation (widens the hedge). It cites this as the inverse of the echo sin and a fit for the two-axis refusal.
**AC-3.3:** The doc flags this feature as PO-adjudication-pending and NOT built this epic (it depends on the same license clearance as S2).

### S4 — Surface the commercial-license blocker as a blocking PO decision

**Given** the free tier is non-commercial only,
**When** the spike screens the license (§18 open-data screen / SS-11 precondition),
**Then** the blocker is surfaced as an explicit, blocking product decision that gates any build.

**AC-4.1:** The doc records the license class in full: **data CC-BY 4.0** (attribution satisfied by existing `VerifiedFact.source` stamping); **server code AGPLv3** (hosted HTTP only — never vendor/port); **free tier non-commercial only** with the keyless rate limits (600/min · 5k/hr · 10k/day · 300k/mo).
**AC-4.2:** The doc states the blocker plainly: a shipping product (auth, households) on the free tier violates Open-Meteo ToS; a real build requires a paid subscription OR self-host, and this is a PO decision, not a lane default — and is the core reason this is a spike, not a build.
**AC-4.3:** The epic's Phase/status line and a dedicated "Build status" note both state the downstream build is BLOCKED on this license decision.

### S5 — Invariant guard: prove the corroboration path is untouched

**Given** the highest risk is a future contributor "counting the second weather feed,"
**When** the spike PR lands,
**Then** it is objectively provable that no corroboration path, adapter, or registry wiring changed.

**AC-5.1:** `git diff` on the PR shows **no** changes to `orchestration/engine.py`, `orchestration/confidence.py`, `orchestration/adapters/registry.py`, `orchestration/adapters/base.py`, or `orchestration/config.py` — verifiable by a reviewer and stated as a DoD gate.
**AC-5.2:** No file named `orchestration/adapters/open_meteo.py` is added.
**AC-5.3:** The epic explicitly FORBIDS routing Open-Meteo into engine corroboration and states that any future adapter must hard-code a non-corroborating (`corroboration=1`) disclosure.

### S6 — Deliver the spike outputs + index row through CI

**Given** spike lanes ship a real PR through CI (docs-lint),
**When** the builder opens the PR,
**Then** the research doc + this epic (copied into `docs/epics/`) + the index row are present and docs-lint green.

**AC-6.1:** `docs/research/open-meteo-failover.md` is committed and passes docs-lint.
**AC-6.2:** `docs/epics/epic-037-openmeteo-failover.md` is committed — the body copied from the sprint spec, with its `**Status:**` header set to `REVIEW` at PR-open (body verbatim, Status flipped). This header is the SSOT that `scripts/gen_epic_index.py` syncs the README Status cell from; leaving it `DEFINED` while AC-6.3 sets the README row to `REVIEW` makes `gen_epic_index --check` (run by docs-lint) fail on the mismatch.
**AC-6.3:** `docs/epics/README.md` has a new row for Epic 037 (status flipped to REVIEW at PR-open per the merge-train recipe; content marks the downstream build BLOCKED).
**AC-6.4:** Both `make check` **and** `make docs-lint` (= `python scripts/doc_lint.py`) are green, and the PR is titled `Epic 037: Open-Meteo weather availability-failover — FOR REVIEW`. Note: `make check` is `format-check lint typecheck test` (Makefile:53) and does **not** run docs-lint — for this docs-only lane it touches zero Python and passes trivially. **docs-lint is the real gate** (epic-index sync via `gen_epic_index --check`, broken-link, denylist, `gen_state --check`) and is its own CI job (`.github/workflows/ci.yml:31`); run it explicitly or CI red-lights the PR.

---

## Build status
**BLOCKED** on a commercial-license PO decision (paid subscription vs. self-host vs. non-commercial-personal-only). No product code, config, or registry wiring ships until that clears. The refusal decision (S1) and the design (S2–S4) are the deliverable; the adapter is a future BACKLOG build.

## Definition of Done
- [ ] All ACs above satisfied (S1–S6); each is a checkable doc assertion or a `git diff`/`grep`-verifiable fact.
- [ ] `docs/research/open-meteo-failover.md` + `docs/epics/epic-037-openmeteo-failover.md` + README row committed.
- [ ] `git diff` confirms zero changes to the corroboration path (AC-5.1/5.2).
- [ ] `make check` **and** `make docs-lint` both green — they are separate targets (docs-lint is NOT part of `make check`; Makefile:53 vs :103). For this docs-only lane `make check` runs no doc check and passes near-empty; docs-lint is the gate that matters (see AC-6.4).
- [ ] Targeted self-review run; CRITICALs fixed.
- [ ] Pushed on `claude/openmeteo-failover`; PR opened with the 5 sections (summary / why / scope / validation / merge-risk).
