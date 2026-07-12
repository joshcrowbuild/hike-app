# Comprehensive Security Review — 2026-07-12

> **PO verification stamp (2026-07-12):** third-party review (owner-commissioned external agent). All 8 new findings **verified accurate against code** by the PO before action; the prior-findings mitigation table spot-checked against shipped waves and found correct. **Remediated same day in PR #166** (lanes 1–6: input-validation caps, `_finite_positive` env parsing, secret-URL log redaction, NWS second-hop pin, committed lockfile + blocking pip-audit). One gap: the review graded "log hygiene ✅" and missed that FIRMS/AirNow keys rode in httpx-logged request URLs — found by the PO in live Render logs the same day and fixed in the same PR. Four MODERATE follow-ups from #166's self-review are documented in that PR. NF8/AM3/L-series remain tracked design notes.

**Scope:** Full trust-surface audit — API edge, auth, access control, input validation, SSRF, injection, DoS, privacy, supply chain, deployment, CI/CD, frontend.
**Method:** Static code review across all surfaces, cross-referenced against the prior review (`security-review-findings.md`, 2026-07-01).
**Context:** The app is a **live public deployment** (`state.json` confirms `https://adventure-planner-api.onrender.com`), which raises the severity of any auth-boundary or input-validation gap.

---

## Executive Summary

The codebase is in **strong security posture** for a Phase-1 personal application. The prior review (2026-07-01) identified 17 findings across two passes; **13 of those have since been mitigated**. The remaining open items are low-to-medium severity. This review identifies **8 new findings** not covered by the prior pass, most related to input validation gaps on fields the prior review didn't examine.

**No critical or high-severity vulnerabilities remain.** The most actionable items are input-validation hardening (unbounded text fields, unvalidated path params) and supply-chain maturity (lockfile).

---

## Prior Findings: Mitigation Status

### Mitigated (confirmed fixed in code)

| ID | Finding | How it was fixed |
|----|---------|-----------------|
| **H1** | Dev viewer secret shipped to browser bundle | `resolveScope.ts` returns `ANON_SCOPE` when no `VITE_DEV_VIEWER_SECRET` — prod builds are always anonymous |
| **H2** | Generic exception handler leaked `str(exc)` | `generic_exception_handler` now returns `"Internal error"` |
| **H3** | Drive-time prefilter used trail centroid, not trailhead | Engine passes `coord_of=lambda c: _latlon(c.trailhead_point) or _latlon(c.point)` |
| **H4** | NWS alerts `None` treated as "no alerts" | Curator `_alerts()` returns `None` for failed alerts, distinguishing from `[]` |
| **AH1** | SSRF via Valhalla `follow_redirects=True` | Valhalla adapter passes `follow_redirects=False` explicitly |
| **AH2** | Rate limiter bypass via X-Forwarded-For | `real_client_ip()` reads the rightmost X-Forwarded-For entry |
| **AH3** | `k=50` unbounded API spend | `k` capped at `le=20` in `PlanRequest` |
| **AH4** | `viewer_id` unvalidated free text | `VIEWER_ID_PATTERN = r"^[A-Za-z0-9_:-]{1,64}$"` enforced |
| **AM1** | TTLCache not thread-safe | `threading.Lock` guards all `_store`/`stats` access |
| **AM2** | Background queue no error handling | `_drain_queue_bg` wraps in try/except with correlation-ID logging |
| **AM4** | Path traversal via `region_id` | `load_region()` rejects `/`, `\\`, and `..` |
| **AL2** | `canonical_id` unvalidated | `CANONICAL_ID_PATTERN` enforced via `Path(pattern=...)` |
| **AL3** | `delta_answer` unbounded | `max_length=2000` enforced |

### Still Open (from prior review)

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| **AM5** | Medium | `drive_speed_kmh` accepts non-finite values (`inf`, `NaN`) | `float(e.get("DRIVE_SPEED_KMH", "60.0"))` still has no `math.isfinite()` check |
| **AL5** | Low | No lockfile — `pyproject.toml` has lower bounds only | Still no `requirements.txt` lockfile; `pip-audit` is advisory only in CI |
| **AM3** | Low | Commons re-identification risk on sparse trail+band+month | Design note for future; no API read path exposes `:CommonsObservation` |
| **L1** | Info | `granted_ids` scope parameter always empty | Unused feature; safe today, flag for future validation if populated |
| **L3** | Info | Belief corroboration recount lacks explicit `owner_scope('b')` | Implicitly safe (`belief_id` embeds owner); defense-in-depth note |
| **L4** | Info | `assert_scoped_write` is regex-based | Acceptable — all Cypher is authored in `graph.queries`, never user-supplied |

