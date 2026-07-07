# Epic 034 — NPS closures live adapter (`ConditionKind.closures`)

**Status:** DONE ✅
**Phase:** 1 (live-conditions seam — Epic 013 family)
**Spec refs:** discovery sweep #1 (`/Users/joshcrow/.hike-lanes/oss-sprint/research/discovery.md` lines 17–22, 95–99) · Epic 013 (LiveAdapter seam) · CLAUDE.md rules #1/#3/#7 · CDP-01 (corroboration locus)

---

## Capability statement
The feed can, for the first time, surface **"this place is CLOSED / in danger"** — the biggest live gap left after weather/air/fire/water/permits — by probing the National Park Service Data API for the nearest NPS unit's active **Closure** and **Danger** alerts, park-scoped and disclosed, source-or-silence (no park / no alert → nothing, never a fabricated "open").

## Architectural context
**Builds on:** the Epic 013 `LiveAdapter` seam — `orchestration/adapters/base.py` (`LiveAdapter` ABC, `VerifiedFact`, `Point`, `LiveCapabilities`, `ConditionKind`, `health_from_status`), the kind-keyed `orchestration/adapters/registry.py` (`ADAPTER_FACTORIES`, `probes_for`, `TTLCache`), the shared HTTP helper `orchestration/adapters/_http.py` (degrade-to-None), and the config self-drop pattern in `orchestration/config.py`. Mirrors `orchestration/adapters/ridb.py` most closely (header-API-key + point-in → `VerifiedFact | None`).

