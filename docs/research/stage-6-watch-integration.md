# Stage 6 — Watch Integration (design)

*Workplan Stage 6. Draft v0.1 — June 23, 2026. Builds on Stage 5 (memory schema); feeds into Stage 7 (eval) and Stage 9 (commons).*

> **Status: DESIGN.** Specifies the Garmin + Coros ingestion pipeline, FIT extraction, episode creation, belief update mechanics, MCP config, and privacy discipline for all watch-derived data. Decisions in §7. Honors rules #6, #7, #9, #10.

> **What this produces (per workplan):** Garmin access (library + auth + fragility handling) · Coros access (official MCP) · FIT parsing · the **readiness filter** logic · polling / ingestion jobs + the always-on decision.

> **⚠️ Architecture update (June 24):** the device-access design in §1–2 is now formalized as a **config-driven device-provider seam** — see [`device-integration-seam.md`](./device-integration-seam.md) (built as the rescoped Epic 004). Garmin / Coros / future vendors (Suunto, Polar, Wahoo, Apple Health, Strava…) are adapters behind one `DeviceAdapter` contract selected by config; adding a manufacturer is one adapter file + one config line. This doc remains the source of truth for the FIT fields (§1.3), per-vendor endpoints/auth (§1.1–1.2), and the **device-agnostic** episode / belief / commons mechanics (§2–6) the seam feeds into.

---

## 1. Data sources

### 1.1 Garmin Connect API

`python-garminconnect` uses SSO session auth, not a public OAuth2 flow. It is unofficial and fragile.

**Auth flow:**
1. The scheduled job calls `garth.client.login(email, password)` on first run. Credentials are read from the secrets manager (`GARMIN_EMAIL`, `GARMIN_PASSWORD`) — never from the repo or `.env` file.
2. The library persists a session token (cookie) to a local cache directory (`~/.garth`). Sessions remain valid for ~30 days of activity.
3. On expiry (`GarthHTTPError: 401`): log + emit a re-auth signal to the connections UI; skip the sync cycle; retry on next scheduled run.

**Endpoints polled (via the garth HTTP layer):**

| Endpoint | Purpose |
|---|---|
| `GET /activitylist-service/activities/search/activities?activityType=hiking&start=0&limit=20` | Activity list (paginated; sorted by date desc) |
| `GET /download-service/files/activity/{activity_id}` | FIT file download (returns a ZIP) |
| `GET /wellness-service/wellness/bodyBattery/{start_date}/{end_date}` | Body Battery — readiness filter only, never persisted |

**Rate-limit discipline:** poll at most once per 6 hours; exponential backoff (1h → 2h → 4h) on 429 or connection error. This is an unofficial API — keep Garmin access behind a swappable adapter interface so an official replacement (Garmin Health API, currently gated) can substitute without touching the rest of the pipeline.

**Decommission risk:** `python-garminconnect` is community-maintained and has broken on past Garmin auth changes. Mitigation: the adapter interface abstracts the library; the rest of the pipeline sees only the output dict.

### 1.2 Coros official MCP

Coros provides an **official MCP server** (`@coros/mcp-server`) backed by the `open.coros.com` REST API with standard OAuth2 PKCE. Credentials (`COROS_CLIENT_ID`, `COROS_CLIENT_SECRET`) live in the secrets manager.

MCP tools exposed:
- `coros_list_activities(user_id, start_date, limit, sport_type)` — paginated activity list
- `coros_get_activity(activity_id)` — activity metadata + summary stats
- `coros_download_fit(activity_id)` — raw FIT bytes

**Coros MCP is for interactive queries only.** Batch ingestion (scheduled polls) calls the `open.coros.com` HTTP API directly — MCP earns its keep mid-reasoning, not in a cron job. See §5 for the `.mcp.json` config.

### 1.3 FIT file structure — what we extract

All hiking-relevant data lives in the `session` message and `record` messages:

**From `session`:**

| FIT field | Episode property | Notes |
|---|---|---|
| `total_timer_time` | `moving_min` | Moving time (excludes auto-pause), in seconds → convert to minutes |
| `total_elapsed_time` | `duration_min` | Total elapsed including pauses |
| `total_distance` | `distance_m` | Meters |
| `total_ascent` | `ascent_m` | Meters |
| `total_descent` | `descent_m` | Meters |
| `avg_heart_rate` | HR zone input | bpm; used for `heat_response` computation |
| `start_time` | `date` | UTC timestamp |

