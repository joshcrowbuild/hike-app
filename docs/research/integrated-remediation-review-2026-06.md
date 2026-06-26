# Integrated Remediation Review — Trunk (commit 549e6f3)

**Scope:** the *integrated* whole of three parallel tracks (six gap-audit CRITICAL-remediation epics) merged into one trunk. The per-track builds were reviewed in isolation and were correct there; this pass asks whether the cross-cutting invariants still hold and whether the load-bearing orderings compose after the merges. All findings below were re-verified against the merged code at `…/scratchpad/trunk-review` (file:line cited).

---

## Executive verdict

**Conditionally sound — one structural CRITICAL must be fixed before this is a clean trunk; four MODERATEs should follow.**

The merge did not produce an *active* breach: every owned write on the live Outcome path is functionally owner-scoped today (literal `$owner_id` bound to `viewer_id`), so there is no present cross-owner data leak, no overlay egress, and no fabricated fact. The engine's adapter/probe seam, the commons fork's transactional write path, and the scoped-read choke point all compose correctly.

What the merge *did* break is **structural** — the load-bearing invariant that each track established in isolation no longer holds end-to-end:

1. The Epic-011 write seam (every owned-node write routes through `run_write`/`assert_scoped_write`) is **bypassed by a whole live endpoint** — `POST /episode/{id}/outcome` writes two owned labels (`Outcome`, `Belief`) through `scoped.run` (the *read* path), never invoking the write guard. This is the CRITICAL: defense-in-depth that exists specifically to make a future owner-clause regression impossible is silently absent on a production handler, and `make check` stays green because the seam's own coverage test carves `Outcome`/`PartyProfile` out as `deferred_writers`.
2. The Epic-013 verifier reshape and the Epic-012 source-seam generalization each left **one orphaned literal/caller** behind in code the track didn't touch (the sprint smoke runner; the OSM-hardcoded consolidation), so the seams are not actually composed end-to-end.
3. The new `health()` probe path routes the FIRMS `MAP_KEY` (carried in the URL *path*) into a DEBUG log line — a fresh regression against rule #10.

None of these is a per-track nit already fixed; each is a genuine *merge-integration* defect. The CRITICAL is must-fix; the four MODERATEs are should-fix-before-next-epic.

---

## Findings (severity-ranked)

