# Self-Review: Rules Compliance + Consistency Audit — 2026-06-23

A rigorous second-pass audit of the Adventure Planner codebase. A prior ultrareview
fixed ~17 bugs. This review targets what that pass may have missed: design consistency
issues, rule violations, and silent failures that only surface at runtime.

## Summary Table

| Severity  | Count | Notes                                   |
|-----------|-------|-----------------------------------------|
| CRITICAL  |   2   | Both fixed in-code (see "FIXED" below)  |
| MODERATE  |   4   | Document-only; acceptable at pilot scale but need tracking |
| LOW       |   3   | Minor; fix before production            |
| INFO      |   3   | No functional impact; context only      |

---

## Audit 1 — Source-or-Silence (Rule #1)

### [CRITICAL] — curator._alerts() crashes when NWS alerts endpoint fails — FIXED

File: `orchestration/curator.py:37`

Finding: The NWS adapter correctly sets `active_alerts=None` in the `VerifiedFact.value`
dict when the `/alerts/active` sub-call fails (alerts endpoint failed but forecast
succeeded). However, `_alerts()` calls `value.get("active_alerts", [])` which returns
the stored `None` — the default only applies when the key is *absent*, not when it is
explicitly set to `None`. The list comprehension `[a for a in None if ...]` then raises
`TypeError: 'NoneType' object is not iterable`.

Impact: Any request where the NWS forecast succeeds but the alerts endpoint fails
(network hiccup, 5xx, DNS timeout) crashes the entire engine pipeline mid-run. The
user receives an unhandled exception instead of a hedged response.  This is not a
rare path — the alerts endpoint is a separate HTTP call that can fail independently.

Fix (applied): Changed `value.get("active_alerts", [])` to `value.get("active_alerts") or []`.
The `or []` handles both `None` (stored sentinel) and the absent-key case identically,
without losing the semantic distinction between "unknown" and "no alerts" at the
VerifiedFact level (the `None` value is preserved; only iteration is guarded).

```python
# Before (crashes when active_alerts is None):
return [a for a in value.get("active_alerts", []) if isinstance(a, str)]

# After (safe; treats None as "unknown → empty for iteration"):
alerts = value.get("active_alerts") or []
return [a for a in alerts if isinstance(a, str)]
```

Note: `present.py:_body("weather", ...)` does not access `active_alerts`, so no
downstream presentation bug exists there. The guardrail block in `evaluate_guardrails()`
is the only caller of `_alerts()` and the only crash site.

---

### [INFO] — USGS discharge: numeric sentinel value -999999 passes through

File: `orchestration/adapters/usgs_water.py:46`

Finding: USGS WaterServices occasionally returns `-999999` as a numeric sentinel
meaning "no data / equipment malfunction." The `float(raw)` conversion succeeds,
returning `-999999.0`, which is then returned in the `VerifiedFact` as a real discharge
value. A user would see "latest_discharge_cfs: -999999.0."

Non-numeric sentinels (e.g., "Eqp", "Ice", "Dry") already fail `float(raw)` and are
caught by the `except ValueError` guard, returning `None`. Only the numeric sentinel
leaks through.

Impact: Low at pilot scale; -999999 is a legacy USGS convention rarely seen in modern
NRT feeds. Does not crash; causes slightly misleading presentation only.

Fix (do not fix now): When implementing Stage-4 full pipeline, add:
`if raw and float(raw) < 0: return None` (or a more specific sentinel check).

---

### [INFO] — Water gauge "None" display when site_id also missing

File: `orchestration/present.py:52`

Finding: `_body("water", value)` renders
`f"nearest gauge: {value.get('monitoring_location') or value.get('site_id')}"`.
When both `monitoring_location` and `site_id` are `None`, this produces
`"nearest gauge: None"` — the string "None", not an omission.

Impact: Cosmetic only. No rule violation; the fact is still sourced and timestamped.
The string "None" is ugly but not misleading (there is a nearest gauge; its name
is unavailable). Fix in Stage 10 (presentation polish).

---

## Audit 2 — Confidence Never Penalizes Ranking (Rule #2)

### [INFO] — Rule #2 correctly honored throughout

