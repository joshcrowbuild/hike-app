# Epic 025 — Wire geometry/null-island validity into the load path + externalize trail-filter denylists to config

**Status:** REVIEW
**Phase:** 1 (corpus quality — foundation, Phase-A adjacent)
**Wave:** 2 · **depends_on:** Epics **023** and **030** (both wave 1) — this epic **rebases after both merge** and its PR must say *merge AFTER Epics 023 and 030*. See *Merge sequencing* below.
**Spec refs:** comaps-borrow-plan item A3 · CLAUDE.md rules #1 (source-or-silence), boundary discipline (fail loudly at boundaries, degrade at surface) · path-to-complete.md Phase A (CDP-03 provenance bundle)

> **Provenance of this epic.** Item A3 of the CoMaps borrow plan proposed three things: (1) wire the dead geometry/null-island validity checks, (2) externalize the hardcoded trail-filter denylists to config, and (3) add a provenance-completeness gate + a `replaced_tags` tag-canonicalization table. The plan's binding verifier corrections **split (3) out** and **skip the tag table** — see *Does NOT include*. This epic is only (1) + (2). No CoMaps C++ port is required: the validity primitives already exist in `ingestion/hygiene.py`; the work is *activating* them and *externalizing* our own regexes.

---

## Capability statement
A malformed corpus record — a degenerate/empty geometry or a null-island `(0,0)` centroid — is dropped per-record at load with a logged reason (never aborting the region), and the incident-tuned trail-filter denylists live in `regions/exclusions.json` as the single source of truth rather than hardcoded in `ingestion/trail_filter.py`.

## Architectural context
**Builds on:**
- `ingestion/hygiene.py` — `valid_lonlat` (line 19) and `geometry_valid` (line 30) already exist, are unit-tested (`tests/test_hygiene.py`), and are **dead** — imported nowhere in the load path (verified: `grep -rn valid_lonlat|geometry_valid` returns only `hygiene.py` + its test). This epic wires them in.
- `ingestion/pipeline.py::_load_matches` (lines ~502–636) — the load loop that turns Features into `CanonicalTrail` nodes. Its `counts` dict already carries a `skipped_hygiene` key (line ~530) that today only counts nameless features (line ~597); this epic adds the validity drops to that same counter.
- `ingestion/trail_filter.py::is_trail_worthy` (line 95) — runs **LIVE at fetch time** (`ingestion/fetch/osm.py:75`), not in the load path. The four denylists it uses are module-level compiled regexes (lines 48, 51, 63–65, 84–92).

**Enables:** a config-owned, per-corpus-editable exclusion set that a future region can extend without a code change; a per-record hygiene floor at load that makes null-island / degenerate geometry impossible to persist.