**Enables:** a real closures/hazard axis on the card; the second closures provider later (USFS/EDW — discovery #9 — folds under this same `ConditionKind.closures` as a fallback adapter, no new kind).

**Does NOT include:**
- **No USFS/EDW closures** (discovery #9 — fragmented per-forest ArcGIS layers, no clean keyed API; a *second* adapter under this same kind, later).
- **No `avalanche`/`snow` kind** (discovery #5 — alpine-region-gated; our live corpus is mid-Atlantic).
- **No frontend work** beyond the disclosure the card already renders for any live `FeedLine` (the generic `summarize_fact` path). No new curator warning/block wiring (`orchestration/curator.py` is **out of scope** — see Open Questions).
- **No corroboration wiring.** Live facts are pinned at corroboration=1 by the engine and `_corpus_corroboration` feeds only from corpus `SAME_AS` — closures is correct-by-construction and must **not** touch that path (`orchestration/engine.py` unchanged).
- **No persistence.** JIT-fetched, held only in the registry TTL cache, never a graph node (rule #3).

---

## Invariant guards (must hold — restated from the brief)
1. **Source-or-silence (rule #1):** `probe()` returns `None` when there is no nearest park in range, no alert of the relevant categories, or any transport failure. It must **never** synthesize "open" / "no closures" as a positive fact.
2. **Disclose granularity (rules #1/#7):** the fact is **park-scoped**, not trail-scoped. Every fact carries a disclosure saying so; nothing may imply a specific trail is open or closed.
3. **JIT, never persisted (rule #3):** no graph writes; the registry `TTLCache` is the only cache.
4. **No corroboration path (CDP-01):** do not route closures into `_corpus_corroboration`; the engine already pins live facts at corroboration=1. A closures `FeedLine.sources` is a 1-tuple like every other live kind.
5. **Self-drop on missing key (SS-10):** `from_config` returns `None` when `NPS_API_KEY` is absent — an absent probe, never a fabricated one.
6. **Secrets never in repo / never in logs (rule #10):** the key comes from `settings.nps_api_key` (env only), passed as an HTTP **header** (not the URL path), so `_http._safe_url` logging never sees it.

## License / attribution
NPS Data API = **US Government work → public-domain DATA via an api-service**. No code is ported (api-service class), so **no third-party source header is required**. Honor the per-key rate limit and attribute the source in the `VerifiedFact.source` label (`"NPS api.nps.gov"`). Reference sample code (`nationalparkservice/nps-api-samples`, public-domain/US-gov) may be read for the request shape but nothing is copied.

## API facts (verified 2026-07-07 against developer.nps.gov docs + `nationalparkservice/nps-api-samples`)
- **Base:** `https://developer.nps.gov/api/v1/`
- **Auth:** API key via HTTP header. NPS documents the `X-Api-Key` header (the official python sample uses an `Authorization` header; the `api_key` query param also works). **Use a header, never the URL path** (rule #10). **Default to the `X-Api-Key` header and ship it.** The mocked tests use `httpx.MockTransport`, which ignores auth entirely, so a live `curl` is an OPTIONAL manual dev check — **do NOT treat inability to `curl` (no real key in this environment) or the absence of a live `200` as a blocker.** A wrong header degrades to source-or-silence (the fact simply never appears), and that failure mode is disclosed as Open Question 3.
- **`GET /alerts`** params: `parkCode` (comma-separated), `stateCode`, `q`, `limit`, `start`, `fields`. **No lat/lon/radius filter** (this is the design gap vs. RIDB). Each alert object: `id`, `title`, `description`, `category` ∈ {`Danger`, `Closure`, `Caution`, `Information`}, `url`, `parkCode`, `lastIndexedDate`.
- **`GET /parks`** returns units with `fullName`, `parkCode`, `states`, `url`, and `latLong` — a **string** formatted `"lat:38.916554, long:-77.025977"` (may be empty for some units; skip those). No radius query, so "nearest park" = fetch the parks list once (`limit=500`) and pick the nearest centroid by haversine.
- **Rate limit:** per-key hourly cap (NPS default commonly 1000/h); `429` on exceed → `health()` returns `RATE_LIMITED` via the shared `health_from_status`.

---

## Stories

### S1 — Add `ConditionKind.closures`

**Given** the live seam enumerates conditions in `orchestration/adapters/base.py:54` (`ConditionKind`, members `weather|air|fire|water|permits|drive_time` at lines 60–65)
**When** a closures source is added
**Then** the enum carries a `closures` member and every kind-enumerating test is updated.

**AC-1.1:** `orchestration/adapters/base.py` `ConditionKind` gains `closures = "closures"` (added alongside `permits`; `drive_time` stays the origin-relative special-case).
**AC-1.2:** `tests/test_live_base.py::test_s1_ac3_condition_kind_members` (line 38, the hard-coded member set) is updated to include `"closures"` and passes.
**AC-1.3:** No other member is renamed/removed; `AdapterHealth`, `LiveCapabilities`, `Point`, `VerifiedFact` are unchanged.

### S2 — `NpsAlertsAdapter` (point → nearest park → closure/danger alerts)

**Given** the `LiveAdapter` contract and the `ridb.py` header-key template
**When** `probe(point)` runs
**Then** it resolves the nearest NPS unit, fetches that unit's alerts, keeps only `Closure`/`Danger`, and returns a stamped park-scoped `VerifiedFact` or `None`.

**AC-2.1:** New file `orchestration/adapters/nps_alerts.py` defines `class NpsAlertsAdapter(LiveAdapter)` with `name = "nps_alerts"`, `kind = ConditionKind.closures`, and a `ttl_seconds` in the 1-hour range (e.g. `3600`) with a rationale comment (closures change on hour/day scale, faster than permits' 1-day window, slower than minute-scale).
**AC-2.2:** `capabilities()` returns `LiveCapabilities(needs_point=True, needs_site_id=False, is_keyless=False, supports_region=frozenset({"US"}))`.
**AC-2.3:** `probe(point, when=None)` performs, via the injected `httpx.Client` and `_http.get_json`:
  (a) a `GET /parks?limit=500` (key in header), parses each unit's `latLong` string (`"lat:<f>, long:<f>"`), computes haversine distance to `point`, and selects the nearest unit **within a radius cap** (a module constant, e.g. `RADIUS_MILES = 50`); units with empty/unparseable `latLong` are skipped;
  (b) if no unit is within the cap → returns `None` (source-or-silence);
  (c) a `GET /alerts?parkCode=<nearest_code>` (key in header), filters `category ∈ {"Closure", "Danger"}`;
  (d) if the filtered list is empty → returns `None` (never fabricate "open");
  (e) otherwise returns `VerifiedFact(value={"park": <fullName>, "park_code": <code>, "alerts": [{"title","category","url"} …], "count": n}, source="NPS api.nps.gov", fetched_at=now, confidence_inputs={"authority": "tier1_gov", "freshness": "live"}, disclosures=("Park-level scope — the nearest NPS unit to this point, not trail-specific.",))`.
**AC-2.4:** `probe` **never raises past the boundary** on any transport failure (non-200, connection error, unparseable body) — it returns `None` (the `_http` helper degrades; the adapter treats a `None` from either sub-call as silence).
**AC-2.5:** The API key is passed as an HTTP header (via `_http.build_client(headers=…)`), never in the URL path or query string, so it never reaches `_http`'s logging (rule #10).
**AC-2.6:** `health()` issues a lightweight `_http.probe_status` to a fixed NPS URL and maps via `health_from_status` (401/403→`NEEDS_REAUTH`, 429→`RATE_LIMITED`, 2xx/3xx→`OK`, else→`DOWN`); it never raises.
**AC-2.7:** `from_config(settings)` returns `cls(settings.nps_api_key)` when the key is set, else `None` (SS-10 self-drop) — mirroring `RidbAdapter.from_config`.

### S3 — Config key `NPS_API_KEY`

**Given** the `Settings` dataclass and `from_env` in `orchestration/config.py`
**When** `NPS_API_KEY` is set (or not)
**Then** it is read into settings with `repr=False` (secret hygiene) and defaults to `None`.

**AC-3.1:** `Settings` gains `nps_api_key: str | None = field(repr=False, default=None)` grouped with the other live-source credentials (near `ridb_api_key`, config.py line 82).
**AC-3.2:** `Settings.from_env` sets `nps_api_key=e.get("NPS_API_KEY") or None` (near the `ridb_api_key` line, ~209).
**AC-3.3:** `.env.example` enumerates the live keys (`NWS_USER_AGENT`/`AIRNOW_API_KEY`/`FIRMS_MAP_KEY`/`RIDB_API_KEY` at lines 66–72, verified), so add an empty `NPS_API_KEY=` entry with a one-line comment (`# NPS Data API — closures/danger alerts; free key from developer.nps.gov`) grouped with them.

### S4 — Registry + config-list wiring

**Given** the kind-keyed registry in `orchestration/adapters/registry.py`
**When** `"nps_alerts"` is named in `ADVENTURE_LIVE_ADAPTERS`
**Then** the registry instantiates it (dropping it silently when the key is absent) and groups it under `ConditionKind.closures`.

**AC-4.1:** `orchestration/adapters/registry.py` imports `NpsAlertsAdapter` and adds `"nps_alerts": NpsAlertsAdapter` to `ADAPTER_FACTORIES` (line 42 dict).
**AC-4.2:** A test builds `Settings.from_env({"ADVENTURE_LIVE_ADAPTERS": "nps_alerts", "NPS_API_KEY": "k"})` and asserts `registry.probes_for("US", s)[ConditionKind.closures]` contains the adapter; and that with `NPS_API_KEY` unset the adapter self-drops (absent from the grouping).
**AC-4.3:** `.env.example` (line 79, `ADVENTURE_LIVE_ADAPTERS=`) and any deploy note that enumerates adapter names list `nps_alerts` as an available name (e.g. in the adjacent comment listing known adapters).

### S5 — Present-layer render (`closures` body + origin)

**Given** the templated presentation in `orchestration/present.py`
**When** a closures `VerifiedFact` is summarized
**Then** it renders a legible, sourced line with an honest single-source note.

**AC-5.1:** `orchestration/present.py::_body` (line 62) gains a `kind == "closures"` branch rendering e.g. `f"{value.get('count', 0)} NPS closure/danger alert(s) — {value.get('park', 'nearest park')}"`.
**AC-5.2:** `orchestration/present.py::_origin` (line 92) gains a `closures` branch returning `f"NPS {value.get('park_code')}"` when a `park_code` is present, else `""` — so `_source_note` reads `single authoritative source (NPS SHEN)`.
**AC-5.3:** A closures `FeedLine` reports `sources` as a 1-tuple (single live source — the corroboration invariant holds without touching the corpus path).

### S6 — Conformance + adapter tests

**Given** the shared conformance suite and a new adapter test file
**When** the suite runs
**Then** the new adapter satisfies the same boundary contract as every other adapter.

**AC-6.1:** New `tests/test_nps_alerts.py` covers, with `httpx.MockTransport` routing `/parks` and `/alerts` (no live calls): (a) happy path → a stamped `VerifiedFact` with `source == "NPS api.nps.gov"`, `count ≥ 1`, and the park-scope disclosure present; (b) no park within `RADIUS_MILES` → `None`; (c) alerts present but all `Caution`/`Information` → `None`; (d) empty alerts → `None`; (e) a non-200 or `ConnectError` on either sub-call → `None`, never raises; (f) `health()` maps 401→`NEEDS_REAUTH`, 429→`RATE_LIMITED`, 503→`DOWN`, connection-error→`DOWN`; (g) `from_config` returns `None` with no key and an adapter with a key; (h) only `Closure`/`Danger` alerts survive into `value["alerts"]`.
**AC-6.2:** `tests/test_live_conformance.py` `ADAPTERS` list (~line 90) gains an `("nps_alerts", lambda c: NpsAlertsAdapter("key", client=c), _nps_alerts_ok)` entry with a handler routing `/parks` (one unit at the test point) and `/alerts` (one `Closure`), so the parametrized S6 AC-6.1/6.2/6.3 contract tests cover it; and `test_s6_ac5_all_builtin_adapters_registered` includes `"nps_alerts"`.
**AC-6.3:** A present-layer test (in `tests/test_present_edgecases.py` or `tests/test_nps_alerts.py`) asserts the `closures` `_body` branch renders the count + park and does not fall through to `str(value)`.
**AC-6.4:** `make check` is green (ruff format check + ruff + mypy + pytest).

---

## Definition of Done
- [ ] All ACs covered by at least one passing test
- [ ] `make check` green
- [ ] Targeted self-review agent run; every CRITICAL fixed, MODERATE+ documented
- [ ] Epic copied into `docs/epics/` + index row added (status `REVIEW` at PR-open); `scripts/gen_epic_index.py` run to sync status cells
- [ ] Committed and pushed on `claude/nps-closures-adapter`; PR "Epic 034: NPS closures live adapter — FOR REVIEW"

## Open questions (surface in the PR, do not silently resolve)
1. **"Nearest park" is centroid-crude.** A park centroid can be far from a trailhead inside a large unit, and dense metro areas (e.g. DC) have many co-located units — nearest-centroid may pick the wrong one. Mitigation shipped: a radius cap → `None` when nothing is close, plus the park-scope disclosure. Follow-up (not this epic): point-in-boundary using the `/parks` `boundary` GeoJSON, or a region→parkCode map keyed off `settings.region`.
2. **Curator warning surfacing.** A `Closure`/`Danger` alert is safety-relevant and could warrant a `CardWarning`/`BlockReason` in `orchestration/curator.py::evaluate_guardrails` (as weather alerts / AQI do). Deliberately **out of scope** here (curator.py untouched) — the card already renders the live `FeedLine`. Flag as a fast follow so a reviewer decides whether closures should escalate to a prominent card warning.
3. **Auth header form.** `X-Api-Key` vs. `Authorization` vs. `api_key` query param — we ship `X-Api-Key` (the documented default); the mocked tests do not exercise auth, and a wrong header degrades to source-or-silence rather than an error. An operator should confirm it empirically against a live `200` when a real key is provisioned. The spec requires only that the key travels in a header, not the URL.
4. **Parks-list refetch cost.** The required design fetches `/parks?limit=500` on every cache-miss probe (two HTTP calls per miss). The registry `TTLCache` dedupes repeat probes for the same rounded point. An optional module-level parks-reference cache (long TTL — the list is near-static) would cut this to one `/alerts` call per miss; left optional to keep the required path simple and thread-safe.