---

## New Findings (not in prior review)

### NF1. `episode_id` path parameter has no validation — PII in URL paths

**Severity:** Medium
**File:** `api/app.py:1034-1043`
**Seam:** API edge / input validation / privacy

The `/episode/{episode_id}/outcome` endpoint accepts `episode_id` as a raw path parameter with no `Path(pattern=...)` constraint, unlike `canonical_id` which has `CANONICAL_ID_PATTERN`. The `episode_id` embeds the owner_id by construction (`ep:{owner_id}:{watch_activity_id}` per `ingestion/ingest_episode.py`), so it is **PII**.

**Issues:**
- No format validation — arbitrary characters accepted
- No length limit — memory bloat / log bloat vector
- Appears in URL path → access logs, browser history, CDN logs, proxy logs all carry the raw owner_id
- Inconsistent with `canonical_id` which IS validated

The `scrub_episode()` function exists for application logs, but the raw `episode_id` in the URL path bypasses it — access logs at the proxy/CDN layer capture the unredacted value.

**Recommendation:** Add `episode_id: str = Path(pattern=r"^[A-Za-z0-9_:-]{1,128}$")` matching the `episode_id` format. Consider moving `episode_id` to the request body to keep it out of URL paths entirely.

---

### NF2. `delta_question` field has no max_length

**Severity:** Low
**File:** `api/schemas.py:233`
**Seam:** Input validation / data injection

`OutcomeBody.delta_question` is `str | None = None` with no `max_length`, unlike its sibling `delta_answer` which has `max_length=2000`. It is stored verbatim in the graph via `upsert_outcome` (`o.delta_question = $delta_q`). An attacker could store an unbounded string, causing graph storage bloat.

**Recommendation:** Add `max_length=500` (a question string is naturally short).

---

### NF3. `query` field in `PlanRequest` has no max_length

**Severity:** Low–Medium
**File:** `api/schemas.py:22-24`
**Seam:** Input validation / LLM prompt injection / token budget

`PlanRequest.query` is free text with no length limit. It flows through `parse_intent` into the LLM prompt and is also stored in the feed cache key. An extremely long query:
- Exhausts LLM token budgets (the mechanical-tier model call)
- Bloats the feed cache key (a tuple including the raw query string)
- Is a prompt injection surface — unbounded user text assembled into LLM context

The `context_assembly.py` module caps personal context at `MAX_CONTEXT_CHARS = 500`, but the raw `query` itself is uncapped before it reaches the model.

**Recommendation:** Add `max_length=500` to `PlanRequest.query`. A natural-language hiking request is well under 100 chars; 500 is ample headroom.

---

### NF4. NWS `forecast_url` second-order SSRF

**Severity:** Low
**File:** `orchestration/adapters/nws.py:49-61`
**Seam:** SSRF

The NWS adapter fetches `forecast_url = props.get("forecast")` — a URL returned by the NWS API response — and passes it to `_http.get_json()` with the default `follow_redirects=True`. If the NWS API response were manipulated (DNS poisoning, BGP hijacking, compromised CDN, or a crafted response from a lookalike domain), the `forecast_url` could point to an internal address like `http://169.254.169.254/`.

The NWS adapter uses `_http.build_client()` which defaults to `follow_redirects=True` (the Valhalla adapter correctly passes `follow_redirects=False`, but NWS does not).

**Risk assessment:** Low — `api.weather.gov` is a trusted government API, and the `lat`/`lon` inputs are Pydantic-validated. But it's a latent SSRF vector if any adapter URL becomes configurable or if a trusted API is compromised.

