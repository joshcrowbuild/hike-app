# Epic 030 — Guard the unguarded short-slug canonical_id collision + re-runnable audit

**Status:** DONE ✅
**Phase:** A (Stop the lies in the substrate)
**Spec refs:** `docs/strategy/path-to-complete.md` §Phase A (BLOCKING substrate audit, lines ~131–140) · CLAUDE.md non-negotiable rules #1 (source-or-silence) & #5 (private overlay) · CDP-14 (additive/reversible/degree-guarded/flag-on-ambiguous merges)

---

## Capability statement
Two distinct same-source trails whose names collide under slugification (identical short slug, or a long shared prefix) can no longer silently fuse into one `CanonicalTrail`. Zero-silent-same-source-fusion is proven by the *union of two mechanisms*: (a) a re-runnable read-only audit that proves zero silent **distinct-NAME** same-source fusions in the loaded corpus, plus (b) an at-load `log.warning` (S5) that catches the genuinely-indistinguishable **same-NAME** case — which is invisible to any post-hoc graph audit because two same-source same-name `ref`-less features MERGE to a single `SourceRecord` node via `_sr_uid` and leave no distinct trace to recompute. Neither mechanism alone is sufficient; together they close the loop.

## Files touched (the real set — 6)
- `ingestion/pipeline.py` — `_build_canonical_id` fix (S1/S2) **and** the S5 in-memory flag inside `_load_matches`. **Merge-sensitive seam** (AGENTS.md: ingestion pipeline entrypoint) — call out in the PR.
- `scripts/audit_canonical_id.py` — new read-only audit (S4).
- `tests/test_build_canonical_id.py` — new, pure-function tests (S1–S3) + audit-clustering-helper test (S4).
- `tests/test_pipeline.py` — S5 load-path tests (uses the existing `_StubSource`/captured-Cypher harness + `caplog`); AC-3.3 regression already lives here.
- `docs/epics/epic-030-slug-collision.md` — copied epic file.
- `docs/epics/README.md` — one index row (append-conflict magnet across concurrent new-epic lanes — prefer regenerating via `scripts/gen_epic_index.py` over hand-editing; see Process in the prompt).

**Launch sequencing:** `ingestion/pipeline.py` is the substrate corroboration (CDP-01) reads from. If any parallel Phase-A lane also edits `ingestion/pipeline.py` or `tests/test_pipeline.py`, Epic 030 lands **first** (per path-to-complete ordering — it is the substrate fix). Confirm no wave-1 collision before launch.

## Architectural context