Files: `orchestration/curator.py:111-132`, `orchestration/engine.py:106-118`

`rank_ids()` sends only `(canonical_id, name)` pairs and an optional `profile` string
to the judgment-tier LLM. No confidence score, no `facts`, no `GuardrailVerdict` data
is included in the ranking prompt. `rank_plan()` in engine.py confirms by comment:
"confidence is not an input (rule #2)."

The guardrail filter (`plan_from_origin`) runs *before* ranking and is a hard binary
block on safety/legality grounds (not confidence), which is the intended design.

No issues found.

---

## Audit 3 — Access Control at Query Layer (Rule #4)

### [INFO] — Rule #4 correctly honored; seam is watertight

Files: `graph/queries.py`, `graph/client.py`, `orchestration/scout.py`

- `candidate_trails_near` and `candidate_trails_near_direct` touch only world nodes
  (Trailhead, CanonicalTrail, Area) which carry no `owner_id`. No scope clause needed
  or present. ✓
- `episodes_on_trail` correctly applies `owner_scope('e')` on the `Episode` node. The
  Person node is an identity node (no `owner_id`), so matching any Person without a
  scope clause is correct. ✓
- `ScopedSession.run()` unconditionally merges `viewer_id` and `granted_ids` into every
  query's params. Even world-node queries receive the vars (unused but harmless). ✓
- `graph/load.py` writes only world nodes and uses no access-control seam (correct:
  writes are ingest-time, not query-time; owned nodes are Phase-1). ✓

One style note: `pipeline.py:204` calls `gc._ensure_driver().session()` directly,
bypassing `gc.scoped_session()`. This is not a security issue (it's ingest-time, not
query-time), but it couples the pipeline to the private driver API. Track as tech debt
for Phase-1 refactor.

---

## Audit 4 — Ingestion Idempotency

### [MODERATE] — consolidate_osm_segments() silently drops suffix-only feature names

File: `ingestion/pipeline.py:95-98`

Finding: `normalize_name()` strips suffix words (trail, path, road, loop, etc.) from
feature names. A feature whose entire name consists of suffix words (e.g., name="Trail",
name="Loop", name="Footpath") normalizes to `""`. The guard `if key:` in
`consolidate_osm_segments()` then silently discards these features — they never enter
`by_norm` and never appear in `consolidated`. They are not counted in
`skipped_hygiene` either; they vanish with no log entry.

Impact: Silent data loss. Uncommon in practice (OSM trail names like "Trail" or "Loop"
do exist, especially as generic names for unnamed paths), but the silence makes it
invisible. These trails cannot be found or displayed.

Fix: Add a log warning and fall-through to `consolidated` for empty-key features:

```python
if key:
    by_norm[key].append(feat)
else:
    log.debug("Feature dropped from consolidation (suffix-only name): %r", feat.name)
    consolidated.append(feat)  # keep it; treat as unnamed singleton
```

---

### [MODERATE] — Canonical ID and sr_uid truncation creates silent merge/collision risk

File: `ingestion/pipeline.py:65-75`

Finding: Both ID-generation functions truncate name-based slugs:

```python
def _build_canonical_id(source, ref, name):
    slug = name.lower().replace(" ", "-").replace("/", "-")[:40]
    return f"ct:{source.lower()}:{slug}"

def _sr_uid(source, ref, name):
    key = ref or name.replace(" ", "_")[:30].lower()
    return f"{source}:{key}"
```

Two trails with `ref=None` and names sharing the same first 40/30 characters will
produce the same canonical_id / sr_uid. Since all writes use MERGE, the second write
silently overwrites the first node's properties. Example collision:
- "Appalachian Trail Northern Section Route" → `ct:osm:appalachian-trail-northern-sect`
- "Appalachian Trail Northern Section Route Alternate" → same ID (40-char match)

The `_sr_uid` collision is the more serious case: two different source records from
two genuinely different trails would share a SourceRecord node, corrupting provenance.

Impact: Silent data corruption at ingest; no crash, no log. Unlikely at Shenandoah+GWJ
pilot scale but plausible for Appalachian Trail segments.

Fix: Append a short hash of the full name to break collisions:

```python
import hashlib

def _build_canonical_id(source, ref, name):
    if ref:
        ...
    slug = name.lower().replace(" ", "-").replace("/", "-")[:36]
    h = hashlib.md5(name.encode()).hexdigest()[:4]
    return f"ct:{source.lower()}:{slug}-{h}"
```

---

## Audit 5 — Provider Seam Correctness

### [MODERATE] — anthropic_claude.py stores api_key as a public attribute

File: `orchestration/providers/anthropic_claude.py:22`

Finding: `AnthropicProvider.__init__` stores `self.api_key = api_key` (public).
`LocalOpenAIProvider` correctly uses `self._api_key = api_key` (private). The
inconsistency means any code that calls `repr()`, `vars()`, `dir()`, or serializes
the provider instance will expose the Anthropic API key in plaintext. Debug logging
frameworks (structlog, sentry-sdk) commonly do this automatically on exceptions.

This violates Rule #10 in spirit: secrets should not surface outside the secrets store,
but a public attribute named `api_key` is one `str(provider.__dict__)` away from a log.

Impact: Potential secret leak in tracebacks or debug logging. No crash.

Fix:

```python
# anthropic_claude.py line 22
self._api_key = api_key  # not self.api_key

# and in _ensure_client():
self._client = anthropic.Anthropic(api_key=self._api_key)
```

---

### [INFO] — Sensitivity routing: forced_local=False when provider already "local"

File: `orchestration/providers/registry.py:50-68`

Finding: When `tier.provider == "local"` and `touches_private_overlay=True`, the
condition `tier.provider != "local"` is False, so the sensitivity routing block is
skipped. We fall through to the normal path which returns `forced_local=False` even
though local is being used for private-overlay data. This is metadata-only; the actual
provider selection is correct (local provider is still chosen).

Impact: The `Resolution.forced_local` field would be `False` for a private-overlay
call on a local-defaulted tier, making it impossible for callers to distinguish "forced
to local" from "was already local." No functional routing bug.

Fix: Not urgent. Could return `True` when `touches_private_overlay and provider == "local"`
for accurate metadata, but semantically debatable.

---

## Audit 6 — OSM Consolidation Correctness

### [CRITICAL] — sprint.sh: --password-stdin conflicts with schema.cypher stdin redirect — FIXED

File: `scripts/sprint.sh:39-43`

Finding: The schema application step was:

```bash
NEO4J_PASSWORD="${NEO4J_PASSWORD}" docker compose exec -T \
    -e NEO4J_PASSWORD \
    neo4j cypher-shell \
    -u "${NEO4J_USER:-neo4j}" --password-stdin \
    < graph/schema.cypher
```

`cypher-shell --password-stdin` reads its authentication password from stdin. The
`< graph/schema.cypher` redirection means stdin IS the schema file. Therefore:

1. cypher-shell reads the first line of schema.cypher (`// ────────...`) as the password.
2. Authentication fails (wrong password).
3. No Cypher is executed.
4. `set -euo pipefail` stops the sprint with a non-zero exit.

The schema is never applied. The database has no constraints, no indexes, and no
seeded world data. The subsequent ingestion step runs against a bare database.

Note: This bug is in Audit 6 (sprint.sh security review) because the password-passing
approach is the mechanism that failed, but it affects the entire sprint workflow.

Impact: Sprint fails at schema step; indexes/constraints never created; no seed data.

Fix (applied): Remove `--password-stdin` and the stdin redirect. Use `-f /graph/schema.cypher`
(the graph directory is already mounted as `/graph:ro` inside the container). Rely on
`NEO4J_PASSWORD` env var for authentication (cypher-shell reads this automatically):

```bash
docker compose exec -T \
    -e NEO4J_PASSWORD \
    -e NEO4J_USER \
    neo4j cypher-shell \
    -u "${NEO4J_USER:-neo4j}" \
    -f /graph/schema.cypher
```

---

### [INFO] — OSM cross-region name consolidation (accepted risk at pilot scale)

File: `ingestion/pipeline.py:81-111`