| # | Severity | Title | Location | Invariant |
|---|----------|-------|----------|-----------|
| 1 | **CRITICAL** | Outcome endpoint writes owned `Outcome`+`Belief` outside the scoped-write seam | `orchestration/outcome.py:88-125,158-211`; `api/app.py:219` | Scoped writes (rule #4) |
| 2 | MODERATE | Stated-preference `Belief` MERGE keyed on forgeable id only (owner_id omitted from merge key) | `orchestration/outcome.py:166-167` | Private-by-default overlay / scoped writes |
| 3 | MODERATE | `scripts/sprint.sh` imports removed `build_probes` and calls `verify()` with old float signature | `scripts/sprint.sh:63-71` | Config-driven adapter seam (C6) |
| 4 | MODERATE | `consolidate_osm_segments` hardcodes `source="OSM"` → wrong provenance + dropped authority floor for non-OSM spine | `ingestion/pipeline.py:133` (called at `:320`) | Config-driven corpus seam (C5) / provenance |
| 5 | MODERATE | FIRMS `MAP_KEY` (in URL path) leaks into DEBUG logs via new `health()` probe | `orchestration/adapters/firms.py:87-90`; `orchestration/adapters/_http.py:60` | Secrets never in repo/logs (rule #10) |

**CRITICAL: 1  ·  MODERATE: 4  ·  (combined CRITICAL+MODERATE: 5)**

---

## Fixes

### 1 — CRITICAL · Route the Outcome endpoint's owned writes through the write seam
**Verified:** `api/app.py:219` passes `scoped.run`, which is `ScopedSession.run` (`graph/client.py:51-54`) — it merges `$viewer_id`/`$granted_ids` but **never** calls `assert_scoped_write`; only `run_write` (`client.py:56-65`) and `execute_write` (`client.py:67-82`) invoke the guard. `outcome.py:90` MERGEs `:Outcome` and `outcome.py:166` MERGEs `:Belief` — both in `OWNED_LABELS` — as inline Cypher, not via the `graph.queries` builders the seam designates as the sole author of owned-node Cypher. `tests/test_graph_queries.py:297` carves `{"Outcome","PartyProfile"}` out as `deferred_writers`, so the coverage assertion (`:298`) passes without demanding the seam.

**Fix (do both):**
- Change the live handler to pass the **write** choke point, not the read one. The `write_outcome` runner must dispatch owned-label statements through `scoped.run_write` (or `scoped.execute_write` for the multi-statement Outcome+HAS_OUTCOME+Belief+DERIVED_FROM+ABOUT set, so they commit atomically). Note: the inline Cypher currently binds `$owner`/`$owner_id`, which `assert_scoped_write` would **reject** (it requires a `$viewer_id`-shaped owner clause, AC-1.6) — so this fix forces (2) below as well.
- Move the `Outcome` and stated-`Belief` Cypher into `graph/queries.py` builders (reuse/extend `upsert_pace_belief`/the `wire_belief_*` builders that already exist for exactly these nodes), then delete the `deferred_writers` carve-out at `tests/test_graph_queries.py:297` so the coverage test enforces full seam routing.

Until the carve-out is removed, **`make check` cannot catch a future owner-clause regression on this path** — that is the whole reason this is CRITICAL despite no active leak today.

### 2 — MODERATE · Pin `owner_id` in the stated-Belief merge key
**Verified:** `outcome.py:168` does `MERGE (b:Belief {belief_id: $bid})` with `owner_id` only in `ON CREATE SET` (`:170`); the sibling Outcome MERGE (`:90`) *does* pin owner. The seam's sanctioned writer pins it (`graph/queries.py:282`: `MERGE (b:Belief {belief_id: $bid, owner_id: $viewer_id})`) and `tests/test_graph_queries.py:174-194` asserts exactly that, with the rationale "ownership is enforced by the seam, not by the id-naming convention." Schema has only a global `belief_id IS UNIQUE` (`schema.cypher:166`), no composite `(belief_id, owner_id)` — so the DB does not backstop the missing pin.

**Fix:** `MERGE (b:Belief {belief_id: $bid, owner_id: $owner})`. (Subsumed by the builder migration in (1); the `belief_id` string already embeds `owner_id`, so today's exposure is delimiter-injection-only, hence MODERATE — but it is the one Belief writer in the trunk relying on the id-naming convention the seam forbids.)

### 3 — MODERATE · Migrate the sprint smoke runner to the new verifier seam
**Verified:** `build_probes` is defined in **zero** source files (grep: survives only in `sprint.sh`, docstrings at `verifier.py:10` / `registry.py:79`, and a comment in `tests/test_overlay_egress.py:123`). `sprint.sh:63` `from orchestration.verifier import build_probes, verify` → immediate `ImportError`; `:66` `build_probes(s)` and `:70` `verify(38.5519, -78.2861, probes)` use the dead 3-float contract, while `verifier.py` now is `verify(point: Point, probes_by_kind, *, cache=…)`.

**Fix:** rewrite Phase 4 to build probes via `orchestration.adapters.registry.probes_for(region, settings)` and call `verify(Point(lat=38.5519, lon=-78.2861), probes_by_kind, cache=…)`. Fails loudly (ImportError) and is confined to the smoke script — engine/API/pytest unaffected — hence MODERATE.

### 4 — MODERATE · Drop the hardcoded `"OSM"` from consolidated spine features
**Verified:** `run_pipeline` resolves the spine by declared role (`registry.spine`, `pipeline.py:312`, consumed at `:320`) but still calls `consolidate_osm_segments(raw_spine)` unconditionally, and that function hardcodes `Feature(name=name, geom=combined, source="OSM", ref=None)` on every multi-segment merge (`:133`). Single-feature groups preserve their real source (`:127`); merges do not. Downstream `_tier_extra` keys the authority floor on the real source name via `tier_by_name` (`:370`/`:205`), so for a non-OSM spine `_tier_extra("OSM")` returns `None` → authority floor silently dropped (SS-4/AC-4.3) and SourceRecord/SAME_AS provenance is wrong. Contradicts `docs/epics/epic-012-corpus-source-seam.md:94` ("source-agnostic… an NPS-spine region would consolidate the spine identically").

**Fix:** preserve the group's real source on merge — `Feature(name=name, geom=combined, source=group[0].source, ref=None)` at `pipeline.py:133`. (No impact under the default OSM-spine pilot config, hence MODERATE; but it defeats the C5 invariant Epic 012 exists to establish.)

### 5 — MODERATE · Redact the FIRMS key from logged URLs
**Verified:** FIRMS uniquely carries its secret in the URL *path* (`firms.py:33`). The new `FirmsAdapter.health()` (`:85-90`) builds the full key-bearing URL and passes it to `_http.probe_status`, which logs the complete URL on any `httpx.HTTPError` (`_http.py:59-60`). The same leak exists on `probe()/fetch()` via `get_text` (`firms.py:49` → `_http.py:43-44`). AirNow (`params=`) and RIDB (header) do not route secrets through the logged `url` string. `health()`/`probe_status` did not exist at base `0fdbeee`, so this is a fresh regression. `_http.py:4-5` itself states the intent is to log failures "without leaking to the user."

**Fix:** sanitize in `_http` before logging — strip/redact the path segment carrying the key (log a templated path), covering **both** `probe_status` (health path) and `get_text` (probe/fetch path); or carry the FIRMS key out of the path (header/param) so it never enters the logged URL. Conditional (DEBUG + transport error only) and exposes no user data, hence MODERATE — but a genuine rule-#10 violation.

---

## Invariants — CONFIRMED holding vs. gaps

**Confirmed holding (re-verified in the merged trunk):**
- **Scoped reads / fail-closed read auth.** `ScopedSession.run` merges `$viewer_id`/`$granted_ids` on every statement (`client.py:51-54`); the Outcome handler verifies episode ownership before any write (`outcome.py:72-83`, returns `None`/404 on miss).
- **Commons unlinkability / transactional fork.** `execute_write` guards each owned statement and commits the Episode + wires + de-identified `:CommonsObservation` in one managed transaction (`client.py:67-82`, `:108-116`); the severed observation passes the guard as correctly-unowned. No regression introduced by the merge.
- **No overlay egress.** The overlay-egress test path is intact (`tests/test_overlay_egress.py`); the merge added no new egress of the private overlay. Beliefs/Outcomes written by the new endpoint are owner-scoped and never shared raw.
- **No model training / pure orchestration.** Stated-belief promotion is "no LLM call — raw statement stored as-is" (`outcome.py:162-164`).
- **Provenance + confidence + timestamp on every belief.** The stated Belief carries `confidence`, `created_at`/`last_updated_at`, and DERIVED_FROM/ABOUT provenance edges (`outcome.py:177-211`).

**Gaps (this review's findings):**
- **Scoped *writes* (rule #4 extended).** GAP — finding #1: a live endpoint writes two owned labels around the write seam; the structural guarantee is absent though present-day scoping is functionally correct.
- **Merge-key ownership pinning.** GAP — finding #2: one Belief writer keys on a forgeable id only.
- **Config-driven seams (C5 corpus / C6 adapter).** PARTIAL — findings #3 and #4: the seams hold inside the engine/pipeline core but each left one orphaned literal/caller, so they are not composed end-to-end.
- **Secrets never in logs (rule #10).** GAP — finding #5: FIRMS key reachable in DEBUG logs.

**Forged-identity boundary (out of scope, noted):** `viewer_id` remains unauthenticated by design at the query layer (`client.py:14-17`); a forged `viewer_id` is still a forged write. That is a separate spec decision (gap-audit C3), not a merge regression — but it is the reason finding #1's structural-vs-active distinction matters: once auth lands, the write guard is the second line, and it is currently bypassed.

---

## Known CI gap (flagged)

`.github/workflows/ci.yml` runs the `test` target (`matrix.target: […, test]`, `:32-42`) with **no `services:` block and no Neo4j**. Any DB-backed guardrail (live-graph integration assertions, owner-isolation tests that need a real Neo4j) is **silently skipped in CI** — they pass by being no-ops, not by being satisfied. Combined with finding #1's `deferred_writers` carve-out (`tests/test_graph_queries.py:297`), the seam-bypass on the Outcome path is doubly invisible to `make check`: the coverage test excuses it, and any DB-level test that might catch it does not run. **Recommendation:** add a `neo4j` service container to the `test` matrix leg (or a separate `integration` job) so DB-backed owner-isolation tests actually execute before trunk merges, and remove the `deferred_writers` carve-out once finding #1 is fixed.