**Builds on:** `ingestion/pipeline.py::_build_canonical_id` (line ~80) — the stateless function that derives a `CanonicalTrail.canonical_id` from `(source, ref, name)`. Slow/structural graph data (rule #3). The conflation load loop (`_load_matches` region-load at pipeline.py:534/599) that MERGEs `CanonicalTrail` by this id and attaches `SourceRecord`s via `SAME_AS` (`graph/load.py::load_source_record` line ~520, `merge_same_as` line ~566).

**Enables:** The Phase-A exit criterion — "the slug-collision audit (both collision modes) passes with zero silent same-source merges." Unblocks trustworthy corroboration counting (CDP-01): a fused node would double-count or mis-count distinct `SourceRecord.source` per `SAME_AS` cluster.

**Does NOT include:**
- **The `canonical_id` back-fill / corpus re-key is OUT (explicit).** Correcting `_build_canonical_id` changes the `canonical_id` of every already-loaded trail, which can orphan any `Episode`/`Belief`/grant edge keyed on the old id. At current state (mock episodes, no real auth) back-fill risk is minimal, so this epic **scopes the back-fill OUT and flags it in the PR body** as the named follow-up. The fix takes effect on the next ingest; already-loaded Aura nodes keep their old ids until a re-ingest.
- **The 1643→1458 conflation-delta row-by-row audit is OUT (explicit).** That ~185-node collapse can only be audited against the live Aura corpus, which is **not reproducible from `main`**. It depends on the re-runnable Aura ingest verification (a separate Phase-A item). Name it in the PR as the follow-up; this epic ships only the *re-runnable audit script itself*, which runs against whatever corpus is loaded in the target Neo4j.
- **Geometry stitching / conflation geometry.** BINDING (E1 verifier correction 3): geometry stitching does NOT touch this — it is a pure string-hashing problem, orthogonal to the spatial `consolidate_osm_segments` / `_connected_components` merge. Do not modify `consolidate_osm_segments`, `_connected_components`, or `assemble_geometry`.
- **CDP-01 corroboration wiring** (`engine.py:172`), **CDP-06 MIN-fusion**, the owned-Cypher CI lint (M9) — separate Phase-A items.

---

## Stories

### S1 — Distinct same-source names with an identical short slug no longer fuse

Two distinct raw names can slugify to the same ≤40-char string (slash→dash, space→dash, case-fold collapse them): e.g. `"Blue/Ridge Trail"` and `"Blue Ridge Trail"` both → `blue-ridge-trail`; `"Foo  Bar"` (double space) and `"Foo Bar"` → `foo-bar`. Today the sha1 suffix fires **only** when `len(slug) > 40` (`ingestion/pipeline.py:85`), so these ≤40-char collisions are fused with **no guard at all** — both records MERGE onto one `canonical_id`.

**Given** two distinct source names from the same source, both without a `ref`, that slugify to the same ≤40-char string
**When** `_build_canonical_id` is called on each
**Then** the two returned `canonical_id`s differ.

**AC-1.1:** The name-slug branch (the `ref`-absent path) applies a hash suffix **unconditionally** (not gated on `len(slug) > 40`).
**AC-1.2:** The suffix is derived from the **full original `name`** (the pre-slugification string, e.g. `hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]`), NOT from the lossy `slug` — so two names that slugify identically but differ in the original string get distinct suffixes. (Hashing the slug would give both the same suffix and would not fix the bug.)
**AC-1.3:** A test asserts `_build_canonical_id("osm", None, "Blue/Ridge Trail") != _build_canonical_id("osm", None, "Blue Ridge Trail")`, and likewise for a double-space vs single-space pair.

### S2 — Long shared-prefix names no longer truncation-collide

Even past the old guard, the id kept only `slug[:33]` + a 6-char hash **of the slug** — but two distinct names sharing a long common prefix still hash their (near-identical) slugs to values that can collide, and the truncated prefix is identical. The corrected suffix (full-name hash, S1) already distinguishes them; this story pins the prefix length so the readable portion is long enough to remain human-distinguishable and the fix is verified against the shared-prefix mode.

**Given** two distinct same-source names sharing a common prefix longer than the retained prefix window (e.g. a 60-char shared prefix differing only in the last word)
**When** `_build_canonical_id` is called on each
**Then** the two returned `canonical_id`s differ.

**AC-2.1:** The retained slug prefix is lengthened from `slug[:33]` to at least `slug[:50]` (choose one value ≥50; document it in a comment).
**AC-2.2:** A test asserts two names with a ≥55-char shared prefix that differ only after the prefix produce distinct `canonical_id`s.
**AC-2.3:** The total `canonical_id` length stays bounded (prefix ≤64 chars + separator + 8-char hex + the `ct:<source>:` prefix) — a test asserts the id is ≤128 chars for a pathologically long name.

### S3 — Identical names still conflate; the `ref` path is unchanged

The fix must not break legitimate conflation: two records with the **same** name (or same `ref`) must still resolve to the **same** `canonical_id` (that is how OSM+NPS records for one trail land on one node). The `ref`-present branch is the primary identity path and must be byte-for-byte unchanged.

**Given** two calls with identical `(source, ref, name)`, or identical `(source, name)` with `ref=None`
**When** `_build_canonical_id` is called on each
**Then** the returned `canonical_id`s are identical (deterministic, idempotent).

**AC-3.1:** A test asserts `_build_canonical_id("nps", None, "Old Rag Loop") == _build_canonical_id("nps", None, "Old Rag Loop")` (idempotent across calls).
**AC-3.2:** The `ref`-present branch (`ingestion/pipeline.py:81–83`) is unchanged; a test asserts `_build_canonical_id("osm", "relation/123", "Anything") == "ct:osm:relation_123"` (existing behaviour preserved).
**AC-3.3:** The existing pipeline test asserting `canonical_params[0]["cid"].startswith("ct:nps:")` (`tests/test_pipeline.py:365`) still passes.

### S4 — A re-runnable, read-only audit over the loaded corpus

An operator must be able to prove "zero silent **distinct-NAME** same-source merges" against whatever corpus is loaded, and re-run it after any ingest. The audit recomputes the id function over every loaded `SourceRecord` and reports collision clusters. **Scope limit (state it in the script's own printed summary):** the audit can only catch *distinct-name* slug collisions — two same-source **same-name** `ref`-less features MERGE to one `SourceRecord` via `_sr_uid` and leave no distinct row to recompute, so they are invisible here and are caught instead at load time by S5's warning. The audit's summary line must say this so the operator does not read "0 collisions" as "0 same-source fusions."

**Given** a Neo4j with `CanonicalTrail` + `SourceRecord`/`SAME_AS` data loaded
**When** the operator runs `python scripts/audit_canonical_id.py`
**Then** it prints every same-source collision cluster (a `canonical_id` fed by ≥2 `SourceRecord`s of the **same** `source` with distinct `(source_id, raw_name)` identity) and a summary count, and exits non-zero under `--strict` if any cluster is found.

**AC-4.1:** `scripts/audit_canonical_id.py` exists, is **read-only** (opens a Neo4j session and only `MATCH`/`RETURN`s — no `CREATE`/`MERGE`/`SET`/`DELETE`), and connects via `graph.client.GraphClient` + `orchestration.config.Settings.from_env()` (mirror `scripts/region_counts.py`). It closes the client in a `finally`.
**AC-4.2:** The audit reads each `SourceRecord`'s `source`, `source_id`, `raw_name` and recomputes the id via the **same** `_build_canonical_id` imported from `ingestion.pipeline` (single source of truth — no re-implementation of the hashing).
**AC-4.3:** A collision cluster is defined as: two or more `SourceRecord`s sharing one recomputed `canonical_id` where they have the **same `source`** but distinct `(source_id, raw_name)` identity. (Cross-source sharing is legitimate conflation and MUST NOT be flagged.) The audit prints, per cluster: the `canonical_id`, the source, and each colliding `(source_id, raw_name)`.
**AC-4.4:** The audit also reports, for the currently-loaded corpus, how many of those clusters are **resolved by the corrected function** (the imported `_build_canonical_id`, AC-4.2) vs. the **pre-fix** function, so the operator sees the fix's effect without re-ingesting. The pre-fix comparator is a deliberate, clearly-named throwaway local helper (e.g. `_prefix_id_legacy`) defined in the audit script and used **only** for this delta report — it is the one sanctioned re-implementation of the old hashing (this does NOT conflict with AC-4.2: the *corrected* id, used for the actual collision detection, remains the single imported SSOT; the legacy helper is a read-only historical comparator, not an identity source). It states plainly that already-loaded nodes keep their old ids until re-ingest (back-fill is out).
**AC-4.5:** `--strict` makes the process exit non-zero when ≥1 same-source collision cluster is found (so a future CI/cron gate can consume it); default (no flag) prints the report and exits 0.
**AC-4.6:** "Empty corpus" = a **reachable** Neo4j with zero `SourceRecord` nodes: `session.run(...).data()` returns `[]`, the audit prints "0 collisions" and exits 0 (no crash on empty result). A connection/driver failure (DB unreachable, auth error) is a boundary failure and MUST fail loudly — let it propagate (non-zero exit + traceback), never swallow it and print "0 collisions" (rule: fail loudly at boundaries).

### S5 — Flag-on-ambiguous merge at load (CDP-14: additive / reversible / degree-guarded)

When two `ref`-less same-source features share **one name** (structurally ambiguous — nothing distinguishes them but the name they share), the loader must **flag** the fusion rather than silently absorb the second record. This same-NAME case is *exactly* the S5 trigger and is the only same-source fusion that survives the S1/S2 fix: after the fix, two **distinct** names always get distinct `canonical_id`s, so the only way two same-source features still resolve to one `canonical_id` at load is if their names are byte-identical (indistinguishable). Those two features also collapse to a single `SourceRecord` node (identical `_sr_uid`), so the fusion is invisible to the post-hoc audit (S4) and MUST be caught here, at load. The flag is non-destructive: additive (log/warn only), reversible (no data overwritten), degree-guarded.

**Trigger definition (keyed on `(canonical_id, source)` re-attachment within the run — NOT on distinct `(source_id, raw_name)`):** track, in memory for the duration of one `_load_matches` call, every `(canonical_id, source)` tuple already loaded this run. Warn when a subsequent feature resolves to a `(canonical_id, source)` tuple **already seen this run**. Because two distinct names now produce distinct `canonical_id`s, a repeat `(canonical_id, source)` means the two features share a name — the indistinguishable case. The cross-source (`osm`+`nps`) conflation case is **naturally excluded**: those two records share the `canonical_id` (from the spine feature) but carry **different** `source`s, so they key to two distinct `(canonical_id, source)` tuples and never repeat (AC-5.2).

**Given** a region load where a second same-source feature resolves to a `(canonical_id, source)` tuple already loaded this run (i.e. two `ref`-less same-source features that share one name)
**When** the load loop processes the second one
**Then** it emits a WARNING naming the `canonical_id`, the source, and the shared name — and continues without overwriting or deleting the existing node/record.

**AC-5.1:** The load path logs a `log.warning(...)` (fail-loud-at-boundary, rule) when it detects a repeat `(canonical_id, source)` within the run — it does NOT raise, does NOT delete, does NOT overwrite the surviving record's `raw_name`. (Additive + reversible.) The detection keys on `(canonical_id, source)` re-attachment, NOT on `(source_id, raw_name)`-distinctness (the same-name case has identical `(source_id, raw_name)`, so a distinctness guard would wrongly stay silent).
**AC-5.2:** The detection is degree-guarded — it triggers only on the repeat-same-source case, never on legitimate cross-source `SAME_AS` corroboration. OSM+NPS on one trail key to distinct `(canonical_id, "osm")` / `(canonical_id, "nps")` tuples → no repeat → no warning.
**AC-5.3:** A test drives a region load with two same-source, **same-name**, `ref`-less features and asserts the warning fires (this is the genuinely-indistinguishable trigger; open-question #4 confirms flag-not-split); a second test with one OSM + one NPS record on the same trail asserts NO warning fires.
**AC-5.4:** No schema change and no new node/edge property is required — the flag lives in logs only (keeps the change reversible and out of the merge-sensitive graph seam).

---

## Definition of Done
- [ ] All ACs (S1–S5) covered by at least one passing test in `tests/test_build_canonical_id.py` (S1–S3) and `tests/test_pipeline.py` (S5 load-path; S4 audit smoke if practical DB-free)
- [ ] `_build_canonical_id` corrected; `consolidate_osm_segments` / geometry untouched (E1 correction 3)
- [ ] `scripts/audit_canonical_id.py` re-runnable, read-only, `--strict` gate
- [ ] `make check` green (`ruff format --check` + ruff + mypy + pytest -m "not neo4j")
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed
- [ ] PR body explicitly names the back-fill/re-key follow-up (OUT) and the 1643→1458 delta audit follow-up (OUT), and flags the load loop as a merge-sensitive seam per AGENTS.md
- [ ] Epic file copied into `docs/epics/` **with its own `**Status:**` header set to the same token as the README row** (IN_PROGRESS during build → both flipped to REVIEW at PR-open); `scripts/gen_epic_index.py` treats the epic-file header as source of truth and rewrites the README cell, so the two must agree or CI's docs-lint reds the PR
- [ ] `python scripts/gen_epic_index.py` run to sync the README row, then `python scripts/doc_lint.py` (or `make docs-lint`) passes locally — **note `make check` does NOT run docs-lint but CI does** (`.github/workflows/ci.yml` docs-lint job)
- [ ] Committed and pushed to `claude/slug-collision`; PR opened into `main`