**From `record` messages (sampled):**
- `position_lat`, `position_long`, `altitude` — GPS track polyline for activity→trail matching (§3.2)
- `heart_rate` — per-point HR for zone-on-grade analysis (`heat_response` signal)

`lap` messages are parsed but not stored in v1 (useful for future effort-topology commons data — Stage 9).

### 1.4 What we explicitly do NOT ingest

- **VO2max estimates** — vendor-computed, opaque provenance, meaningless across watches; never enters the belief store.
- **Sleep data beyond a readiness signal** — sleep staging, REM breakdown, sleep score. Only Body Battery (already summarized) is used, and only as a filter.
- **All-day HR / stress timeseries** — available via wellness API; out of scope for an episode-scoped pipeline.
- **Raw biometric archive (HR time series)** — stored in the FIT `record` stream but not persisted to Neo4j. Capability signals are extracted at ingest and discarded; the graph never holds the raw stream (Rule #7, Stage 5 S5-8).
- **Live readiness scores at ingest time** — Body Battery and recovery scores are fetched at query time for the readiness filter, never persisted as beliefs (Stage 5 S5-9).

---

## 2. Ingestion pipeline

### 2.1 Trigger

`scripts/watch_sync.py` runs on a cron schedule (every 6 hours). This is a plain Python script, not an MCP tool. On a local machine the poller runs when the machine is awake; always-on behavior requires a persistent host (VPS / Pi) — deferred per workplan. The job is idempotent: running it hourly is safe.

Per-provider order: Garmin first (richer data), then Coros. Each provider's adapter implements the same interface: `adapter.fetch_new_activities(since: datetime) → list[RawActivity]`.

### 2.2 Deduplication

The MERGE pattern (§3.1) is keyed on `(watch_activity_id, owner_id)`. Activity IDs are namespaced by source: `"garmin:{activity_id}"` (integer from the activity list) and `"coros:{activity_id}"`. An exact re-ingest is a structural no-op — only `updated_at` changes on MATCH. The job queries for the most-recent `Episode.created_at` per owner before fetching to limit the API call window.

### 2.3 FIT parsing — library choice

**`fitdecode`** (primary). Better handling of compressed timestamps (common in Garmin FIT v2 files), actively maintained, cleaner iterator API. `fitparse` is the fallback for FIT files `fitdecode` fails to open — log the version and fall back gracefully.

```python
import fitdecode

def parse_session(fit_bytes: bytes) -> dict:
    result = {}
    with fitdecode.FitReader(fit_bytes) as reader:
        for frame in reader:
            if frame.frame_type == fitdecode.FIT_FRAME_DATA and frame.name == 'session':
                result = {
                    'moving_min':   int((frame.get_value('total_timer_time') or 0) / 60),
                    'duration_min': int((frame.get_value('total_elapsed_time') or 0) / 60),
                    'distance_m':   int(frame.get_value('total_distance') or 0),
                    'ascent_m':     int(frame.get_value('total_ascent') or 0),
                    'descent_m':    int(frame.get_value('total_descent') or 0),
                    'avg_hr':       frame.get_value('avg_heart_rate'),   # may be None
                    'start_time':   frame.get_value('start_time'),
                }
                break
    return result
```

GPS track extraction happens in a separate pass over `record` messages (not shown — outputs a `list[tuple[float,float]]` for the trail-matching step).

### 2.4 Transform — pace_on_grade computation

Grade-adjusted pace (Naismith approximation) normalizes pace across trails with different elevation profiles:

```python
def pace_on_grade(distance_m: int, ascent_m: int, moving_min: int) -> float | None:
    if not moving_min:
        return None
    # Naismith: 1m ascent ≈ 10m additional flat effort
    grade_adj_km = (distance_m + ascent_m * 10) / 1000.0
    return moving_min / grade_adj_km  # min/km
```

This is a pure arithmetic transform — no LLM call. The result is stored as `Episode.pace_on_grade` and fed into the EWMA belief update (§4.2).

### 2.5 Sensitivity routing

Watch ingest processes personal health data. Any LLM call in this path (e.g., extracting a `conditions_note` from an activity description) must call:

```python
provider = provider_registry.route(sensitivity="private")
```

This returns the **local adapter** unconditionally (Stage 4 §2). The routing is wired at the job entrypoint — it cannot be overridden per-call. Cloud models never see raw FIT-derived HR or GPS coordinates.

### 2.6 Error handling

| Failure mode | Behavior |
|---|---|
| Garmin session expired | Log + emit re-auth signal to connections UI; skip poll; retry next cycle |
| Garmin / Coros 429 or connection error | Exponential backoff (1h → 2h → 4h); silent degrade |
| FIT file malformed (parse error) | Log activity_id + error; write stub `Episode` with `fit_parsed=false`; do not block |
| Trail match returns no result | `trail_id=null`; episode created; contributes to PhysicalProfile only |
| Neo4j write failure | Retry 3× with 5s backoff; log and defer to next cycle if all fail |
| NWS call fails during heat_response computation | Skip heat inference for this episode; try again on next episode |

---

## 3. Episode creation

### 3.1 MERGE pattern (idempotent)

```cypher
MERGE (e:Episode {watch_activity_id: $watch_activity_id, owner_id: $owner_id})
ON CREATE SET
    e.episode_id    = randomUUID(),
    e.trail_id      = $trail_id,
    e.date          = date($start_date),
    e.source        = 'watch_fit',
    e.duration_min  = $duration_min,
    e.moving_min    = $moving_min,
    e.distance_m    = $distance_m,
    e.ascent_m      = $ascent_m,
    e.descent_m     = $descent_m,
    e.pace_on_grade = $pace_on_grade,
    e.party_members = $party_members,
    e.fit_parsed    = $fit_parsed,
    e.created_at    = datetime(),
    e.updated_at    = datetime()
ON MATCH SET
    e.updated_at = datetime()
WITH e
MATCH (p:Person {member_id: $owner_id})
MERGE (p)-[:DID]->(e)
WITH e
MATCH (ct:CanonicalTrail {canonical_id: $trail_id})
  WHERE $trail_id IS NOT NULL
MERGE (e)-[:ON]->(ct)
```

After episode write: push `{episode_id, owner_id}` to the belief-update queue (§4.1). Separately, fork the commons write (§6.2) in the same transaction.

### 3.2 Activity → trail matching

**Primary: GPS track overlap.** Extract GPS polyline from `record` messages → build Shapely `LineString` → buffer by 100m → query the graph for `CanonicalTrail` nodes within the bounding box (Neo4j point index on the representative point, then fetch `geom_wkt`). Load candidate trail geometries into Shapely, compute `buffer.intersection(trail_line).length / trail_line.length` as an overlap fraction. Accept the best match if overlap ≥ 0.7.

**Fallback: title name match.** The Garmin activity name field (from the API response, not the FIT file) often contains the trail name. Run `rapidfuzz.process.extractOne(activity_name, candidate_trail_names)`. Accept if score ≥ 80.

**No match: `trail_id = null`.** Episode is created; contributes to `PhysicalProfile` (pace, range, ascent maxima) but not to trail-specific beliefs. Log the unmatched `watch_activity_id` for future manual review.

Both thresholds (0.7 overlap, 80 fuzzy score) are configuration values — tune empirically in the first real-data spike.

### 3.3 Party detection

Ruby is a dependent node, not an account; she has no watch. Party detection is **manual only**: the outcome card includes a toggle "Was Ruby with you?" Confirming sets `Episode.party_members = ["ruby"]`. Default on sync: `party_members = []`.

If the outcome card is skipped, `party_members` stays as the default. No automated proximity detection between independent device streams is implemented in Phase 1 — that requires simultaneous always-on sync of both devices' telemetry, which is out of scope.

---

## 4. Belief updates

### 4.1 Queue

Belief updates are **not computed in the ingest path**. After a successful Episode MERGE, the ingest job pushes `{episode_id, owner_id}` to an `asyncio.Queue`. A worker coroutine drains the queue and runs the update logic. This decouples the ingest path (fast write) from belief computation (slower, multiple Cypher reads + writes).

On restart, the queue is rebuilt from `Episode` nodes where `fit_parsed=true` and `Belief.last_updated_at < e.created_at` (episodes that haven't triggered an update yet).

### 4.2 EWMA pace update (α=0.3, per Stage 5 §3)

```python
def update_pace(current_estimate: float | None, new_pace: float, alpha: float = 0.3) -> float:
    if current_estimate is None:
        return new_pace  # first episode
    return alpha * new_pace + (1 - alpha) * current_estimate
```

Written back:

```cypher
MATCH (pp:PhysicalProfile {owner_id: $owner_id})
SET pp.pace_on_grade    = $new_pace,
    pp.pace_confidence  = $new_confidence,
    pp.episode_count    = pp.episode_count + 1,
    pp.last_episode_at  = date($episode_date),
    pp.updated_at       = datetime()
```

The associated `Belief {key: "pace_on_grade_moderate"}` also gets `corroboration_n` incremented and `last_updated_at` refreshed. `Belief.confidence` is recomputed from `corroboration_n` + recency (same formula as the Stage 5 decay model).

### 4.3 max_distance_m and max_ascent_m

These are empirical maxima — not means. The user demonstrably *can* do what they've done.

```cypher
MATCH (pp:PhysicalProfile {owner_id: $owner_id})
SET pp.max_distance_m = CASE WHEN $distance_m > pp.max_distance_m THEN $distance_m
                              ELSE pp.max_distance_m END,
    pp.max_ascent_m   = CASE WHEN $ascent_m   > pp.max_ascent_m   THEN $ascent_m
                              ELSE pp.max_ascent_m END
```

### 4.4 heat_response inference

After each episode with `avg_hr` and a known start date:
1. Fetch NWS high temperature at the episode's representative point on the episode date (archived from the daily weather fetch, or re-fetched from `api.weather.gov/gridpoints/{wfo}/{x},{y}/forecast/hourly`).
2. If `temperature > 28°C` AND `avg_hr > profile.hr_zone2_threshold * 1.15`: increment `PhysicalProfile.heat_hit_count`.
3. When `heat_hit_count >= 2`: write `Belief {key: "heat_sensitivity", value: "sensitive", axis: "capability", type: "inferred", corroboration_n: 2}`.

If NWS is unavailable for the episode date, skip heat inference for this episode — log and move on. This is the standard degrade-and-disclose pattern (Rule #1).

### 4.5 Provisional → confirmed (N=3, per Stage 5 §2)

New beliefs are written with `confidence < 0.4`, `type="inferred"`, `corroboration_n=1`. At `corroboration_n = 3`, the belief crosses the confidence floor and becomes eligible for injection into the Curator context assembly. No automatic user confirmation — the user affirms via the belief-store UI (sets `confirmed_by_user=true`, `type="stated"`). Stated beliefs never decay.

---

## 5. MCP config

### 5.1 `.mcp.json`

```json
{
  "mcpServers": {
    "coros": {
      "command": "npx",
      "args": ["@coros/mcp-server"],
      "env": {
        "COROS_CLIENT_ID": "${COROS_CLIENT_ID}",
        "COROS_CLIENT_SECRET": "${COROS_CLIENT_SECRET}"
      }
    }
  }
}
```

Garmin is **not** wired into `.mcp.json`. Batch Garmin ingestion uses `python-garminconnect` as a scheduled job. A Garmin MCP server (community-built) may be added later for interactive agent queries; deferred.

Credentials in `.mcp.json` are environment variable references, not values — the secrets manager populates them at runtime.

### 5.2 MCP tool calls — interactive context only

Coros MCP tools are called only when an interactive agent (the future "ask the planner" chat) needs live watch data mid-reasoning. Example:

```json
{
  "tool": "coros_list_activities",
  "params": {
    "user_id": "josh",
    "start_date": "2026-06-01",
    "limit": 5,
    "sport_type": "hiking"
  }
}
```

The agent calls this to answer "show me my recent hikes" — a read query. If the response includes an activity not yet in the graph, it is enqueued for the next scheduled sync. The agent never writes `Episode` nodes directly; the batch job owns all writes.

### 5.3 MCP tool results — belief updates vs. readiness filter

| MCP tool result | Handling |
|---|---|
| `coros_list_activities` — activity not yet in Episode | Enqueue for next batch sync; do not write from agent context |
| `coros_get_activity` — activity details | Read-only display in the agent's response |
| Live recovery score (Coros training status) | **Readiness filter parameter only** — never persisted as a belief |

Readiness data from MCP flows to the Curator as a JIT filter parameter (`$readiness_score`, `$readiness_available=true`), applied only when the user has enabled "tune to today's recovery." No graph write occurs. The filter is a constraint (Curator hard-filter half), not a ranking adjustment.

---

## 6. Privacy and disclosure

### 6.1 Sensitivity routing

All LLM calls in the watch ingestion path are routed to the **local provider adapter** by `provider_registry.route(sensitivity="private")`. This is enforced at the job entrypoint — not an optional per-call setting. Personal health data (HR, GPS, pace) never reaches a cloud model in any form.

This is consistent with Stage 4 §2's routing policy: cloud is acceptable for the anonymous world+conditions layer; anything touching the private overlay goes local. Watch data is the most sensitive class of private overlay data.

### 6.2 Commons fork (per Stage 5 §6 and Rule #8)

On `Episode` creation, a `CommonsObservation` is written in the same transaction:

1. **Person link severed**: `CommonsObservation` has no `owner_id` property and no edge to `:Person`. A one-way audit hash (`writer_hash`) is stored for revocation lookup only; it cannot be reversed to the person.
2. **Endpoint trimming**: if a GPS track is present, strip the first and last 250m before writing. This removes the re-identification risk at trailhead parking lots and home addresses.
3. **Capability-band substitution**: raw `pace_on_grade` is bucketed into one of four bands before the commons write:

   | Band | Range |
   |---|---|
   | `"easy"` | ≤ 12 min/km |
   | `"easy-moderate"` | 12–16 min/km |
   | `"moderate"` | 16–20 min/km |
   | `"strenuous"` | > 20 min/km |

   The raw pace value never appears in `CommonsObservation`.

The private `Episode` retains full data. Once `CommonsObservation` is aggregated above the k-anonymity threshold, deletion of the individual contribution is no longer recoverable — disclosed in onboarding consent.

### 6.3 Disclosure tag

Any feed card where watch-derived capability data influenced ranking carries a disclosure tag on the Curator's output:

```python
{
    "source_tags": ["watch_capability"],
    "rationale": "Matched to your typical pace range (from past hikes)."
}
```

The frontend renders this as an attributive note in the card's rationale section (not a banner — per the calm-utility aesthetic). The `Belief.source_episode_ids` property makes the full provenance traversable in the belief-store UI (which trips generated the belief, which episodes, what confidence).

---

## 7. Stage 6 decisions

| # | Decision | Status |
|---|---|---|
| S6-1 | FIT parser: `fitdecode` primary (compressed-timestamp support, active maintenance); `fitparse` fallback on parse failure | ✅ |
| S6-2 | Garmin access via `python-garminconnect` (SSO session auth, unofficial); re-auth on session expiry; adapter interface keeps it swappable for a future official path | 🔶 Fragile — monitor for auth breakage |
| S6-3 | Coros via official MCP (`@coros/mcp-server`) for interactive queries; direct HTTP for batch ingestion | ✅ |
| S6-4 | Activity→trail matching: Shapely GPS buffer-intersect (100m, ≥0.7 overlap) primary; `rapidfuzz` title match (≥80 score) fallback; `trail_id=null` on no match | 🔶 Overlap threshold needs empirical tuning on first real data |
| S6-5 | Party detection: manual toggle on outcome card only; no automated proximity detection in Phase 1 | ✅ |
| S6-6 | Belief updates via `asyncio.Queue` drained by worker coroutine; never blocks ingest path; queue rebuilt from unprocessed Episodes on restart | ✅ |
| S6-7 | pace_on_grade via Naismith (`(distance_m + ascent_m * 10) / 1000`); α=0.3 EWMA (per S5-6 — tune in spike) | 🔶 |
| S6-8 | heat_response: NWS archived temp at episode date; 2 heat-hit episodes before belief promotion; degrades gracefully if NWS unavailable | 🔶 Depends on NWS historical data availability |
| S6-9 | All LLM calls in ingest path route to local provider via `provider_registry.route(sensitivity="private")`; enforced at job entrypoint | ✅ |
| S6-10 | Commons fork writes `CommonsObservation` in same transaction as Episode; person link severed at write; 250m endpoint trim; 4-band capability substitution | ✅ |
| S6-11 | Garmin is **not** in `.mcp.json`; batch ingestion = scheduled job; MCP reserved for interactive agent queries; MCP tools never write Episode nodes directly | ✅ |
| S6-12 | Always-on poller (for true push / same-day sync) is deferred; Phase-1 syncs on machine wake or manual trigger | 🔶 Revisit when always-on infra is decided (Stage 8 gating event) |
