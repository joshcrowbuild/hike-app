# Epic 044 — History import: years of hikes become trip memory (B003)

**Status:** DEFINED
**Phase:** C (Real Intake)
**Spec refs:** [`../strategy/path-to-complete.md`](../strategy/path-to-complete.md) Phase C (B003 + the map-matching risk + Open Decision #10) · CDP-20 (HMM snap) · CLAUDE.md Rules #6/#7 · Epic 031 (GPX reader, DONE) · decision-log §47 · Epics 025/027 (the corpus quality-gate discipline this import mirrors — S6)

> **Build gate (hard):** ToS/consent + **data export/deletion** must exist before this epic ingests real personal history — the deletion right is a precondition of health-adjacent intake (path-to-complete Phase-C dependencies; pulled forward from Phase B by §47). Epic 043 (auth) must land first.

---

## Capability statement

The owner imports a historical activity archive (Garmin bulk export / GPX files) and it becomes real trip memory: Episodes with `source:"import"`, capability beliefs from measured history, and `been_on` beliefs wherever a track confidently matches a corpus trail — pre-warming taste from day one and unblocking the novelty filter (Epic 006).

## Architectural context

**Builds on:** Epic 031 (GPX reader tolerance) · Epic 001 (belief pipeline) · Epic 011 (scoped writes) · Epic 043 (verified identity)
**Enables:** Epic 006 novelty (the `been_on` producer it was blocked on) · the Stage-7 memory eval · the "what we believe about you" transparency surface
**Does NOT include:** Strava/Garmin *API* integrations (archive-file first) · live watch sync (Epic 004 owns it) · any commons emission (imports are private-overlay only) · an upload UI (v1 is an operator-run local batch — see AC-1.3)

---

## Stories

### S1 — Ingest an archive, idempotently

**Given** a local Garmin bulk-export (FIT) or a folder of GPX files
**When** the import job runs for a verified `viewer_id`
**Then** each activity parses through the Epic 031 tolerance path and lands exactly once

**AC-1.1:** re-running the import creates no duplicates (activity-id / start-time + content-hash dedupe)
**AC-1.2:** unparseable files are skipped **with disclosure** — a run summary names every skipped file and why; never silently dropped, never fabricated
**AC-1.3:** v1 runs local-first as a batch job (route private data by sensitivity); no upload endpoint yet

### S2 — Activities become Episodes, honestly

**AC-2.1:** each Episode carries `source:"import"`, `date` from the track, and measured fields only where the file actually has them — absent fields stay null (degrade-and-disclose, never zeros)
**AC-2.2:** all writes go through the scoped-write seam under the verified viewer

### S3 — Map-matching with a never-blocks fallback (Open Decision #10)

**Given** a track that must bind to a corpus trail to produce a `been_on` edge
**When** matching runs
**Then** a confident match writes the belief, and an unconfident one still preserves the trip

**AC-3.1:** a confident match writes `been_on` carrying provenance + confidence + timestamp — recorded as an *inference*, never a stated fact (Rule #7)
**AC-3.2:** a low-confidence match falls back to a **free-floating Episode with geometry** (matched opportunistically later) — the import NEVER produces zero value because matching is hard
**AC-3.3:** match confidence is disclosed on read ("likely Cascade Pass — low confidence, GPS sparse"); the rigorous Newson-Krumm HMM snap (CDP-20) is the eventual implementation, not a v1 requirement

### S4 — Measured history feeds capability beliefs (per-activity channels — decision-log §48)

**AC-4.1:** imported pace/duration flow through the existing Epic 001 pipeline (EWMA, maxima, N=3 promotion) with `provenance:"import"`, written to the **activity's own channel** (`pace(hike)`, `pace(run)` are distinct beliefs)
**AC-4.2:** capability ≠ preference holds — imports update capability; preference beliefs still come only from outcomes/stated input (Rule #7)
**AC-4.3 (no cross-channel bleed):** hiking predictions (duration estimates, effort screens) read only hike-channel beliefs; run pace/maxima can never set a hiking pace or distance maximum — falsification-tested (a fast imported run must not change a hiking duration estimate)
**AC-4.4 (hedged endurance floor — the only bridge):** consistent running history may set an aerobic-endurance *floor* at cold-start, carried as an inference with provenance + confidence (Rule #7), disclosed on any surface that uses it, and displaced as real hike evidence accrues

### S5 — Privacy posture

**AC-5.1:** processing is local-first; nothing from the import reaches a cloud model (the C4 egress guard covers the read path)
**AC-5.2:** residual metadata is stripped on any future emit path (the Strava privacy-zone leak is the cautionary tale); imports never write to the commons fork
**AC-5.3 (no biometrics — §49):** heart-rate/biometric streams are dropped at parse time and never reach the graph; pace/GPS/duration only. Revisit only with a named consumer + its own consent line.

### S6 — Import-quality gates + run report (corpus-grade discipline)

*The personal import holds the same ingestion-quality bar as the trail corpus (Epics 025/027's posture), adapted to an additive, personal pipeline: screens and validity gates in the load path, and a per-run report instead of the destructive-ingest guards (prune-ratio etc.) that only make sense for a repeated, pruning ingest.*

**Given** a real archive containing rides, runs, gym sessions, and GPS-glitched tracks alongside hikes
**When** the import runs
**Then** only quality-screened foot travel shapes the user's hiking profile, and everything else is counted and disclosed — never silently absorbed, never silently dropped

**AC-6.1 (activity-type screen — resolved by decision-log §48):** a config-driven allowlist of foot-travel activity types (hike, walk, run incl. trail run) produces Episodes tagged `activity_type`; all foot travel counts fully for `been_on`/novelty/trip memory. Non-foot activities (ride, swim, gym…) are excluded from Episode creation and **counted per type in the run report**. Capability separation is S4's job (per-activity channels), not this screen's.
**AC-6.2 (track-validity gates):** beyond Epic 031's tolerance path, physically implausible tracks (sustained speed above a foot-travel ceiling, teleporting fixes, null-island points) are barred from feeding capability beliefs — a glitched track can never set a pace/distance maximum. The trip itself is still preserved (free-floating Episode, geometry kept) with its exclusion reason disclosed: degrade-and-disclose, never discard.
**AC-6.3 (run report — the ingest-diff analog):** every run emits a persisted report: files parsed / skipped (each with a reason) · activities screened by type · Episodes created · matched vs. free-floating · capability-eligible vs. quality-excluded. Reports are comparable across re-runs (the Epic 027 pattern), so a re-import that suddenly parses far fewer activities is visible, not silent.
**AC-6.4 (no silent loss — falsification-tested):** the totals reconcile: every activity in the archive appears in exactly one report bucket. A planted unparseable file, a planted bike ride, and a planted teleporting track each surface in the report with the right reason (the same falsification bar the corpus gates are held to).

---

## Definition of Done
- [ ] All ACs tested; the S3 fallback falsification-tested (a garbage track still lands as a free-floating Episode)
- [ ] S6 gates falsification-tested (planted junk of each class lands in the right report bucket, and none of it touches capability beliefs)
- [ ] `make check` green
- [ ] Live verification: the owner's real archive imported; the run report's totals reconcile against the archive; `been_on` count > 0 OR the fallback path disclosed honestly; Epic 006 demonstrably unblocked
- [ ] Targeted review agent run; CRITICALs fixed
