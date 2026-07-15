# Epic 044 — History import: years of hikes become trip memory (B003)

**Status:** DEFINED
**Phase:** C (Real Intake)
**Spec refs:** [`../strategy/path-to-complete.md`](../strategy/path-to-complete.md) Phase C (B003 + the map-matching risk + Open Decision #10) · CDP-20 (HMM snap) · CLAUDE.md Rules #6/#7 · Epic 031 (GPX reader, DONE) · decision-log §47

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

### S4 — Measured history feeds capability beliefs

**AC-4.1:** imported pace/duration flow through the existing Epic 001 pipeline (EWMA, maxima, N=3 promotion) with `provenance:"import"`
**AC-4.2:** capability ≠ preference holds — imports update capability; preference beliefs still come only from outcomes/stated input (Rule #7)

### S5 — Privacy posture

**AC-5.1:** processing is local-first; nothing from the import reaches a cloud model (the C4 egress guard covers the read path)
**AC-5.2:** residual metadata is stripped on any future emit path (the Strava privacy-zone leak is the cautionary tale); imports never write to the commons fork

---

## Definition of Done
- [ ] All ACs tested; the S3 fallback falsification-tested (a garbage track still lands as a free-floating Episode)
- [ ] `make check` green
- [ ] Live verification: the owner's real archive imported; `been_on` count > 0 OR the fallback path disclosed honestly; Epic 006 demonstrably unblocked
- [ ] Targeted review agent run; CRITICALs fixed