Finding: `consolidate_osm_segments()` groups OSM ways solely by normalized name within
the fetch bbox. Two geographically separate trails sharing a name (e.g., "Ridge Trail"
in Shenandoah NP and the same name in a neighboring national forest) would be merged
into a single `MultiLineString` feature before conflation. This could reduce overlap
scores against agency records for either park.

The function comment explicitly acknowledges this: "add spatial clustering later if
cross-park false-merges become a problem." Per CLAUDE.md this is WONTFIX at pilot scale.

Separately: `unary_union` of disconnected `LineString` geometries produces a
`MultiLineString`, which is valid input to Shapely's `hausdorff_distance()` and
`buffer()`. The Hausdorff distance is well-defined for multi-geometries. Conflation
results may be sub-optimal for merged features but will not crash.

---

## Audit 7 — Security

### [LOW] — graph/load.py extras: isidentifier() permits Python keywords as Cypher property names

File: `graph/load.py:137-140`

Finding: `isidentifier()` returns `True` for Python keywords (`return`, `where`, `match`,
`with`, `in`, `as`, `on`, `set`, etc.). The SET clause template `r.{k} = $ex_{k}`
would generate `r.return = $ex_return`. In Cypher, property names accessed via dot
notation after a bound variable are generally parsed as property access, not as keywords,
so most Python keywords are safe. However, some tokens may be context-sensitive in
certain Cypher parsers or future versions.

Impact: Low. No confirmed crash case identified in Neo4j 5's Cypher parser. The pilot
uses controlled `extra` keys, making accidental keyword collision unlikely.

Fix (before production): Add a blocklist of Cypher reserved words, or wrap `k` in
backticks in the SET clause: `` f"r.`{k}` = $ex_{k}" ``.

---

### [LOW] — engine.py: probe runs at origin (not trail) when candidate.point is None

File: `orchestration/engine.py:97`

Finding: `_latlon(candidate.point) or (lat, lon)` falls back to the user's origin
coordinates when `candidate.point` is `None`. A trail with no stored point property
(e.g., fresh ingest before centroid is computed) causes the Verifier to probe the
user's location instead of the trail's location. Weather, fire, and AQI returned to
the user would be for the wrong location. No crash; no log.

Impact: Silent incorrect data for locationless candidates. Rule #1 in spirit: the
source is live and genuine, but the location is wrong, making the fact misleading.

Fix: Log a warning and skip the trail, or skip probes for pointless candidates:

```python
clat_lon = _latlon(candidate.point)
if clat_lon is None:
    log.warning("Candidate %r has no point; skipping live probes", candidate.canonical_id)
    clat_lon = (lat, lon)  # or: continue
clat, clon = clat_lon
```

---

### [LOW] — preflight.py: .env parser does not strip surrounding quotes from values

File: `scripts/preflight.py:21-25`

Finding: The inline .env parser strips whitespace but not surrounding quotes:

```python
k, _, v = line.partition("=")
os.environ.setdefault(k.strip(), v.strip())
```

If `.env` contains `ANTHROPIC_API_KEY="sk-ant-..."`, the stored value would be
`'"sk-ant-..."'` (with double-quote characters), which would fail the Anthropic API
call. The `check_env` masking would show 10 chars starting with `"` rather than `s`.

Impact: Confusion when users write quoted values in .env (common habit from shell). No
crash but a baffling auth failure.

Fix: `v = v.strip().strip('"').strip("'")` after splitting.

---

### [INFO] — docker-compose.yml binding is correct; no exposure

File: `docker-compose.yml:11-12`

Both Neo4j ports (`7474` browser, `7687` bolt) are bound to `127.0.0.1` only. No
other services are defined. No secrets in the compose file (password via env var
substitution with required-value syntax `${NEO4J_PASSWORD:?...}`). ✓

---

## Fixed Summary

| Finding | File | Fix Applied |
|---------|------|-------------|
| CRITICAL: `_alerts()` crashes on `active_alerts=None` | `orchestration/curator.py:37` | `value.get(...) or []` |
| CRITICAL: sprint.sh schema step fails due to `--password-stdin` + stdin redirect | `scripts/sprint.sh:39-43` | Removed `--password-stdin`; use `-f /graph/schema.cypher` + env var auth |
