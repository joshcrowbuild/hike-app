# Epic 004 — Device-Integration Seam (Garmin + Coros, pluggable)

**Status:** DEFINED
**Phase:** 1 (Personal Intelligence)
**Spec refs:** `docs/research/device-integration-seam.md` · Stage 6 §1–2 · Stage 4 §2 (seam pattern) · decision-log §29

> **Rescopes the former "Garmin Connect poller" Epic 004.** Watch integration becomes a config-driven device-provider seam (sibling of the model-provider seam), so Garmin, Coros, and future manufacturers are drop-in. On adoption: update the index row for 004 and remove the redundant `epic-004-garmin-connect-poller.md` if wave-1 produced it.

---

## Capability statement

The system syncs hiking activities from **any configured smart-device vendor** (Garmin and Coros at launch) through one normalized adapter contract — so adding a new manufacturer is a single adapter file plus a config line, with zero change to FIT parsing, Episode creation, belief updates, or the commons fork.

## Architectural context

**Builds on:** `ingestion/ingest_episode.py` (`parse_fit`, `create_episode`, belief-queue wiring — Epic 001), the model-provider seam pattern in `orchestration/providers/` (mirror it), Stage 5 schema.

**Enables:** Epic 007 (readiness filter — becomes device-agnostic via `fetch_readiness` + `Capabilities`), same-day sync once an always-on host exists (S6-12), the commons pace data for any vendor.

**Does NOT include:** the always-on poller host (deferred — S6-12; Phase-1 syncs on machine wake / manual trigger); automated party proximity detection (S6-5); a Garmin **MCP** server (deferred — interactive only); heat_response (Epic-001 scope note).

---

## Stories

### S1 — Adapter contract, canonical models, and registry

**Given** the device-seam package `ingestion/watch/`
**When** the contract and registry are defined
**Then** a `DeviceAdapter` ABC plus canonical `ActivityRef` / `RawActivity` / `ReadinessSignal` / `Capabilities` / `AdapterHealth` types exist, and a config-driven registry resolves the enabled adapters

