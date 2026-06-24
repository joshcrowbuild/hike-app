# Device-Integration Seam (design)

*Refines Stage 6 (watch integration) into a formal, pluggable seam. Draft v0.1 — June 24, 2026. Supersedes the Garmin-only framing of Epic 004.*

> **Status: DESIGN.** Specifies a config-driven **device-provider seam** so smart-device support (Garmin, Coros, and future manufacturers) is modular: a new manufacturer is one adapter with zero downstream change. Mirrors the model-provider seam (Stage 4 §2 / Decision Log §29). Honors rules #6, #7, #9, #10.

> **Why now (the gap):** Stage 6 §2.1 gestures at an adapter interface (`fetch_new_activities`) but never formalizes it, and `ingestion/ingest_episode.py` is a single FIT-file path. Garmin (fragile community SSO lib) and Coros (official OAuth2 / MCP) interface in completely different ways — exactly the case a seam exists for. We want to be able to add Suunto / Polar / Wahoo / Apple Health / Strava-as-aggregator later as a drop-in.

---

## 1. The principle — a second provider-agnostic seam

The project already has one swappable seam (models: `extract`/`normalize`/`judge` → local-or-cloud adapter). Devices get the **same shape**: one normalized contract, N vendor adapters behind it, selected by config. Architectural consistency — *the mechanism a vendor uses (community lib vs. official OAuth vs. MCP) is the adapter's private business; everything downstream sees one normalized output.*

```
 Garmin (garminconnect SSO) ─┐
 Coros  (open.coros.com OAuth)─┤→ DeviceAdapter contract → RawActivity (FIT bytes)
 Suunto / Polar / … (future) ─┘        (registry, config-driven)        │
                                                                        ▼
                              the EXISTING pipeline, unchanged:  parse_fit → Episode → belief queue → commons fork
```

**The win:** adding a manufacturer touches *one new file* and a config line. FIT parsing, Episode creation, belief updates, the commons fork, and the poller are all device-agnostic and never change (§6).

---

## 2. Canonical types (the normalized contract)

Lives in `ingestion/watch/base.py` (sibling of `orchestration/providers/base.py`):

- **`ActivityRef`** — lightweight list item: `id` (namespaced, e.g. `"garmin:12345"` / `"coros:abc"` — Stage 6 §2.2), `source`, `title | None`, `start_time`, `sport | None`.
- **`RawActivity`** — `ActivityRef` + `fit_bytes: bytes`. The downloaded FIT is the **normalization point**: every adapter yields FIT, so the existing `parse_fit` consumes any device identically.
- **`ReadinessSignal`** — `value`, `kind` (`"body_battery"` | `"recovery"` | …), `source`, `fetched_at`. **JIT only, never persisted** (Stage 6 §5.3 / S5-9). Feeds the readiness filter (Epic 007).
- **`Capabilities`** — booleans (`has_fit`, `has_readiness`, `has_activity_title`). Drives **per-device degrade-and-disclose**: a vendor without a readiness API → the readiness filter is simply *absent* for that user, not broken.
- **`AdapterHealth`** — `ok` | `needs_reauth` | `rate_limited` | `down`. Uniform signaling so re-auth prompts and backoff are handled the same way for every vendor.

## 3. The adapter contract

```
class DeviceAdapter(ABC):
    name: str                                            # "garmin" | "coros" | ...
    def capabilities(self) -> Capabilities: ...
    def list_activities(self, since, *, sport="hiking", limit=20) -> list[ActivityRef]: ...
    def download_fit(self, ref: ActivityRef) -> bytes: ...                  # raises if !has_fit
    def fetch_readiness(self, *, at=None) -> ReadinessSignal | None: ...    # None if !has_readiness
    def health(self) -> AdapterHealth: ...
    # default, in terms of the above — preserves Stage 6 §2.1's interface name:
    def fetch_new_activities(self, since) -> list[RawActivity]: ...
```

