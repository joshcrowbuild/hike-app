# Epic 010 — Commons Fork Write (de-identified `:CommonsObservation`)

**Status:** DONE ✅ *(2026-06-24 — built on `claude/track-a-write-path`, on Epic 011's scoped-write builders)*
**Phase:** 1 (Personal Intelligence) — a dependency of the episode pipeline, **not** Stage 9
**Spec refs:** Stage 9 §2 (build source of truth) · Stage 9 §6 / S9-13 · Stage 6 §6.2 / S6-10 · Stage 5 §6 / S5-10 · gap-audit C1 · decision-log-additions-proposed §40 (C1) · Rule #8 · Rule #5 · Rule #3 · Rule #4 · Rule #10

---

## Capability statement

Every ingested Episode silently accretes a **born-severed, de-identified `:CommonsObservation`** committed atomically with the `:Episode` — so the commons substrate begins accumulating from day one (un-backfillable if it doesn't), while carrying no path of any length to a `:Person` and no raw quasi-identifier. This is the **write half** of the commons (Stage 9 §1); the read half (aggregation, k-anonymity, serving) stays dormant until Stage 9.

> **Why this is a Phase-1 epic and not Stage 9.** De-identification must happen *at write time* (Stage 9 §2): a contribution can never be reconstructed from the already-discarded raw track later. The write is cheap and must start early or the commons is never viable (decision-log §12 "build now: *only* the forked write"). Aggregation is where privacy risk concentrates and is correctly designed late, against real accreted volume (Stage 9 §1). This epic ships **only the write + the structural privacy test that proves it unlinkable** — nothing aggregates or serves.

---

## Architectural context

**Builds on:**
- `ingestion/ingest_episode.py::create_episode()` — today issues **three separate auto-commit `session.run` calls** (the `:Episode` MERGE, the `Person-[:DID]->Episode` wire, the optional `Episode-[:ON]->CanonicalTrail` wire) plus a belief enqueue, then stops (lines 164–239). **There is no open transaction today** (gap-audit C1). This epic *restructures those writes into a single managed transaction* so the fork commits atomically with the Episode (S2) — atomicity is a **new requirement this epic introduces**, not one it inherits.
- `ingestion/ingest_episode.py::parse_fit()` — supplies the raw inputs `total_distance_m`, `total_ascent_m`, and `pace_on_grade` (via `compute_pace_on_grade()`). **The GPS polyline is NOT available downstream today:** `parse_fit` builds `gps_points` as a parse-loop local and retains **only start/end lat-lon** on `FITSummary` (lines 73–104); the full track is discarded before `create_episode()` runs. Endpoint-trim structurally needs the polyline, so this epic adds a track field to `FITSummary` and threads it through (S3, AC-3.0).
- `graph/schema.cypher` — the **reserved** `:CommonsObservation` / `:CommonsStat` labels (schema comment line 12: "Commons in same DB via severed-link `:CommonsObservation` (reserved)"). No uniqueness constraint exists for them yet; this epic adds the `observation_id` constraint.
- Stage 9 §2 — the design this epic builds: the born-severed `CREATE` shape (§2.1), endpoint-trim (§2.2), `writer_hash` (§2.3), and the §6 structural privacy suite (S9-13).

**Enables:** Stage 9 read half (aggregation → `:CommonsStat`), the pace-calibration model (Stage 9 §5), the Stage-9 §6 / Stage-7 §7 "severance fires" privacy invariant — which is **vacuous against absent code** today (gap-audit C1).

**Does NOT include — explicitly Stage 9:**
- **Aggregation, k-anonymity gating, the `:CommonsStat` node, and any serving/read path.** The observations accrete privately; **no aggregate node is computed and no commons fact is ever stated** in Phase 1 (Stage 9 §1, §3).
- **k-value tuning, region-specific trim radius, and quartile-fit band boundaries** — all 🔶, tuned against real accreted volume before public release (Stage 9 §2.2, §3.2, §4.2). This epic uses the v0 seeds: 250m trim and the S9-9 fixed band cutoffs.
- **Consent gating of *exposure*** (Stage 9 §8.2 / S9-17). De-identified accretion pre-consent is permitted *because the write is unlinkable*; consent gates whether rows are ever folded into a public aggregate — a Stage 9 concern. (S6 below records the per-member opt-in *flag write*, default OFF, so the gate has a substrate to read later, but enforces no exposure.)
- **Revocation execution** — `writer_hash` is *written* for a future revocation-by-re-derivation lookup (S4); the deletion flow itself is Stage 9 / retention-policy work (gap-audit M7).
- **DP / snapshot-differencing mitigations** (Stage 9 §7.5, §9).

---

## Stories

### S1 — Demote the false ✅ in the decision log FIRST (do-first-regardless)

> Audit action #1 (gap-audit C1: *"Immediately demote decision-log §32 (lines 265/282) from ✅ to 🔶 'designed, not built.' The false ✅ is the dangerous part — do this first, regardless of the rest."*). The audit's "§32" is loose: the false ✅s actually live in the **committed `docs/decision-log.md`** at **§30 line 265** ("**Commons write for episodes:** ✅ Forked write on episode creation…") and **§31 line 282** ("**Commons fork:** ✅ `CommonsObservation` written in same transaction as Episode…"), and in **`stage-6-watch-integration.md` §6.2 / S6-10** (line 373, `| … | ✅ |`). `decision-log-additions-proposed.md §40 (C1)` already *records* the demotion action — it is the corrections home, not where the false ✅ lives; do not edit it as if it carried the mark.

**Given** the commons forked write does not exist in `create_episode()`
**When** this epic opens
**Then** every wrong-memory ✅ is demoted to 🔶 "designed, not built" **before any code in this epic lands** — wrong memory is worse than none (CLAUDE.md), and a builder reading ✅ would build Stage-9 aggregation on an empty store.

**AC-1.1:** In committed `docs/decision-log.md`, the §30 line-265 "Commons write for episodes" bullet and the §31 line-282 "Commons fork" bullet each read 🔶 "designed, not built — Epic 010 pending" (not ✅). A test asserts neither bullet carries a `✅`.
**AC-1.2:** In `docs/research/stage-6-watch-integration.md`, the S6-10 decision-table row (line 373) reads 🔶 "designed, not built — Epic 010 pending", not `| … | ✅ |`.
**AC-1.3:** `docs/epics/README.md` gains an Epic 010 row (Status `IN_PROGRESS` while building, Phase 1, Depends-on `Epic 001`) and a thread-status note that T3 (commons fork) is now tracked by Epic 010 (closes the gap-audit "no tracker for T3" process miss).
**AC-1.4:** `docs/research/stage-9-commons.md`'s "🔶 designed, NOT yet built (gap-audit C1)" pointers (its §1 table row line 23 and the §2 / §8.2 banners) are repointed to "Epic 010" by name, so the design doc names its builder.
**AC-1.5 (test):** A doc-lint test (`test_s1_no_false_commons_checkmark`) greps the **commons-fork lines in committed `decision-log.md` §30/§31 and `stage-6-watch-integration.md` S6-10** and **fails** if any carries a `✅` — the wrong-memory regression guard. The grep must target those exact lines (not `decision-log-additions-proposed.md §32`, which is the *Stage-3 ingestion-pipeline* section and carries no commons-fork claim — pointing the guard there would make it pass vacuously, the same C1 failure mode this epic kills).

### S2 — The born-severed `:CommonsObservation` write, atomic with the Episode

**Given** `create_episode()` writes the Episode (today via separate auto-commit `session.run` calls)
**When** this epic restructures the Episode + Person-`DID` + Episode-`ON` writes **and** the new `:CommonsObservation` `CREATE` into **one managed transaction** (`session.execute_write(...)` / `begin_transaction()`), committed before the function returns
**Then** the `:CommonsObservation` is **`CREATE`d with no inbound or outbound edge to any `:Person`/`:Episode`/`:Outcome`** — a separate node born without a back-edge, never the episode node with the owner stripped (Stage 9 §2.1). `trail_id` and `segment_ids` are stored as **scalar property values, not edges** (FK-by-value to the unowned world layer; the only join is a value-match performed by a future aggregation job, never a graph path — Stage 9 §2.1, §3.1).

**AC-2.0 (single transaction):** The Episode MERGE, `Person-[:DID]->Episode`, optional `Episode-[:ON]->CanonicalTrail`, and the `:CommonsObservation` `CREATE` all execute in **one managed transaction** — replacing today's three auto-commit `session.run` calls. A test asserts the four writes commit together or not at all. *(This atomicity is introduced here; it does not exist in current code.)*
**AC-2.1:** After `create_episode()`, exactly one `:CommonsObservation` exists per successfully-written `:Episode`, carrying `observation_id` (`randomUUID()`), `trail_id`, `segment_ids` (list), `capability_band`, `month`, `ascent_bucket`, `distance_bucket`, `trimmed_track`, `writer_hash`, `ingest_version`, `written_at`. *(matches the Stage 9 §2.1 `CREATE` shape exactly)*
**AC-2.2:** The `:CommonsObservation` has **no `owner_id` property** (assert the property is absent, not null).
**AC-2.3:** The write is a `CREATE` (not `MERGE`-onto-the-episode, not copy-then-strip): the node is born with zero relationships of any type. A test asserting `count{ (co)--() } = 0` immediately after write passes. *(Stage 9 §2.1 "a security test cannot prove a transient edge never existed"; born-severed has no such window.)*
**AC-2.4:** `trail_id` equals the matched `canonical_id` (the same value passed to the `Episode-[:ON]->CanonicalTrail` MERGE) when a trail matched, and is `null` when unmatched — stored as a **property**, with **no** `:CommonsObservation`-to-`:CanonicalTrail` edge created (assert no such relationship exists).
**AC-2.5:** With AC-2.0's single transaction in place, a forced post-fork failure rolls back **all four** writes together: **neither** the `:Episode`, the `Person-[:DID]` edge, the `Episode-[:ON]` edge, **nor** the `:CommonsObservation` persists (atomicity — Stage 9 §2.1 "either both commit or neither"). A test that injects a post-fork exception asserts zero `:Episode` and zero `:CommonsObservation` rows survive. *(Depends on AC-2.0; under today's auto-commit code this guarantee is unachievable — a committed orphan Episode would remain.)*
**AC-2.6 (schema):** `graph/schema.cypher` adds `CREATE CONSTRAINT commons_observation_id IF NOT EXISTS FOR (co:CommonsObservation) REQUIRE co.observation_id IS UNIQUE;` — realizing the reserved label, Community-Edition-safe single-property uniqueness.

> **C2 note (write-path access control).** Like every owned-node write today (gap-audit C2), `create_episode()` runs through the raw unscoped session/runner (`make_runner`), not the read-only `ScopedSession` choke point (which governs **reads** only). The `:CommonsObservation` is **unowned by construction** (no `owner_id`, AC-2.2), so it is *correctly* outside the owner-scope seam. This epic adds **no** new owned-node write — only an unowned-node `CREATE` and a transaction restructure of the existing owned writes. Record this so a future C2 fix (a `run_write` seam) doesn't mistakenly try to owner-scope the commons write.

### S3 — Endpoint-trim + capability band + coarse buckets (the quasi-identifier reduction)

**Given** the raw FIT inputs (`pace_on_grade`, `total_distance_m`, `total_ascent_m`, the GPS track, the episode `start_time`)
**When** the `:CommonsObservation` properties are computed, **contributor-side, before they cross into the commons node** (Stage 9 §4.1 — the raw pace must never enter `:CommonsObservation` even momentarily)
**Then** every high-entropy field is reduced to a bucket/band, and the track has its identifying endpoints removed:

- **Endpoint-trim 250m:** strip the first and last 250m of the polyline before the commons write; the private `:Episode` retains the full track, only the commons twin is trimmed (Stage 9 §2.2, S5-10).
- **Capability band (raw pace → band):** substitute `pace_on_grade` with one of the four **S9-9** bands (which supersede the divergent S5-11 set and resolve gap-audit M10); the raw pace never appears on the observation (Stage 9 §4.1, §4.2):

  | Band | Range (min/km, grade-adjusted) |
  |---|---|
  | `easy` | `< 12` |
  | `easy-moderate` | `[12, 16)` |
  | `moderate` | `[16, 20)` |
  | `strenuous` | `≥ 20` |

  Boundaries are **half-open `[lo, hi)`** so no value falls in two bands (Stage 9 §4.2 / S9-9).
- **Month bucket:** `"YYYY-MM"`, derived from the episode `start_time` — **never the raw date** (Stage 9 §3.3).
- **Ascent / distance buckets:** bucketed (ascent in 200m bands; distance in a coarse band), never the raw totals (Stage 9 §3.3).

**AC-3.0 (track capture — code-accurate precondition):** `parse_fit()` retains the GPS polyline (a new `FITSummary` field, e.g. `gps_track`) and threads it to `create_episode()`'s de-id transform — because the polyline is **not available today** (only start/end lat-lon survive parse, lines 73–104). The **full** track is **not** added to the `:Episode` (Rule #3 / §35 "raw biometrics not in the graph"); it is consumed in-transform to produce `trimmed_track` for the commons twin only. A test asserts the full polyline appears on no `:Episode` property and only the trimmed track reaches the observation.
**AC-3.1:** `start_time` capture is **unconditionally owned by this story** (`parse_fit` has no `start_time` field today and `create_episode` never writes `e.date` — gap-audit M1, which has no owning epic). `parse_fit` captures the session `start_time`; the de-id transform derives the `"YYYY-MM"` month from it. **Boundary:** this epic writes **only the month bucket** to the commons node; whether `e.date` / `PhysicalProfile.last_episode_at` is also written to the private `:Episode` (the rest of M1) is **out of scope** and left to a named M1 dependency (recorded in the DoD). No raw date crosses to the observation regardless.
**AC-3.2:** `trimmed_track` startpoint is **> 250m** from the raw track startpoint, and `trimmed_track` endpoint is **> 250m** from the raw track endpoint (the trim provably fired). *(unit-level check; the structural/CI version is S5)*
**AC-3.3:** `trimmed_track` is `null` when no GPS track is present (degrade gracefully — Stage 9 §2.1 "null if no GPS"). No band/bucket field is null on that account; only the track.
**AC-3.4:** `capability_band` is one of `{easy, easy-moderate, moderate, strenuous}` and **never** the raw pace value; the four boundary cases (`11.99→easy`, `12.0→easy-moderate`, `16.0→moderate`, `20.0→strenuous`) land in the correct half-open band. A test asserts no `:CommonsObservation` property anywhere equals the episode's raw `pace_on_grade`.
**AC-3.5:** `month` matches `^\d{4}-\d{2}$` and equals the episode `start_time`'s year-month; **no raw date, day, or timestamp** appears on the observation (assert no property parses as a full date).
**AC-3.6:** `ascent_bucket` and `distance_bucket` are coarse bucket labels (e.g. `"200-400"`), not the raw `ascent_m` / `distance_m`; a test asserts neither equals the raw total.
**AC-3.7:** The band substitution is **pure arithmetic** (a threshold lookup) — no model/provider call is made on the commons-write path (Stage 9 §4.1; consistent with local-first sensitivity routing, Rule #5). A test asserts the write path invokes no provider.

### S4 — `writer_hash` for revocation-by-re-derivation (one-way, not a back-edge)

**Given** the contributor's `member_id` and a secret salt from the secrets store
**When** the `:CommonsObservation` is written
**Then** `writer_hash = HMAC(secret_salt, member_id)` is stored — **deterministic** (the same member always hashes identically, so their observations are findable for deletion), **non-reversible** (the salt never enters the graph), and **not a quasi-identifier** (a single opaque value shared across all of one person's observations, carrying zero external linkage) (Stage 9 §2.3 / S9-3).

**AC-4.1:** `writer_hash` is an HMAC keyed by a salt sourced from config/secrets, **never** a plain hash of `member_id` (a plain hash of the small enumerable member-id space is brute-forceable — Stage 9 §2.3). A test asserts the same `member_id` yields the same hash, and two different members yield different hashes.
**AC-4.2:** The salt is **never** written to the graph and never appears on any node property (Rule #10 / §2.3). A test asserts no `:CommonsObservation` property equals the salt.
**AC-4.3:** `writer_hash` does **not** equal `member_id`, and `member_id` is not derivable from the observation — the only thing that can reproduce the hash is the secrets-manager salt plus the member's own id at request time. The graph contains **no stored mapping** from hash back to person.
**AC-4.4:** `writer_hash` is a **property value, not a graph edge** — it creates no path from observation to person (this is the precondition for S5's no-path invariant; revocation is a *forward property lookup keyed by a re-derived hash*, never a traversal — Stage 9 §2.3, §6 assertion 1).

> Revocation *execution* (re-derive the requester's hash, property-match, delete pre-aggregate rows) is **Stage 9 / retention** (gap-audit M7), not this epic. Epic 010 only *writes the handle* so revocation is possible later.

### S5 — The structural privacy test lands WITH the write (must fail against absent code)

> Stage 9 §6 / S9-13 / gap-audit C1 action #4: land the structural privacy test **before more episode-write code lands**. The whole point of C1 is that a test against *absent* code **vacuously passes** — a false guarantee. This test must therefore be written so it **fails** if the fork is removed or never wrote.

**Given** an episode is ingested through `create_episode()` (with and without a GPS track)
**When** the structural privacy suite runs in CI
**Then** all three independently-testable unlinkability properties hold (Stage 9 §2.3, §6) — and the suite is constructed so it cannot pass vacuously.

**AC-5.1 (no path, any length):** There is **no path of any length** from any `:CommonsObservation` to any `:Person`, `:Episode`, or `:Outcome`. The test asserts graph reachability is empty (e.g. `MATCH (co:CommonsObservation), (p:Person) WHERE EXISTS { (co)-[*]-(p) } RETURN count(*)` = 0; likewise for `:Episode`, `:Outcome`). The `writer_hash` property is **not** a graph edge and does not constitute a path (Stage 9 §6 assertion 1 / §2.3).
**AC-5.2 (trim fired):** No `:CommonsObservation.trimmed_track` startpoint falls within the 250m trim radius of the corresponding private `:Episode`'s raw startpoint (Stage 9 §6 assertion 3 / decision-log §17 "does endpoint-trimming actually fire?"). Skipped only for the no-GPS case (AC-3.3), which the test asserts separately produces `trimmed_track = null`.
**AC-5.3 (raw track / raw pace absent):** The raw full track is **absent** from the `:CommonsObservation`, and no observation property equals the episode's raw `pace_on_grade`, raw `distance_m`, raw `ascent_m`, or raw date (the no-raw-quasi-identifier property — Stage 9 §2.3, §6 assertion 2).
**AC-5.4 (non-vacuity — the load-bearing AC):** The suite **fails against absent code.** A test (`test_s5_privacy_suite_not_vacuous`) asserts that for the ingested episode **at least one `:CommonsObservation` was actually written** (count ≥ 1) *before* the no-path/trim/raw-absent assertions run — so a regression that silently stops writing the fork turns the suite **red**, not green. (This directly closes the C1 "vacuously pass against absent code" failure mode.)
**AC-5.5:** The suite runs in CI as part of `make check` and is referenced from the Stage-9 §6 / Stage-7 §7 privacy-invariant home so the "severance fires" guarantee is real, not aspirational.

### S6 — Consent flag substrate (write-only, default OFF) — *exposure gate is Stage 9*

> Stage 9 §8.2 / S9-17: **consent gates *exposure*, not the *write*.** De-identified accretion pre-consent is permitted *because the write is unlinkable* (S2–S5). This story records the per-member opt-in flag so Stage 9's aggregation has a substrate to read; it enforces **no** exposure (there is no read/aggregation in Phase 1).

**Given** a `:Person`
**When** the schema/onboarding records commons-contribution consent
**Then** a `commons_opt_in` flag exists on `:Person`, **default OFF**, separate from person-to-person sharing grants (decision-log §12 "own consent, separate from grants").

**AC-6.1:** `:Person` carries `commons_opt_in` (boolean), defaulting `false` when unset (a Person with the property absent is treated as not-opted-in by any future reader). *(Provides the write-side consent substrate; the opt-in onboarding surface is Stage 9.)*
**AC-6.2:** The commons **write still fires regardless of `commons_opt_in`** (the write is unlinkable, so accretion is not a contribution of identifiable data — Stage 9 §8.2). A test asserts a `:CommonsObservation` is written even when `commons_opt_in = false`.
**AC-6.3:** A doc note (in this epic's DoD and the §8.2 pointer) records that **public-exposure default is OFF** and that whether pre-consent observations become retroactively eligible on opt-in is **open pending the T6 legal read** (Stage 9 §8.2, recommend post-consent only) — this epic neither aggregates nor exposes, so it does not resolve it.

---

## Definition of Done

- [x] **S1 done first:** committed `decision-log.md` §30:265 and §31:282 commons-fork bullets read 🔶 (not ✅); `stage-6-watch-integration.md` S6-10 reads 🔶; README Epic 010 row + T3 thread note added; stage-9 pointers name Epic 010 (AC-1.1–1.4); doc-lint regression guard targets the real false-✅ lines and is green (AC-1.5).
- [x] `:Episode` + `Person-[:DID]` + `Episode-[:ON]` + `:CommonsObservation` writes restructured into **one managed transaction** (`ScopedSession.execute_write`, replacing the auto-commit calls); the `:CommonsObservation` is born-severed (no `:Person`/`:Episode`/`:Outcome` edge, no `owner_id`), `trail_id`/`segment_ids` as scalars (S2; AC-2.0–2.6), with the schema constraint added. *(Write is a retry-idempotent `MERGE` on a contributor-minted random `observation_id`, not a bare `CREATE` — still born-severed, but safe under managed-transaction auto-retry; per the review.)*
- [x] `parse_fit` retains the GPS polyline + `start_time`; endpoint-trim 250m + raw pace → 4-band half-open **S9-9** capability band + month/ascent/distance buckets, all computed contributor-side before the commons node, no raw date, no model call, full track never on the `:Episode` (S3; AC-3.0–3.7). `e.date` (rest of M1) explicitly **deferred** to a named M1 dependency.
- [x] `writer_hash = HMAC(salt, member_id)`: one-way, salt never in the graph, property-not-edge (S4; AC-4.1–4.4).
- [x] The structural privacy suite (no-path-any-length · trim-fired · raw-absent) lands **with** the write and **fails against absent code** via the non-vacuity guard (S5; AC-5.1–5.5). *(DB-free structural proof — a `MERGE`d node with no relationship syntax, never re-referenced, can have no path; stronger than a live reachability query against a transient edge.)*
- [x] `commons_opt_in` flag on `:Person` (default OFF), write fires regardless, eligibility-on-opt-in noted as open pending T6 (S6; AC-6.1–6.3).
- [x] All ACs covered by ≥1 passing test (named `test_s{story}_{ac}_{desc}`); tests written with the code they cover.
- [x] `make check` green (ruff format + ruff + mypy + pytest) — 279 tests.
- [x] **Adversarial review run** (6 dimensions: Rule #8 severance · Rule #5 raw-leak · Rule #3 raw-track · atomicity · Rule #10 salt-hygiene · AC/non-vacuity → per-finding verification; 4 raw → 4 confirmed, **all MINOR, all fixed**: retry-idempotent commons MERGE; AC-3.7 no-provider guard; AC-2.1/2.6 observation_id+constraint guards; AC-6.1 default-OFF schema-lint). No CRITICAL/MODERATE.
- [x] Atomic commits (S1 doc demotion · schema+config substrate · de-id module · execute_write+builder · `create_episode` transaction + privacy suite · review hardening · epic close), each with a *why* body.
- [x] Committed and pushed; `docs/epics/README.md` Epic 010 row → `DONE ✅`; stage-9 §1 table row updated to "✅ write built (Epic 010); aggregation dormant (Stage 9)".

> **Interpretation note (S6).** The task brief's "gate on `Person.commons_opt_in` (default False)" is built as the epic specifies: the flag is the **write-side substrate** (default OFF), and the de-identified write **fires regardless** of it — consent gates Stage-9 *exposure*, not the write (S6 / Stage 9 §8.2 / S9-17; the write is unlinkable, so pre-consent accretion is not a contribution of identifiable data, and the substrate must accrete from day one or it is un-backfillable). If a write-gated reading was intended instead, that is a one-line change (`if commons_salt and person_opted_in:`), but it contradicts the epic + Stage-9 decisions and would defeat the accretion thesis.
> **Watch-path note.** Both ingestion paths fork: the CLI (`ingest_episode`) threads the salt from `Settings`; the watch poller (`scripts/watch_sync.py`) binds it via `functools.partial` (no `run_sync` signature change).

**Scope reminder (carried, not solved here):** aggregation, k-anonymity, the `:CommonsStat` node, serving, k/trim/band tuning, revocation *execution*, consent *exposure-gating*, the `e.date` half of M1, and the snapshot-differencing / DP mitigations are **all out of this epic** (Stage 9 §1, §3, §7.5, §8, §9; gap-audit M1/M7). Epic 010 ships the unlinkable write and the proof — nothing reads it.
