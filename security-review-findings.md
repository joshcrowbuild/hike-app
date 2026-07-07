# Security Review Findings

**Date:** 2026-07-01 (updated: adversarial deep-dive pass)  
**Scope:** Full trust-seam review — access control, source/guardrail, API edge, ingestion/prune, confidence/corroboration, broad sweep, adversarial deep-dive  
**Method:** Static code review, no runtime testing  

> **Pass 2 — Adversarial Deep-Dive** findings are prefixed `[A]` and appear below the original findings.

---

## High Confidence

### H1. Dev viewer secret shipped to browser bundle — auth bypass

**File:** `frontend/src/data/http/httpPlanner.ts`  
**Seam:** API edge / access control  

The frontend reads the dev viewer secret from `VITE_DEV_VIEWER_SECRET`, which Vite embeds in the browser bundle as a static string. The backend (`api/app.py:129-150`) compares the `X-Dev-Viewer-Secret` header against `ADVENTURE_DEV_VIEWER_SECRET` using `secrets.compare_digest`. Since the secret is in the browser bundle, any user can extract it and authenticate as an arbitrary `viewer_id`, gaining access to that viewer's owned data (Episodes, Beliefs, PhysicalProfile, Outcomes).

The code comments acknowledge this is a dev-only pattern until Stage-8 auth exists, but if this deploy is reachable on the public internet, it is a live authentication bypass.

**Recommendation:** Do not ship the secret to the browser. Use a server-side session token or an OAuth flow. Until then, restrict non-anonymous access to a non-public deploy or remove the `VITE_DEV_VIEWER_SECRET` env var from the frontend build.

---

### H2. Generic exception handler leaks raw exception messages

**File:** `api/app.py:579-583`  
**Seam:** API edge / error handling  

```python
@app.exception_handler(Exception)
async def generic_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    logger.exception("unhandled exception")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
```

The last-resort exception handler returns `str(exc)` to the client. Raw Python exception messages can contain database connection strings, file paths, internal state, or stack details. The route handlers (`/plan`, `/trail`, `/outcome`) catch `Exception` and return `"Internal error"`, but this handler fires for anything that escapes those try/except blocks — middleware errors, serialization failures, dependency injection errors, etc.

**Recommendation:** Replace `str(exc)` with a generic `"Internal error"` message. The server-side `logger.exception` already captures the full traceback for debugging.

---

### H3. Drive-time prefilter uses `CanonicalTrail.point` instead of `Trailhead.point`

**File:** `orchestration/drive_time.py`  
**Seam:** Source/guardrail  