Every method that can fail at the network boundary **degrades to a signal, not an exception that escapes the adapter** (rule #6, source-or-silence's watch-side analog). Secrets come only from the secrets manager (rule #10); never the repo.

## 4. The registry (config-driven, like the model seam)

`ingestion/watch/registry.py`, mirroring `orchestration/providers/registry.py`:

- `ADVENTURE_WATCH_ADAPTERS=garmin,coros` in `.env` → the registry instantiates the enabled adapters from config (each adapter pulls its own secrets).
- `enabled_adapters(settings) -> list[DeviceAdapter]`. Unknown name → `ValueError` (fail loudly at the boundary).
- This is the single place that knows which vendors exist; everything else iterates the list.

## 5. Per-vendor adapters (mechanism hidden behind the contract)

| Adapter | Mechanism | Readiness | Notes |
|---|---|---|---|
| **`GarminAdapter`** | `python-garminconnect` / `garth` SSO (unofficial, fragile) | Body Battery | `health()` → `needs_reauth` on 401 (Stage 6 §1.1); kept swappable for a future Garmin Health API (S6-2) |
| **`CorosAdapter`** | **direct `open.coros.com` HTTP, OAuth2 PKCE** for batch | recovery score | Coros MCP is reserved for *interactive* queries only (S6-3 / §5) — **not** used in the batch poller |

Both implement the identical contract; their wildly different auth/transport lives entirely inside the adapter. (Detailed endpoints, rate limits, and auth flows are in Stage 6 §1.1–1.2 — unchanged; this seam just wraps them.)

## 6. Downstream is unchanged (the modularity proof)

The poller `scripts/watch_sync.py`:
1. `for adapter in enabled_adapters(settings):` — **each in its own try/except so one vendor down never stops the others** (rule #6).
2. `adapter.fetch_new_activities(since)` → `RawActivity` list (since = most-recent `Episode.created_at` per owner).
3. Hand each `fit_bytes` to the **existing** `parse_fit` → `create_episode` (MERGE on namespaced `watch_activity_id`, idempotent) → belief queue → commons fork.

Nothing in parse/Episode/belief/commons is vendor-aware. The commons FIT fork (Stage 6 §6.2) is device-agnostic because it operates on FIT, not on a vendor shape.

**Adding a new manufacturer = a closed checklist:**
1. Implement `DeviceAdapter` (the 5 methods) in `ingestion/watch/<vendor>.py`.
2. Declare its `Capabilities` (degrade-and-disclose falls out automatically).
3. Register it; add `<vendor>` to `ADVENTURE_WATCH_ADAPTERS`.
4. Put its secrets in the secrets manager.
5. Run it through the shared adapter **conformance test suite**.
→ Zero edits to FIT parsing, Episode, belief, commons, or the poller.

## 7. Privacy / sensitivity (unchanged, now uniform)
All watch data is the most-sensitive private-overlay class. Every LLM call in this path routes to the **local** provider via sensitivity routing (Stage 6 §6.1 / S6-9), enforced at the poller entrypoint for *all* adapters. Per-adapter secrets never enter the repo or a cloud model.

## 8. Decisions

| # | Decision | Status |
|---|---|---|
| DV-1 | Watch integration is a **config-driven device-provider seam** mirroring the model seam; new manufacturer = one adapter + one config line, zero downstream change | ✅ |
| DV-2 | Adapters normalize to **FIT bytes** → the existing `parse_fit`/Episode pipeline (downstream is device-agnostic) | ✅ |
| DV-3 | Garmin = community-lib adapter (fragile, swappable); Coros = direct OAuth HTTP for **batch**, MCP for **interactive only** (S6-3) | ✅ |
| DV-4 | `Capabilities` flags drive per-device degrade-and-disclose (missing readiness API → filter absent, not broken) | ✅ |
| DV-5 | Per-adapter failure isolation in the poller (one vendor down ≠ pipeline down) — rule #6 | ✅ |
| DV-6 | All adapter secrets from the secrets manager; all LLM in this path local (sensitivity routing) | ✅ |
| DV-7 | Epic 004 is rescoped from "Garmin poller" to "device seam + Garmin & Coros adapters"; Epic 007 (readiness) then becomes device-agnostic via `fetch_readiness` + `Capabilities` | 🔶 confirm renumbering with the build session |

## 9. Build
This is built as **Epic 004 (rescoped)** — see `docs/epics/epic-004-device-integration-seam.md`. It supersedes the Garmin-only Epic 004; Epic 007 (readiness filter) consumes `fetch_readiness`/`Capabilities` from this seam.