**AC-1.1:** `DeviceAdapter` declares `name`, `capabilities()`, `list_activities(since, *, sport, limit)`, `download_fit(ref)`, `fetch_readiness(*, at)`, `health()`, and a default `fetch_new_activities(since)` implemented in terms of `list_activities` + `download_fit`.
**AC-1.2:** `RawActivity` carries `fit_bytes` and a namespaced `id` (`"<vendor>:<id>"`); `ActivityRef` ids are namespaced by source (Stage 6 §2.2).
**AC-1.3:** `registry.enabled_adapters(settings)` returns the adapters named in `ADVENTURE_WATCH_ADAPTERS` (env); an unknown name raises `ValueError` (fail loudly at the boundary).
**AC-1.4:** `Settings.from_env` exposes `ADVENTURE_WATCH_ADAPTERS` (default empty → no devices, pipeline still runs — rule #6).
**AC-1.5:** No adapter is constructed unless named in config; constructing an adapter never makes a network call (lazy, like the provider adapters).

### S2 — Garmin adapter

**Given** `ADVENTURE_WATCH_ADAPTERS` includes `garmin` and Garmin credentials in the secrets manager
**When** the Garmin adapter runs
**Then** it implements the full contract over `python-garminconnect`/`garth`, with secrets read only from the environment (rule #10)

**AC-2.1:** `GarminAdapter.list_activities` returns `ActivityRef`s with `id = "garmin:<activity_id>"`, filtered to hiking, newest-first.
**AC-2.2:** `download_fit` returns raw FIT bytes (unzipping the download-service ZIP).
**AC-2.3:** `capabilities()` reports `has_fit=True, has_readiness=True` (Body Battery), `has_activity_title=True`.
**AC-2.4:** On a 401/session-expiry, `health()` returns `needs_reauth` (no crash); credentials are read from `GARMIN_EMAIL`/`GARMIN_PASSWORD`, never hardcoded.
**AC-2.5:** Tests drive the adapter with a mocked `garth`/library client — no live Garmin call in the test suite.

### S3 — Coros adapter

**Given** `ADVENTURE_WATCH_ADAPTERS` includes `coros` and Coros OAuth credentials in the secrets manager
**When** the Coros adapter runs in the **batch** path
**Then** it implements the full contract over the **direct `open.coros.com` HTTP API (OAuth2 PKCE)** — not the MCP server (S6-3)

**AC-3.1:** `CorosAdapter.list_activities` returns `ActivityRef`s with `id = "coros:<activity_id>"`, hiking, newest-first.
**AC-3.2:** `download_fit` returns raw FIT bytes from the Coros download endpoint.
**AC-3.3:** `capabilities()` reports `has_fit=True, has_readiness=True` (recovery), `has_activity_title=…` per the API.
**AC-3.4:** Batch ingestion uses HTTP, not MCP; credentials from `COROS_CLIENT_ID`/`COROS_CLIENT_SECRET`.
**AC-3.5:** Tests drive the adapter with mocked HTTP responses — no live Coros call.

### S4 — Poller over enabled adapters, feeding the existing pipeline

**Given** one or more enabled adapters
**When** `scripts/watch_sync.py` runs
**Then** it iterates the enabled adapters, normalizes each activity to FIT bytes, and hands them to the **existing** `parse_fit` → `create_episode` → belief-queue path — with per-adapter failure isolation and idempotency

**AC-4.1:** Each adapter runs in its own try/except; an exception or `down`/`needs_reauth` from one adapter is logged and **does not stop the others** (rule #6).
**AC-4.2:** `since` is the most-recent `Episode.created_at` for the owner (bounds the API window).
**AC-4.3:** Re-running the poller with no new activities is a structural no-op (MERGE on `(watch_activity_id, owner_id)`; only `updated_at` changes).
**AC-4.4:** The poller reuses the existing parse → Episode → belief → commons path; `create_episode` is parameterized by `source` (`"garmin"`/`"coros"`/…) and made strictly idempotent (`ON CREATE` vs `ON MATCH`), but **no new** FIT-parse, belief, or commons logic is added — downstream stays device-agnostic. (Absorbs the wave-1 Garmin-epic review finding: `create_episode` currently hardcodes `source='fit_file'` and lacks the ON-CREATE/ON-MATCH split — the minimal change, not a rewrite.)
**AC-4.5:** All LLM calls in this path route to the local provider via sensitivity routing, enforced at the poller entrypoint (S6-9).

### S5 — Conformance suite + drop-in guarantee

**Given** the adapter contract
**When** a new adapter is added
**Then** a shared conformance test fixture verifies any adapter satisfies the contract, and a one-page "add a manufacturer" guide documents the closed checklist (device-integration-seam.md §6)

**AC-5.1:** A parametrized conformance test runs against every registered adapter (using its mocked client) and asserts: namespaced ids, FIT bytes from `download_fit`, `capabilities()` shape, `health()` returns a valid state, `fetch_readiness` returns `None` when `has_readiness=False`.
**AC-5.2:** Adding a third (stub) adapter to the test registry and the conformance params requires **no change** to parse/Episode/belief/poller code — asserted by the test existing and passing with only the new adapter file.
**AC-5.3:** `docs/research/device-integration-seam.md` §6 checklist is referenced from the adapter package docstring.

---

## Definition of Done
- [ ] All ACs covered by at least one passing test (mocked clients — no live device calls)
- [ ] `make check` green (ruff + mypy + pytest)
- [ ] Targeted review agent run; CRITICALs fixed (focus: rule #6 isolation, rule #10 secrets, sensitivity routing, idempotency, no vendor-awareness leaking downstream)
- [ ] `epics/README.md` index row 004 updated to the seam scope; redundant `epic-004-garmin-connect-poller.md` removed if present
- [ ] Committed and pushed