**Merge sequencing (WAVE 2 — binding):** three Phase-A lanes edit the same merge-sensitive seam `ingestion/pipeline.py` (an AGENTS.md ingestion entrypoint), so they **cannot merge blind in one wave**. This epic **depends on Epics 023 and 030** and is **wave 2**:
- **Epic 023** (agency-length, wave 1) edits the two `load_canonical_trail` call sites this epic guards — `pipeline.py:538` (auto-accept) and `pipeline.py:603` (unmatched-spine). S1 inserts its hygiene `continue` **immediately before** those exact two calls (Epic 023's own spec already names this collision).
- **Epic 030** (slug-collision, wave 1) edits `_build_canonical_id` (`pipeline.py:80–91`) and an in-memory flag inside `_load_matches` in the same file.
- **Sequencing:** let Epics 023 and 030 merge first, then **rebase this branch on `main`** and re-confirm the two `load_canonical_trail` line numbers before inserting the guard (they will have drifted). Do **not** merge blind against 023/030 — the PR body must state **"merge AFTER Epics 023 and 030"** and name the reconcile surface (`ingestion/pipeline.py` + `tests/test_pipeline.py`).

**Does NOT include (scope fence — binding):**
- **The provenance-completeness gate is SPLIT OUT and NOT wired here.** `hygiene.py::has_provenance` (line 34) checks `("source", "source_pk", "fetched_at", "ingest_version")`. The frozen `Feature` dataclass (`ingestion/conflate/match.py:80–96`) carries **none** of `source_pk` / `fetched_at` — they exist nowhere on any record that reaches load. Wiring `has_provenance` as a hard gate would therefore reject **100% of records**. It is a **CDP-03 dependent** (path-to-complete.md Phase A: "CDP-03 capture-at-boundary provenance bundle `{source, timestamp, digest, role}` stamped by the fetch wrapper") and belongs to that later work, once the fetch wrapper stamps those fields. Do not touch `has_provenance` / `hygiene_flags` and do not add any provenance gate to the load path.
- **The CoMaps `replaced_tags` tag-canonicalization table is SKIPPED.** Our Overpass ingest is already pre-filtered (`osm.py` queries only `path|footway|track|bridleway|steps` with a `name`), so a tag-replacement table is the weakest half of A3 and adds no value. Do not build it.
- No change to `is_trail_worthy`'s *logic* or its call site (`osm.py:75`). S2 is a **pure migration** of *where the patterns are stored*, byte-for-byte — not a behavior change and not an "activation" (the filter already runs live).
- No change to the OSM tag-value sets `_PRIVATE_ACCESS` / `_FOOT_OK` / `_NON_TRAIL_FOOTWAY` (lines 33, 34, 37) — those are OSM tag semantics, not incident-tuned corpus denylists, and are out of the migration scope.

---

## Stories

### S1 — Per-record geometry/null-island validity drop in the load path

**Given** the load loop `_load_matches` (`ingestion/pipeline.py` ~502–636) builds a `CanonicalTrail` from each auto-accept match's spine feature (`m.a`) and each unmatched named spine `feat`, computing a centroid `(lat, lon)` via `_safe_geom_centroid`,
**When** a feature's geometry is empty/None/invalid, or its centroid is out of range or the null-island point `(0.0, 0.0)`,
**Then** that single record is dropped (not persisted), `counts["skipped_hygiene"]` is incremented by 1, a WARNING is logged naming the feature and the reason, and the run continues — the region is **never** aborted and every other record still loads.

**AC-1.1:** In `_load_matches`, before the `load_canonical_trail` call in **both** the auto-accept loop (over `m.a`) and the unmatched-spine loop (over `feat`), the node-bearing feature is validated in this **order**: (1) `geometry_valid(feature.geom)` **first**, and only if it passes (2) compute the centroid via `_safe_geom_centroid` and check `valid_lonlat(lon, lat)`. A feature failing **either** check is skipped (the loop `continue`s before any `load_*` write) and `counts["skipped_hygiene"] += 1`. **Order is load-bearing:** `_safe_geom_centroid` accesses `centroid.y`/`.x`, which **raises `GEOSException` on an empty geometry** (`POINT EMPTY`) — so the geometry check must gate the centroid computation, never the reverse (computing the centroid first would crash on exactly the empty-geometry record this AC must drop, aborting the region). The centroid computed here should be reused for the subsequent `load_canonical_trail` call — do not compute it twice.
**AC-1.2:** Each drop emits exactly one `log.warning` that includes the feature's `name` (or `ref`) and distinguishes the reason (invalid geometry vs. invalid/null-island coordinate). No drop raises — there is no code path where an invalid record aborts `_load_matches` or `run_pipeline`.
**AC-1.3:** `valid_lonlat(0.0, 0.0)` is `False` (null island), `valid_lonlat(200.0, 0.0)` is `False` (out of range), `valid_lonlat(-78.4, 38.5)` is `True`; `geometry_valid` is `False` for `None`, an empty `LineString()`, and an invalid geometry, `True` for a well-formed `LineString`. **Pinned today** in `tests/test_hygiene.py`: the three `valid_lonlat` cases and `geometry_valid(empty LineString) == False` / `geometry_valid(valid LineString) == True` — S1 must not regress these. The `geometry_valid(None)` and `geometry_valid(invalid-geometry)` cases are **not** asserted today; add them as new assertions (either in `test_hygiene.py` or alongside the S1 load-path tests) so every branch relied on at line-time is pinned.
**AC-1.4:** Given a batch of all-valid features, `counts["skipped_hygiene"]` stays `0` and `counts["loaded"]` equals today's value — the existing `test_pipeline.py::test_ac5_2_default_config_counts_through_real_adapters` assertion `counts["skipped_hygiene"] == 0` still passes unchanged.
**AC-1.5:** Given a batch containing exactly one invalid-geometry feature (an **empty `LineString()`** — the realistic on-the-wire degenerate, and the case that would crash the centroid step if the order were wrong) **or** one null-island feature (a geometry whose centroid is `(0.0, 0.0)`) among N valid ones, all N valid features load, `counts["skipped_hygiene"] == 1`, and **no exception is raised** — proving the drop is per-record, not a region-wide early return. Verified via a direct `_load_matches(runner, ...)` call with a fake runner (the established pattern in `test_pipeline.py`). (A `None` geometry is not constructed through this path — `Feature.geom` is a required non-optional field always built from source coords — so the `None` branch is covered at the unit level in AC-1.3, not fed through `_load_matches`.)

### S2 — Externalize the four trail-filter denylists to `regions/exclusions.json`

**Given** `ingestion/trail_filter.py` hardcodes four incident-tuned denylist regexes — `_PUBLIC_ROUTE_REF` (line 48), `_TIGER_ROUTE_BASE` (line 51), `_RESIDENTIAL_STREET_SUFFIX` (lines 63–65), `_NAME_DENY` (lines 84–92), all compiled with `re.I`,
**When** those patterns are moved verbatim into `regions/exclusions.json` and loaded at import/first-use,
**Then** `is_trail_worthy` behaves **byte-for-byte identically** — every incident-tuned drop and keep is preserved — and `regions/exclusions.json` is the single source of truth for the patterns.

**AC-2.1:** `regions/exclusions.json` exists and carries the four patterns as their **exact current compiled `.pattern` strings** (JSON-escaped; `json.load` must return the identical Python string that compiles to the same regex):
- `public_route_ref` = `\b(SR|CR|VA|US|State Route|County Route)[\s-]*(Route\s*)?\d`
- `tiger_route_base` = `\b(State|County) Route\b`
- `residential_street_suffix` = `\b(street|avenue|boulevard|court|drive|lane|way)\s*$`
- `name_deny` = `\b(side ?walk|drive ?way|cross ?walk|wheelchair|colonnade|parking (lot|area)|bus (stop|loop))\b|\bwellness (and recreation|cent(er|re)|campus|clinic|hospital|institute)\b|\bpath to (a |an |the )?(school|store|parking|lot|bus|garage|garden|building|club|gym|colonnade)\b|\b(ramp|stairs?) to\b`
**AC-2.2:** `trail_filter.py` loads these four patterns from `regions/exclusions.json` and compiles each with `re.I` (identical flags to today); the four regex **source strings** no longer appear as literals in `trail_filter.py`. Loading is done once (module import or an `lru_cache`d loader), not per `is_trail_worthy` call (it runs per-way at fetch).
**AC-2.3 (BYTE-FOR-BYTE PINNING — binding):** the **entire existing `tests/test_trail_filter.py` suite passes unchanged**. This is the incident-behavior pin. It must still assert, at minimum: Snake Road `ref=SR 650` and Little Loop Road `ref=SR 652` **dropped**; every `_PUBLIC_ROUTE_REF` variant (`CR 600`, `VA 55`, `US 211`, `State Route 12`, `County Route 7`, `US-211`, `VA-55`, `SR-652`, `US Route 211`, `VA Route 55`) **dropped**; `State Route 1108` (route number in the name) **dropped**; `tiger:name_base_1="State Route"` **dropped**; "The Andreae Family Wellness and Recreation Trail" (institutional wellness footway) **dropped**; OBX residential suffixes (`Barracuda Street`, `Amadas Avenue`, `Malbon Drive`, `Seagull Lane`, `Tasman Drive`, `Brother's Way`) **dropped** — **while keeping** `Compton Gap Road` / `Mathews Arm Road` (fire roads, `tiger:cfcc=A41`, no numbered ref), `Salt Pond Road`, `LORAN Road`, `Wellness Trail` / `Riverside Wellness Loop`, `Riverside Greenway` (compound "way"), and `Hull School Trail`.
**AC-2.4:** A new test proves the patterns are **sourced from the JSON, not re-hardcoded**: it loads `regions/exclusions.json` directly and asserts each module-compiled pattern's `.pattern` equals the file's corresponding string (and the module's flags include `re.I`). This guarantees config is the single source of truth and would fail if a stray hardcoded copy drifted.
**AC-2.5:** A missing or malformed `regions/exclusions.json` (missing key, non-string value, unparseable JSON, or a value that is not a valid regex) **fails loudly** — the loader raises at import/first-use with a clear message. It must **never** degrade to an empty/absent denylist, which would silently re-pollute the corpus with the exact TIGER-route / residential-street / institutional-footway junk these regexes were tuned to remove. (This is a build/ingest-time boundary → fail loudly, per CLAUDE.md.)

---

## Definition of Done
- [x] All ACs covered by at least one passing test (extend `tests/test_pipeline.py` for S1's load-path drops; keep `tests/test_trail_filter.py` green and add the config-source + malformed-config tests for S2; `tests/test_hygiene.py` continues to pass).
- [x] `make check` green (`ruff format --check` + `ruff check` + `mypy` + `pytest -m "not neo4j"`).
- [x] Targeted self-review agent run over the diff; every CRITICAL fixed. (Found + fixed: `_canonical_nodes` — the enrichment-node derivation that runs BEFORE `_load_matches` — called the unguarded centroid directly, so the exact crash this epic exists to prevent still fired one call site earlier; and a `matched_spine_ids` ordering bug double-dropped/double-counted a hygiene-failed auto-accept spine feature. See the two follow-up commits on this branch.)
- [x] Epic file copied into `docs/epics/` and a row added to `docs/epics/README.md` (status `IN_PROGRESS` → `REVIEW` when the PR opens).
- [x] Committed and pushed on `claude/validity-exclusions`; PR opened into `main` titled `Epic 025: … — FOR REVIEW`, naming any merge-sensitive seam touched (`ingestion/pipeline.py` is one).
- [x] PR body states **"merge AFTER Epics 023 and 030"** (wave-2 dependency) and, in Merge-risk, names the reconcile surface — `ingestion/pipeline.py` (`load_canonical_trail` sites, shared with Epic 023; `_build_canonical_id` shared with Epic 030) + `tests/test_pipeline.py`. Both 023 and 030 were already merged into `main` before this branch was built, and this branch is rebased on top of current `main`.
