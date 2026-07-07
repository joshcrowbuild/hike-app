# Epics Index

Status legend: `BACKLOG` · `DEFINED` · `IN_PROGRESS` · `REVIEW` · `DONE ✅` · `BLOCKED 🚫`

| # | Epic | Status | Phase | Depends on |
|---|---|---|---|---|
| [001](epic-001-belief-update-pipeline.md) | Belief update pipeline (EWMA pace, maxima, N=3 promotion) | DONE ✅ | 1 | Stage 5 schema |
| [002](epic-002-outcome-card-endpoint.md) | Outcome card endpoint (POST /episode/{id}/outcome) | DONE ✅ | 1 | Epic 001 |
| [003](epic-003-context-assembly.md) | Context assembly in engine.plan() | DONE ✅ | 1 | Epic 001 |
| [004](epic-004-device-integration-seam.md) | Device-integration seam (Garmin + Coros, pluggable) | DONE ✅ | 1 | Epic 001 |
| [005](epic-005-valhalla-drive-time.md) | Valhalla drive-time integration (post-Scout prune + ranking input) | DONE ✅ | 0 | — (via Epic 013) |
| [006](epic-006-novelty-filter.md) | Novelty filter in Curator | DEFINED | 1 | Epic 003 |
| 007 | Readiness filter (Body Battery → Curator parameter) | BACKLOG | 1 | Epic 004 |
| 008 | API tests (FastAPI TestClient, /plan + /health) | REVIEW | 0 | — |
| [009](epic-009-eval-harness-expansion.md) | Stage-7 eval-harness expansion (fixtures, golden trips, judge, N-run regression, security/privacy) | DEFINED | 1→2 | Stage 7 methodology |
| [010](epic-010-commons-fork-write.md) | Commons fork write (de-identified `:CommonsObservation`) | DONE ✅ | 1 | Epic 001 |
| [011](epic-011-scoped-write-seam.md) | Scoped-write seam (`run_write` guard + owned-node builders) | DONE ✅ | 1 | Epic 001 |
| [012](epic-012-corpus-source-seam.md) | CorpusSource seam (contract + registry; OSM-as-spine a declared role) | DONE ✅ | 1 | Stage 3 ingestion |
| [013](epic-013-live-adapter-seam.md) | LiveAdapter seam (kind-keyed registry, failover, Valhalla drive-time, TTL) | DONE ✅ | 1 | Epic 003 |
| [014](epic-014-overlay-egress-and-viewer-auth.md) | Private-overlay egress + viewer-auth hardening (C3 + C4) | DONE ✅ | 1 | Epic 003 |
| [015](epic-015-ci-neo4j-integration.md) | CI Neo4j integration (live owner-isolation guardrail; separate required leg) | DONE ✅ | 1 | Epic 011 |
| [016](epic-016-maps-and-terrain.md) | Maps & terrain (topographic Detail map · route · elevation profile) | DEFINED | 1 | Epic 013 · 017 (S5) |
| [017](epic-017-terrain-elevation-enrichment.md) | Terrain elevation enrichment (USGS 3DEP profiles; parallel to 016) | IN_PROGRESS | 1 | Epic 012 · `geom_wkt` |
| [018](epic-018-live-conditions-on-the-card.md) | Live conditions on the card (JIT overlay wiring; sourced weather/water/air/fire/permits + four-state silence) | DEFINED | 1 | Epic 013 · #53/#54 |
| [022](epic-022-duration-truth.md) | Duration truth (wire the dead-computed Naismith estimate through the live feed with a render-layer estimate disclosure) | DONE ✅ | 1 | Epic 016 · 017 |
| [023](epic-023-agency-length.md) | Capture authoritative USFS/NPS length + re-assemble NPS multi-part trails | DONE ✅ | A | — |
| [030](epic-030-slug-collision.md) | Guard the unguarded short-slug canonical_id collision + re-runnable audit | DONE ✅ | A | — |
| [025](epic-025-validity-exclusions.md) | Wire geometry/null-island validity into the load path + externalize trail-filter denylists to config | DONE ✅ | A | Epics 023 · 030 |

| [024](epic-024-schema-format.md) | Schema-format axis (integer `schema_format` on `:Meta` + API startup gate via /health disclose) | DONE ✅ | A | — |
| [028](epic-028-gpx-export.md) | GPX export (`GET /trail/{id}/export.gpx`) + Send-to-device on Detail (CoMaps borrow §D4) | IN_PROGRESS | 1 | Epic 022 · 024 |

| [027](epic-027-facet-ingest-diff.md) | Per-facet leveled ingest-diff check (within-run) + stats on /health | DONE ✅ | A/B | Epic 024 |
| [038](epic-038-trail-search-geocoder.md) | Trail-name search + geocoder seam (B001) — spec-complete spike, no product code | REVIEW | E | — |

| [037](epic-037-openmeteo-failover.md) | Open-Meteo weather availability-failover (reshaped: refuses corroboration as feed-counting; specs failover + spread-disclosure) | REVIEW | Spike | Epic 013 · downstream build BLOCKED on commercial-license PO decision |

| [033](epic-033-opentopodata-fallback-sampler.md) | OpenTopoData fallback ElevationSampler (degrade-and-disclose network elevation transport) | REVIEW | 1 | Epic 017 |

| [032](epic-032-grade-aware-eta.md) | Grade-aware pedestrian ETA (port Valhalla's MIT grade-speed curve; per-segment integral replaces flat Naismith) | REVIEW | 1 | Epic 022 · 016 · 017 |

| [035](epic-035-osm-water-overlay.md) | OSM on-trail water-source overlay (fetch + persist + proximity read; no potability claim) | REVIEW | 1 | — |

> **Thread T2 (access control):** the owned-node **write** path now goes through `ScopedSession.run_write` + the `graph.queries` builders (Epic 011), extending Rule #4 from reads to writes. Epic 003's context-assembly Cypher should route through `graph.queries` (the gap-audit M9 redirect), which exists now that 011 has landed.
>
> **Thread T3 (commons fork):** tracked by **Epic 010** (closes the gap-audit "no tracker for T3" process miss). The de-identified `:CommonsObservation` forked write — marked ✅ in the decision log, then found unbuilt (gap-audit C1), **now built by Epic 010** — is the write half of the commons, accreting born-severed observations from day one; the read half (aggregation, k-anonymity) stays dormant until Stage 9.

---

## How to use this index

1. Pick the next `DEFINED` epic at the top of the dependency chain.
2. Change its status to `IN_PROGRESS` and add your name/date.
3. Work through stories in order; check off ACs as you verify each one.
4. When all ACs pass + targeted review is clean → `REVIEW`.
5. After review findings fixed → `DONE ✅`, push, update this table.

## Adding a new epic

1. Create `docs/epics/epic-NNN-name.md` from the template below.
2. Add a row here with status `BACKLOG`.
3. When you sit down to define it fully (stories + ACs), change to `DEFINED`.

## Epic template

```markdown
# Epic NNN — Name

**Status:** DEFINED
**Phase:** N
**Spec refs:** Stage N §X · decision-log §N

---

## Capability statement
One sentence: what the system/user can do after this that they couldn't before.

## Architectural context
Builds on: ...
Enables: ...
Does NOT include: ...

---

## Stories

### S1 — Story name

**Given** [context]
**When** [action]
**Then** [outcome]

**AC-1.1:** ...
**AC-1.2:** ...

[repeat for S2, S3…]

---

## Definition of Done
- [ ] All ACs covered by at least one passing test
- [ ] `make check` green
- [ ] Targeted review agent run; CRITICALs fixed
- [ ] Committed and pushed
```