**Recommendation:** Validate that `forecast_url` starts with `https://api.weather.gov/` before fetching it. Or pass `follow_redirects=False` to the NWS client (NWS's 301/302s are to the same domain, so the first hop is sufficient if the full URL is in the response).

---

### NF5. Multiple config float values lack `math.isfinite()` validation

**Severity:** Low
**File:** `orchestration/config.py:245-274`
**Seam:** Input validation

Several config values are parsed with raw `float()` / `int()` with no finiteness or range checks:

- `drive_speed_kmh=float(e.get("DRIVE_SPEED_KMH", "60.0"))` — `inf` yields a zero-second budget; `NaN` is accepted (prior finding AM5, still open)
- `elev_resolution_m=float(e.get("ADVENTURE_3DEP_RESOLUTION_M", "20.0"))` — negative or zero could cause division issues
- `warmup_deadline_s=float(e.get("ADVENTURE_WARMUP_DEADLINE_S", "30.0"))` — negative breaks the warm-up loop
- `feed_cache_ttl_s`, `feed_warm_interval_s` — negative values have undefined behavior

**Recommendation:** Add a `_finite_positive(name, raw, default)` helper in `Settings.from_env()` that validates `math.isfinite(value) and value > 0` and falls back to the default (or raises) on failure.

---

### NF6. `overall` field lacks Pydantic-level constraints

**Severity:** Informational
**File:** `api/schemas.py:229-232`
**Seam:** Input validation

`OutcomeBody.overall` is `int | None` with no `ge`/`le` constraints at the Pydantic schema level. Validation is done in `OutcomeRequest.__post_init__` which raises `ValueError` → 422. This is functionally safe (the validation is enforced before any write), but it's inconsistent with the rest of the schema which uses Pydantic field constraints. A request with `overall=42` gets a 422 but the error message is less clear than a Pydantic validation error.

**Recommendation:** Add `ge=1, le=3` to the `overall` field for defense-in-depth and clearer error messages.

---

### NF7. Dependabot pip ecosystem has no lockfile to update

**Severity:** Low
**File:** `.github/dependabot.yml`, `pyproject.toml`
**Seam:** Supply chain

Dependabot is configured for the `pip` ecosystem with `directory: "/"`, but there is no lockfile (`requirements.txt`, `poetry.lock`, `Pipfile.lock`). Without a lockfile, Dependabot can only propose updates to the direct dependencies in `pyproject.toml` (the `>=` lower bounds), not to transitive dependencies. This means a compromised transitive package would not be detected by Dependabot.

The `pip-audit` CI job is advisory (`continue-on-error: true`), so known vulnerabilities in unpinned transitive deps don't block CI.

**Recommendation:** Generate a lockfile with `pip-compile` (or `uv lock`) and commit it. Update the Dependabot config to point at the lockfile. Move `pip-audit` from advisory to blocking once the lockfile exists.

---

### NF8. Single uvicorn worker — rate limiter is per-process

**Severity:** Informational
**File:** `Dockerfile:63`
**Seam:** DoS / rate limiting

The Dockerfile CMD runs `uvicorn` with no `--workers` flag (single worker). This is intentional for the free tier ("keeps the lifespan-built graph-client singleton simple"), and it means the in-process rate limiter store is correct for the current deploy. But if the app scales to multiple workers, the in-process rate limiter (`slowapi` with default memory store) would under-count — each worker gets its own bucket.

**Recommendation:** Document that horizontal scaling requires a shared rate-limit store (Redis). The code comment in `ratelimit.py` already notes this; add a note to the deploy runbook.

---

## Prioritized Mitigation Plan

### Priority 1 — Quick wins, high impact (do now)

| # | Finding | Effort | Change |
|---|---------|--------|--------|
| 1 | **NF1** — `episode_id` no validation | 1 line | Add `Path(pattern=r"^[A-Za-z0-9_:-]{1,128}$")` to `record_outcome` |
| 2 | **NF3** — `query` no max_length | 1 line | Add `max_length=500` to `PlanRequest.query` |
| 3 | **NF2** — `delta_question` no max_length | 1 line | Add `max_length=500` to `OutcomeBody.delta_question` |
| 4 | **NF6** — `overall` no Pydantic constraints | 1 line | Add `ge=1, le=3` to `OutcomeBody.overall` |
| 5 | **AM5/NF5** — config float validation | ~10 lines | Add `_finite_positive()` helper in `Settings.from_env()` |

**Total effort:** ~15 lines of code, all in `api/schemas.py` and `orchestration/config.py`. All changes are additive constraints — no behavior change for valid inputs.

### Priority 2 — Defense-in-depth (do soon)

| # | Finding | Effort | Change |
|---|---------|--------|--------|
| 6 | **NF4** — NWS `forecast_url` SSRF | ~3 lines | Validate `forecast_url.startswith("https://api.weather.gov/")` before fetch |
| 7 | **AL5/NF7** — lockfile | 1 command | `pip-compile --all-extras > requirements.lock` + commit; update Dependabot + `pip-audit` to blocking |

### Priority 3 — Architectural / future (track for Stage 8)

| # | Finding | Effort | Change |
|---|---------|--------|--------|
| 8 | **H1 residual** — dev secret auth model | Stage 8 | Replace shared dev secret with real OAuth/session auth |
| 9 | **AM2 residual** — background queue durability | Medium | Add persistent dead-letter table or retry mechanism for belief updates |
| 10 | **AM3** — commons re-identification | Future | Monitor `:CommonsObservation` read paths; consider graph-level access control |
| 11 | **NF8** — rate limiter scaling | Ops | Document Redis requirement for multi-worker deploy |

---

## Attack Surface Map

```
Internet
  │
  ▼
Render Edge Proxy (X-Forwarded-For)
  │
  ▼
uvicorn (--proxy-headers --forwarded-allow-ips='*')
  │
  ▼
FastAPI app (api/app.py)
  ├── CORS middleware (default-deny, exact origins) ✅
  ├── Rate limiter (slowapi, rightmost XFF keying) ✅
  ├── Exception handler (generic "Internal error") ✅
  │
  ├── /health, /status, /regions  (anonymous, read-only)
  ├── /plan                       (auth: dev secret or anonymous)
  ├── /trail/{id}                 (auth: dev secret or anonymous)
  ├── /trail/{id}/export.gpx      (auth: dev secret or anonymous)
  └── /episode/{id}/outcome       (auth: dev secret, graph WRITE)
       │
       ▼
  ScopedSession (graph/client.py)
  ├── assert_scoped_write() — regex guard on owned labels ✅
  ├── $viewer_id / $granted_ids merged into all params ✅
  └── All Cypher parameterized (no injection) ✅
       │
       ▼
  Neo4j (Aura, neo4j+s:// strict TLS)
       │
       ▼
  Live adapters (orchestration/adapters/)
  ├── NWS, AirNow, FIRMS, RIDB, USGS — hardcoded URLs ✅
  ├── Valhalla — config URL, follow_redirects=False ✅
  └── NWS forecast_url — second-order SSRF (NF4) ⚠️
       │
       ▼
  LLM providers (orchestration/providers/)
  ├── Local-first (Ollama/vLLM) for private overlay ✅
  └── Anthropic for cloud yardstick (non-private) ✅
```

---

## What's Working Well (confirmed in this review)

- **Parameterized Cypher everywhere** — no string interpolation in any query; `assert_scoped_write` is defense-in-depth on top
- **Owner-scoped access control** — every owned-label read/write carries `owner_scope(var)` or `owner_id = $viewer_id`; MERGE keys include `owner_id` structurally
- **Secrets handling** — all secrets from env vars, `repr=False` on all secret fields, `.env` gitignored and confirmed untracked, gitleaks CI is blocking
- **CORS** — default-deny, exact origins, never wildcard
- **Rate limiting** — conservative per-IP limits, spoof-resistant keying via rightmost XFF
- **Error handling** — generic exception handler returns `"Internal error"`, route handlers catch and map to typed errors
- **Log hygiene** — `scrub_viewer` / `scrub_episode` digest identifiers; optional salt for confirmability resistance
- **Commons fork de-id** — HMAC with keyed salt, endpoint trimming, bucketed quasi-identifiers, no API read path to `:CommonsObservation`
- **Privacy routing for LLM** — personal context forced to local model; cloud judge only sees anonymous free-text
- **GPX export** — XML escaping via `saxutils.escape`, filename slug sanitization, world-data-only (no personal substrate)
- **Thread safety** — `TTLCache` and `FeedCache` both use `threading.Lock` with network calls outside the lock
- **Docker** — runs as unprivileged user (uid 10001), minimal image, ca-certificates for TLS
- **CI security** — bandit (blocking, medium+), gitleaks (blocking, full history), pip-audit (advisory), actionlint
- **Input validation** — `viewer_id` pattern, `canonical_id` pattern, `k` bounded, `lat`/`lon` ranged, `delta_answer` length-capped

---

## Verification Commands

```bash
# Confirm .env is not tracked
git ls-files --error-unmatch .env  # should fail

# Run the existing security CI locally
bandit -r api graph ingestion orchestration evals scripts --severity-level medium
pip-audit --skip-editable  # advisory

# Run the full test suite
make check

# Verify no hardcoded secrets
grep -rn "password\|secret\|api_key\|token" --include="*.py" api/ graph/ orchestration/ | grep -v "test\|example\|env\|config\|repr=False\|#\|docstring\|log\."
```