The drive-time prefilter resolves candidate coordinates via `coord_of=lambda c: _latlon(c.point)` where `c` is a `Candidate` carrying `CanonicalTrail.point` (the trail's centroid). But the drive-time routing should measure from the **trailhead** (the actual trail access point), not the trail centroid. A trail whose centroid is far from its trailhead but whose trailhead is within the time budget will be incorrectly pruned, starving notices and cards.

**Recommendation:** Pass the trailhead point from the scout query results into the prefilter instead of the canonical trail centroid.

---

### H4. NWS alerts sub-call failure treated as "no alerts"

**File:** `orchestration/curator.py:47-55`  
**Seam:** Source/guardrail  

```python
def _alerts(fact: VerifiedFact) -> list[str]:
    value = fact.value
    if isinstance(value, dict):
        alerts = value.get("active_alerts") or []
        return [a for a in alerts if isinstance(a, str)]
    return []
```

When the NWS alerts sub-call fails while the forecast succeeds, `active_alerts` is `None`. The `or []` coercion treats this as an empty alert list, so `evaluate_guardrails` sees no alerts and does not block. A real flash flood or evacuation warning could be silently missed.

**Recommendation:** Distinguish "alerts endpoint returned empty" from "alerts endpoint failed." On failure, either suppress the weather fact entirely (source-or-silence at the fact level) or emit a disclosure notice that alerts are unavailable.

---

## Medium Confidence

### M1. Prune guard `min_current=1` allows data loss on partial ingest

**File:** `graph/load.py:217-290`  
**Seam:** Ingestion/prune  

`prune_stale_trails` deletes all same-region trails whose `ingest_version` is not the current run's. The guard requires `n_cur >= min_current` (default 1). This prevents an empty ingest from wiping the graph, but a **truncated** ingest (e.g. Overpass returns 1 trail instead of 500 due to a timeout) will pass the guard and delete all 499 previous trails.

The caller in `pipeline.py:526` adds a belt (`load_counts["loaded"] > 0`), but this has the same threshold — 1 loaded trail is enough to prune everything else.

**Recommendation:** Raise `min_current` to a fraction of the previous trail count, or compare the current load count against the previous run's count and abort the prune if the count drops by more than a configurable ratio (e.g. 50%).

---

### M2. `viewer_id` passed as query parameter on `/trail` and `/outcome`

**File:** `api/app.py:494,536`  
**Seam:** API edge  

```python
def trail_detail(..., viewer_id: str = "anonymous", ...):
def record_outcome(..., viewer_id: str = "anonymous", ...):
```

`viewer_id` is a query parameter on these endpoints, meaning it appears in URL strings and is logged by access logs, browser history, CDN logs, and proxy logs. The `/plan` endpoint uses a request body field (better, but still not ideal). The code comments acknowledge this is Phase 1 and Stage 8 replaces it with an auth header.

**Recommendation:** Move `viewer_id` to a request header (e.g. `X-Viewer-Id`) or derive it from the auth token. Until then, ensure access logs containing `viewer_id` query params are treated as PII.

---

## Low / Informational

### L1. `granted_ids` scope parameter always empty

**File:** `graph/queries.py:63`, `graph/client.py:189`  

The `owner_scope` clause is `(var.owner_id = $viewer_id OR var.owner_id IN $granted_ids)`. The `granted_ids` parameter is always `()` in the current codebase — `scoped_session` defaults to an empty sequence. This is an unused delegation feature. Not a current bug, but if `granted_ids` is ever populated from user input without validation, it becomes an access-control bypass vector.

---

### L2. `corpus_confidence` computed but not exposed in API response

**File:** `orchestration/engine.py:267`  

The `corpus_confidence` field on `PlannedTrail` is computed with the real SAME_AS corroboration count but is not included in the API response. The code comments note this is intentional ("the api response is intentionally unchanged this PR"). This is an incomplete feature, not a bug.

---

### L3. Belief corroboration recount lacks explicit `owner_scope('b')`

**File:** `graph/queries.py:418-430`  

```cypher
MATCH (b:Belief {belief_id: $bid})
MATCH (b)-[:DERIVED_FROM]->(e:Episode)
WHERE {owner_scope('e')}
```

The belief is matched by `belief_id` only (which embeds `owner_id` by construction: `f"belief:{owner_id}:pace_on_grade_moderate"`), without an explicit `owner_scope('b')` clause. The episode side is owner-scoped. This is implicitly safe because the `belief_id` is server-constructed and embeds the owner, but it is less defense-in-depth than the other owned-label queries that use explicit `owner_scope`.

---

### L4. `assert_scoped_write` is a regex-based guard

**File:** `graph/queries.py:49-58`  

The write guard uses regex (`_OWNED_LABEL_RE` and `_OWNER_SCOPE_RE`) to check that owned-label Cypher contains an owner-scope clause. This is defense-in-depth, not a guarantee — a crafted Cypher string could theoretically bypass it. However, since all Cypher is authored in `graph.queries` (never user-supplied), this is acceptable for the current architecture.

---

## Summary of Seams Reviewed

| Seam | Status | Findings |
|------|--------|----------|
| Access control (scoped session) | Sound | H1 (auth bypass via browser secret), L1 (granted_ids unused) |
| Source/guardrail | Two known bugs | H3 (drive-time point), H4 (NWS alerts None) |
| API edge (rate limit, auth, observability) | Mostly sound | H2 (exception leak), M2 (viewer_id in query params) |
| Ingestion/prune | Guard too weak | M1 (min_current=1 allows data loss) |
| Confidence/corroboration | Sound | L2 (corpus_confidence not exposed), L3 (belief scope implicit) |
| Broad sweep | No hardcoded secrets | L4 (regex guard acceptable) |

---

## Things That Are Working Well

- **ScopedSession write guard** (`assert_scoped_write`): Catches unscoped owned-label writes before they reach the database.
- **Source-or-silence**: Live adapters consistently return `None` on failure; no fabricated readings.
- **Degrade-and-disclose**: Drive-time outage, maps read failure, and graph stats failure all degrade gracefully with disclosures.
- **Observability**: Viewer IDs are scrubbed with SHA-256 + optional salt. Correlation IDs are random tokens. No identity leakage in logs.
- **CORS**: Default-deny, never wildcard. Misconfigured deploy fails closed.
- **Secrets handling**: All secrets use `repr=False`. No hardcoded secrets found. All from environment variables.
- **Parameterized Cypher**: All user input flows through `$param` syntax. No Cypher injection risk.
- **Rate limiting**: Conservative per-IP limits on all public endpoints with clean 429 + Retry-After.
- **Set-aside disclosure**: Hard-blocked trails are disclosed with cause + source, never silently dropped.

---

# Pass 2 — Adversarial Deep-Dive

**Focus:** Injection, SSRF, race conditions, DoS amplification, IDOR/data exfiltration, auth bypass, commons re-identification, supply chain.

---

## High Confidence (Adversarial)

### AH1. SSRF via Valhalla `base_url` — internal network probing

**File:** `orchestration/adapters/valhalla.py:48,95,125`, `orchestration/config.py:145`  
**Seam:** Live adapters / SSRF  

`valhalla_base_url` comes from the `VALHALLA_BASE_URL` env var and is used directly in `post_json` / `get_json` calls with `follow_redirects=True` (`_http.py:43`). An operator who controls this env var (or an attacker who can inject it) can point it at `http://169.254.169.254/` (AWS metadata) or any internal service. The `follow_redirects=True` makes it worse — a 302 from an external URL can redirect to an internal address.

While this is an env-var-controlled value (not user input), the attack surface is real in cloud deploys where env vars might be set via a compromised CI/CD pipeline or a container orchestration layer. The `follow_redirects=True` on all adapter HTTP clients is the broader concern — no adapter restricts redirect targets.

**Recommendation:** Disable `follow_redirects` or validate redirect targets against an allowlist. For Valhalla specifically, consider restricting the base URL scheme to `http://` and rejecting loopback/link-local addresses unless explicitly in dev mode.

---

### AH2. Rate limiter bypass behind reverse proxy — shared IP bucket

**File:** `api/ratelimit.py:57-67`  
**Seam:** API edge / DoS  

The rate limiter uses `get_remote_address` (`request.client.host`), which behind Render's edge proxy is the **proxy's IP**, not the client's. The code comments acknowledge this, but the consequence is adversarial: **all clients share one bucket**, so one abuser can starve all legitimate users, OR conversely, the shared bucket means the 10/min limit is a **global** limit, not per-IP — an attacker rotating across many IPs gets the same 10/min total, which is actually more restrictive for the attacker but less restrictive for each individual legitimate user (they all share the budget).

The more dangerous variant: if uvicorn is run with `--proxy-headers` but without `--forwarded-allow-ips` restricting which proxies can set `X-Forwarded-For`, then any client can spoof their IP via the `X-Forwarded-For` header, completely bypassing rate limits. The code comment warns against this but does not enforce it.

**Recommendation:** Use a shared rate-limit store (Redis) with proper proxy-header configuration. Until then, document the deploy requirement prominently and consider a middleware that rejects requests with client-set `X-Forwarded-For` headers.

---

### AH3. `k=50` with live probes creates unbounded third-party API spend

**File:** `api/schemas.py:16`, `orchestration/engine.py:224-248`  
**Seam:** DoS / resource exhaustion  

`PlanRequest.k` allows up to 50 results (`le=50`). Each candidate triggers up to 5 live adapter probes (weather, air, fire, water, permits). With `k=50`, that's **250 third-party API calls** per `/plan` request. At 10 requests/minute (the rate limit), that's **2,500 calls/minute** — enough to exhaust AirNow, FIRMS, or RIDB API quotas, potentially triggering their own rate limits and degrading service for all users.

The TTL cache mitigates repeat calls for the same coordinates, but an attacker can vary `lat`/`lon` slightly to generate cache misses. The cache key rounds to 3 decimal places (~100m), so moving >100m generates a new key.

**Note:** By default, `live_adapters` is empty (`config.py:67`), so no live probes run at all. This DoS vector only applies when adapters are explicitly enabled via `ADVENTURE_LIVE_ADAPTERS` — which is required for the product to function as designed.

**Recommendation:** Lower `k` max to 20 for the public API. Add a per-request probe budget that short-circuits the candidate loop after N cache misses. Consider a separate, lower rate limit for `k > 10`.

---

### AH4. `viewer_id` is a free-text string with no validation — identity spoofing at scale

**File:** `api/schemas.py:17`, `api/app.py:129-150`  
**Seam:** Access control / auth  

`viewer_id` is a `str` with no format validation, length limit, or allowlist. Combined with H1 (dev secret in browser bundle), an attacker can:
- Enumerate `viewer_id` values (`josh`, `alice`, `bob`) and read their personal data (beliefs, profile, episodes)
- Inject arbitrary strings as `viewer_id`, potentially causing Cypher parameter injection if any query uses string interpolation (currently safe — all parameterized)
- Use extremely long `viewer_id` strings to bloat Neo4j query parameters or log lines

The `scrub_viewer` function in observability hashes the ID, but the raw ID is still used in Cypher queries, stored in the graph, and appears in error logs (`outcome.py:95` logs the raw `viewer_id`).

**Recommendation:** Validate `viewer_id` format (e.g., `^[a-zA-Z0-9_-]{1,64}$`). Enforce a max length. Consider an allowlist or registration flow. At minimum, sanitize `viewer_id` in all log statements, not just observability.

---

## Medium Confidence (Adversarial)

### AM1. TTLCache is not thread-safe — race condition on concurrent `/plan` requests

**File:** `orchestration/adapters/registry.py:122-181`  
**Seam:** Race conditions / data integrity  

`TTLCache` uses a plain `dict` (`self._store`) with no locking. Under concurrent requests (uvicorn with multiple workers or async), two requests probing the same adapter+point simultaneously can:
- Both miss the cache and both call the third-party API (wasted quota — the `stats.misses` counter undercounts)
- One reads `_store` while another is mid-`pop` during FIFO eviction, potentially getting a stale reference

The `ProbeStats` counters (`hits`, `misses`) are also non-atomic integers — concurrent increments can lose counts, making observability metrics inaccurate.

In practice, FastAPI's default sync route handlers run in a threadpool, so concurrent requests **do** hit this path simultaneously.

**Recommendation:** Use `threading.Lock` around `_store` access and `stats` updates. Or switch to `cachetools.TTLCache` which is thread-safe. The impact is correctness/observability, not a security bypass.

---

### AM2. Background belief-update queue has no error handling or dead-letter path

**File:** `api/app.py:517-526`, `orchestration/belief_update.py`  
**Seam:** Data integrity / race conditions  

`_drain_queue_bg` runs after the HTTP response is sent via `BackgroundTasks`. If the belief update fails (graph connection drops, Cypher error), the exception is swallowed by FastAPI's background task runner — the user's outcome is recorded but their beliefs are never updated, and **no one is notified**. There is no retry, no dead-letter queue, no persistent record of the failed update.

Worse, the `BeliefUpdateQueue` is created fresh per request (`BeliefUpdateQueue()` at `app.py:557`), so there is no cross-request recovery mechanism — a failed update is permanently lost.

**Recommendation:** Wrap `_drain_queue_bg` in a try/except with structured logging. Add a retry mechanism or a persistent dead-letter table in the graph. At minimum, log the failure so it can be manually reconciled.

---

### AM3. Commons fork re-identification risk via sparse trail+band+month combinations

**File:** `ingestion/commons_fork.py:141-173`  
**Seam:** Privacy / commons  

The commons observation stores `trail_id` (scalar, not bucketed), `capability_band` (4 values), `month` (YYYY-MM), `ascent_bucket` (200m bands), and `distance_bucket` (5km bands). On a rarely-traveled trail, a single observation with a specific band+month combination creates a **singleton group** that is effectively a fingerprint — an attacker with direct graph database access and a public activity feed (Strava) could cross-reference trail + month + approximate pace/distance to re-identify the contributor.

The k-anonymity gate (`n >= k`) prevents **aggregation/exposure**, but the raw `:CommonsObservation` rows still accrete in the graph. `CommonsObservation` is deliberately excluded from `OWNED_LABELS` (`queries.py:25-27`) and no API read query targets it — the scoped session runs predefined query specs, not arbitrary Cypher — so **API consumers cannot read these rows**. The risk is limited to someone with direct Neo4j access (admin, DBA, backup holder).

**Recommendation:** Verify that no future read query inadvertently traverses to or matches `:CommonsObservation` nodes. Consider a graph-level constraint or plugin that restricts the label to internal/service accounts. The existing design is sound for the current API surface; this is a defense-in-depth note for future feature growth.

---

### AM4. `region_id` used in file path construction — path traversal in ingestion CLI

**File:** `ingestion/pipeline.py:48-49`  
**Seam:** Path traversal  

```python
def load_region(region_id: str) -> Region:
    path = Path(f"regions/{region_id}.geojson")
```

`region_id` comes from CLI args (`--region`). While this is a CLI tool (not the API), if `region_id` contains `../`, the path resolves outside the `regions/` directory. An attacker with access to the ingestion CLI (e.g., via a compromised CI pipeline) could read arbitrary `.geojson` files. The `sys.exit(1)` on missing file prevents arbitrary file reads (only `.geojson` extension matches), but directory traversal is still possible.

**Recommendation:** Validate `region_id` to reject path separators: `if "/" in region_id or "\\" in region_id or ".." in region_id: sys.exit(1)`.

---

### AM5. Drive-time budget accepts non-finite config and non-positive parsed budgets

**File:** `orchestration/config.py:146`, `orchestration/drive_time.py:25-31`, `orchestration/intent.py:53-56`  
**Seam:** Input validation  

```python
drive_speed_kmh=float(e.get("DRIVE_SPEED_KMH", "60.0")),
```

The earlier review overstated this as a crash risk. `time_budget_s` clamps the **derived** speed path with `speed_m_s = max(0.1, drive_speed_kmh * 1000.0 / 3600.0)`, so `DRIVE_SPEED_KMH=0`, negative values, and `NaN` do **not** produce `ZeroDivisionError`; with this argument order, `max(0.1, float("nan"))` returns `0.1`. Those values instead silently degrade to a very slow speed and a very large derived budget.

The remaining issues are narrower:

- **Non-finite/extreme config values:** `DRIVE_SPEED_KMH=inf` is accepted and yields a zero-second derived budget (`radius_m / inf == 0.0`), which can over-prune. Very large finite speeds produce near-zero budgets.
- **Parsed intent bypasses the clamp:** if `intent.time_budget_s` is set, `time_budget_s` returns it directly (`return float(intent.time_budget_s)`). `intent._parse` accepts any integer from the mechanical model, including `0` or negative values. `fetch_isochrone` clamps that to a minimum one-minute contour, but the matrix-only fallback compares returned drive seconds against the original non-positive budget, which can prune every timed candidate.

**Recommendation:** Validate `drive_speed_kmh` with `math.isfinite(value) and value > 0` in `Settings.from_env()`. Also validate `Intent.time_budget_s` as a positive integer either in `intent._parse` or inside `time_budget_s` before returning the stated budget.

---

## Low / Informational (Adversarial)

### AL1. HTTP adapters follow redirects with no target validation

**File:** `orchestration/adapters/_http.py:43`  
**Seam:** SSRF  

All adapter HTTP clients are built with `follow_redirects=True`. While adapter URLs are currently hardcoded constants (NWS, AirNow, FIRMS, RIDB), the Valhalla URL is config-driven. A compromised external API could redirect to an internal service. Low risk because the external APIs are government/trusted, but it's a latent SSRF vector if any adapter URL becomes configurable.

---

### AL2. `canonical_id` in `/trail/{canonical_id}` is unvalidated free text

**File:** `api/app.py:489-514`  
**Seam:** Injection / DoS  

`canonical_id` is a path parameter with no format validation. It flows into `trail_detail_query(canonical_id)` as a parameterized Cypher parameter (safe from injection), but an extremely long string or a string with special characters could cause unexpected behavior in Neo4j's query planner or consume extra memory. Low risk because the parameterized query prevents injection.

---

### AL3. `OutcomeBody.delta_answer` free-text stored unescaped in graph

**File:** `orchestration/outcome.py:114-117`, `graph/queries.py:500-525`  
**Seam:** Data injection  

The `delta_answer` field is user free-text that gets stored as a Belief value via `upsert_stated_belief(belief_id, delta)`. It flows through a parameterized Cypher query (safe from Cypher injection), but there is no length limit, content validation, or sanitization. An attacker could store a very long string (memory bloat) or content that breaks downstream LLM context assembly (prompt injection via stored data).

**Recommendation:** Add a max length on `delta_answer` (e.g., 2000 chars). Consider basic content sanitization or prompt-injection defenses when this text is later assembled into LLM context.

---

### AL4. `observation_id` in commons fork uses `uuid4()` — collision risk is negligible but not cryptographically guaranteed unique

**File:** `ingestion/commons_fork.py:163`  
**Seam:** Data integrity  

`uuid.uuid4()` is random and collision risk is negligible, but it is not guaranteed unique across a distributed system. The MERGE on `observation_id` makes it idempotent under retry, but two concurrent ingests of the same episode (race condition) would create two observations. Low risk in practice.

---

### AL5. No lockfile — `pyproject.toml` has version lower bounds but no pinned lockfile

**File:** `pyproject.toml`  
**Seam:** Supply chain  

`pyproject.toml` exists with version lower bounds (e.g., `neo4j>=5.20`, `httpx>=0.27`, `fastapi>=0.111`, `slowapi>=0.1.9`). However, there is no lockfile (`poetry.lock`, `Pipfile.lock`, `requirements.txt` with pinned versions). Without a lockfile, `pip install -e .` resolves to the latest compatible versions at install time, so two deploys from the same commit can have different transitive dependency versions. A compromised upstream package that publishes a new version within the `>=` range would be pulled into the next deploy.

**Recommendation:** Generate and commit a lockfile (e.g., `pip-compile` → `requirements.txt`, or `poetry lock`). Run `pip-audit` or `safety check` in CI against the locked versions.

---

## Adversarial Summary

| Vector | Findings | Worst Case |
|--------|----------|------------|
| SSRF | AH1, AL1 | Internal network probing via Valhalla URL |
| Rate limit bypass | AH2 | Total bypass via X-Forwarded-For spoofing |
| DoS / resource exhaustion | AH3 | 250 API calls/request, quota exhaustion |
| Auth / identity spoofing | AH4 | Enumerate and impersonate any viewer_id |
| Race conditions | AM1, AM2 | Lost belief updates, inaccurate cache stats |
| Privacy / re-identification | AM3 | Commons observation fingerprinting (direct DB access only, not API) |
| Path traversal | AM4 | Directory traversal via region_id in CLI |
| Input validation | AM5, AL2, AL3 | Non-finite drive speed / non-positive parsed budget can distort pruning, prompt injection via stored text |
| Supply chain | AL5 | No lockfile (pyproject.toml has lower bounds) |

---

## Updated: Things That Are Working Well (Adversarial Pass)

- **No Cypher injection**: All user input flows through parameterized queries. The `assert_scoped_write` regex guard is defense-in-depth on top.
- **No hardcoded secrets**: All credentials from env vars. `repr=False` on all secret fields.
- **Commons fork de-id**: HMAC with keyed salt, endpoint trimming, bucketed quasi-identifiers. The structural no-path test is well-designed.
- **Privacy routing for LLM**: Personal context is forced to the local model provider via `touches_private_overlay=True`. Cloud judge only sees anonymous free-text.
- **Outcome ownership check**: `write_outcome` verifies episode ownership before any write. MERGE key includes `owner_id`, preventing cross-owner writes.
- **Atomic commons write**: Episode + commons observation commit in one managed transaction. No half-state possible.

---

## Pass 2b — Self-Review of Adversarial Findings

**Method:** Re-verified each adversarial finding against the actual code. Three corrections made.

### Corrections Applied

| Finding | Original Claim | Correction | Impact |
|---------|---------------|------------|--------|
| **AM3** | "Anyone with graph read access (including anonymous viewer scope) can see CommonsObservation rows" | **Overstated.** No API read query targets `:CommonsObservation`. The scoped session runs predefined query specs, not arbitrary Cypher. `CommonsObservation` is deliberately excluded from `OWNED_LABELS` (`queries.py:25-27`). API consumers cannot read these rows — risk is limited to direct DB access. | Downgraded from "API-exfiltrable" to "internal-only risk" |
| **AM5** | "Zero speed causes `ZeroDivisionError`" | **Factual error.** `time_budget_s` (`drive_time.py:30`) clamps the derived-speed path with `max(0.1, ...)`, preventing division by zero; `max(0.1, float("nan"))` also returns `0.1`. The remaining issue is non-finite/extreme config values (`inf`) and parsed `Intent.time_budget_s` values that bypass the clamp. | Reframed from "crash" to "input validation gap affecting pruning" |
| **AL5** | "No `requirements.txt`, `pyproject.toml`, `poetry.lock`, or `Pipfile.lock` was found" | **Factual error.** `pyproject.toml` exists with version lower bounds (`neo4j>=5.20`, `httpx>=0.27`, etc.). No lockfile exists, but the claim that no dependency manifest was found is wrong. | Corrected: "has lower bounds, no lockfile" |
| **AH3** | Implied 250 calls/request is the default | **Added context.** Default `live_adapters` is empty (`config.py:67`), so no probes run unless explicitly enabled. The DoS vector requires `ADVENTURE_LIVE_ADAPTERS` to be set. | Added qualifying note |

### Findings That Held Up Under Self-Review

- **AH1** (SSRF): Confirmed — `follow_redirects=True` on all adapters, Valhalla URL is config-driven.
- **AH2** (Rate limit bypass): Confirmed — `get_remote_address` behind proxy, X-Forwarded-For spoofing risk.
- **AH4** (viewer_id no validation): Confirmed — `str` with no pattern/length constraint in Pydantic schema.
- **AM1** (TTLCache not thread-safe): Confirmed — plain `dict`, no locking, FastAPI sync routes run in threadpool.
- **AM2** (Background queue no error handling): Confirmed — `_drain_queue_bg` has no try/except, queue is per-request.
- **AM4** (Path traversal): Confirmed — `Path(f"regions/{region_id}.geojson")` with no validation.
- **AL1–AL4**: All confirmed as described.
