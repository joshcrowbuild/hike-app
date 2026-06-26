# Plan Analysis — Definition Readiness Audit

*Generated 2026-06-23. Re-run before starting each new epic.*

Legend: ✅ Ready to build · 🔶 Needs design · ❌ Blocked · ⬜ Not started

---

## Stage-by-stage readiness

| Stage | Design doc | Decisions | Code | Gaps |
|---|---|---|---|---|
| 0 — Setup | — | ✅ | ✅ | None |
| 1 — Data sources | stage-1-data-sources.md | ✅ | ✅ | None |
| 2 — Schema | stage-2-schema.md | ✅ | ✅ v0.2.0 | None |
| 3 — Corpus pipeline | stage-3-corpus-pipeline.md | ✅ | ✅ | USFS bulk-file; OSM consolidation done |
| 4 — Engine + cost | stage-4-engine-and-cost.md | ✅ | ✅ | Bake-off done; cost spike deferred |
| 5 — Personalization | stage-5-personalization.md | ✅ | ✅ schema | **Belief update pipeline unbuilt** (Epic 001) |
| 6 — Watch integration | stage-6-watch-integration.md | ✅ | 🔶 | FIT parsing stub done; poller, belief update, outcome card unbuilt |
| 7 — Eval deep-dive | ❌ no doc | ❌ | ❌ | Entire stage undesigned |
| 8 — Multiplayer | ❌ no doc | ❌ | ❌ | Entire stage undesigned |
| 9 — Commons | ❌ no doc | ❌ | ❌ | Forked write wired in Stage 6 design; aggregation undesigned |
| 10 — Experience | ❌ (3 wireframes sketched) | ❌ | ❌ | UX undesigned |
| 11 — Native | ❌ no doc | ❌ | ❌ | Entire stage undesigned |

---

## Well-defined items (ready to build now)

### From Stage 6

| Item | Spec location | Effort |
|---|---|---|
| Belief update pipeline (EWMA pace, maxima, N=3 promotion) | §4.1–4.3 | S |
| `scripts/watch_sync.py` — Garmin Connect activity poller | §2.1 | M |
| Outcome card API endpoint (POST /episode/{id}/outcome) | decision-log §10 + Stage 5 §1 | S |
| Coros MCP `.mcp.json` wiring | §5.1 | XS |
| Commons fork (`CommonsObservation`) on Episode creation | §6.2 | S |

### Infrastructure gaps

| Item | Spec | Effort |
|---|---|---|
| API tests (FastAPI TestClient, /plan + /health) | Obvious | S |
| Valhalla drive-time filter | decision-log §27 + valhalla.py adapter | M |
| Garmin Connect adapter (`python-garminconnect`) | §1.1 | M |

---

## Underdefined items (need design before building)

| Item | What's missing | Owner action |
|---|---|---|
| **Novelty filter** | No implementation spec. How `been_on` beliefs appear in Curator prompt; whether it's a hard filter or a ranking adjustment; the discount formula | 30-min design session |
| **Area ingestion** | No design for fetching NPS park boundaries, what data source, field names, how trails link to areas during pipeline | 20-min design session |
| **heat_response inference** | Depends on NWS historical archive — endpoint not confirmed reachable; may need a spike to validate | Spike: 1 hour |
| **GPS track overlap matching** | Requires `geom_wkt` on CanonicalTrail nodes (currently illustrative values); needs real populated geometries | Spike: populate WKT from OSM geometry, then test |
| **Outcome card — belief promotion trigger** | The `Outcome` node write is clear; what happens after (does N=3 check fire immediately? scheduled?) is not specified | 20-min design session |
| **Readiness filter (Body Battery)** | Stage 6 §5.3 says "readiness filter parameter" but the Curator prompt change and Scout filter logic are not specified | 30-min design session |
| **Context assembly implementation** | Stage 5 §4 has Cypher sketches but the Python code integrating it into `engine.plan()` is unspecified | 30-min design session |
| **Stage 7 — Eval methodology** | No doc, no spec. This is the "hardest, role-defining stage" — needs dedicated design. | Design session |

---

## Blocked items (dependency or external constraint)

| Item | Blocker |
|---|---|
| Always-on Garmin poller | Needs a persistent host (VPS/Pi) — deferred to Stage 8 |
| Coros batch ingestion | Need a real Coros account for live testing |
| Garmin live testing | Fragile unofficial API — needs careful sandboxing |
| GPS track overlap matching | `geom_wkt` on graph nodes is currently illustrative |
| Stage 8+ | Stages 7 design must come first |
| Public commons release | ODbL + consent resolved (T6) — not yet done |

---

## Architectural dependency order for next build work

```
Belief update pipeline (Epic 001)          ← no deps, ready now
  └─ Outcome card endpoint (Epic 002)      ← after belief update (it triggers N=3 check)
       └─ Context assembly in engine       ← after beliefs exist and are populated
            └─ Novelty filter              ← needs context assembly + been_on beliefs
                 └─ Stage 7 eval harness   ← needs all of above to evaluate
Garmin Connect poller (parallel)           ← parallel to above
Valhalla drive time (parallel)             ← parallel, no deps
API tests (parallel)                       ← parallel, fills a gap
GPS WKT population (spike)                 ← enables track overlap matching
```
