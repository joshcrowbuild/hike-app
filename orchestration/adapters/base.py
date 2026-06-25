"""Live-data adapters — the LiveAdapter seam (Stage 4 Verifier tools; Epic 013).

Every live source implements one `LiveAdapter` contract and is resolved from a
config-driven registry keyed by `ConditionKind` (so a condition can have redundant
providers, with `health()`-driven primary→fallback). Source-or-silence (rule #1) is
structural: `probe()` returns a `VerifiedFact` stamped with its source + timestamp,
or `None` — a failed adapter contributes nothing, so the engine can never surface an
unsourced fact. Live readings are held in the registry's short-TTL cache and never
persisted as graph nodes (rule #3).

`VerifiedFact` is the proven normalization point (rules #1/#6) and is kept unchanged
and reused by name as the probe return. The behavioral types (`ConditionKind`,
`LiveCapabilities`, `AdapterHealth`, `Point`) are added around it — `LiveCapabilities`
is deliberately distinct from `ingestion/watch/base.py::Capabilities` (differently
shaped) to avoid a same-named/differently-shaped house-style hazard.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestration.config import Settings


@dataclass(frozen=True)
class VerifiedFact:
    value: object
    source: str  # e.g. "NWS api.weather.gov"
    fetched_at: datetime
    # Inputs to the computed-on-read confidence score (freshness / authority /
    # corroboration) — confidence never penalizes ranking (rule #2).
    confidence_inputs: dict[str, object] = field(default_factory=dict)
    # Disclosures travel with the fact (e.g. nearest-gauge distance; FIRMS
    # "thermal anomaly != confirmed fire"; AirNow "preliminary").
    disclosures: tuple[str, ...] = ()


@dataclass(frozen=True)
class Point:
    """A WGS84 coordinate — the uniform probe input. Replaces the positional,
    untyped `(lat, lon)` floats the in-tree code passed before Epic 013."""

    lat: float
    lon: float


class ConditionKind(Enum):
    """The live-condition a probe answers. The registry is keyed by this, so a kind
    can be backed by ordered primary→fallback adapters (closing C6's "weather == NWS,
    no swap path"). `drive_time` is origin-relative and handled in ranking/pre-filter,
    not the per-point guardrail loop (Epic 005 / SS-9)."""

    weather = "weather"
    air = "air"
    fire = "fire"
    water = "water"
    permits = "permits"
    drive_time = "drive_time"


class AdapterHealth(Enum):
    """Uniform health signal so backoff and fallback-to-secondary are handled the same
    way for every adapter. Value-equal to `ingestion/watch/base.py::AdapterHealth` for
    cross-seam consistency (a deliberate mirror, not a shared symbol)."""

    OK = "ok"
    NEEDS_REAUTH = "needs_reauth"
    RATE_LIMITED = "rate_limited"
    DOWN = "down"


@dataclass(frozen=True)
class LiveCapabilities:
    """What a live adapter needs/covers. Drives per-region probe selection (a US-only
    feed isn't selected outside the US) and degrade-and-disclose at selection time
    (rule #6). Distinct from the device seam's `Capabilities` (has_fit/has_readiness)."""

    needs_point: bool
    needs_site_id: bool
    is_keyless: bool
    # Region codes the source has authority over (e.g. {"US"}). Empty set = region-
    # agnostic (e.g. drive_time), always selected.
    supports_region: frozenset[str] = frozenset()


def health_from_status(status: int | None) -> AdapterHealth:
    """Classify an HTTP status into the uniform health signal: 401/403 → needs_reauth,
    429 → rate_limited, 2xx/3xx → ok, everything else (incl. None / connection error)
    → down. Shared so every adapter's `health()` maps transport state identically."""
    if status is None:
        return AdapterHealth.DOWN
    if status in (401, 403):
        return AdapterHealth.NEEDS_REAUTH
    if status == 429:
        return AdapterHealth.RATE_LIMITED
    if 200 <= status < 400:
        return AdapterHealth.OK
    return AdapterHealth.DOWN


class LiveAdapter(ABC):
    """One adapter per live source. Source-or-silence (rule #1) and degrade-and-
    disclose (rule #6) are the boundary contract: `probe()` returns a stamped
    `VerifiedFact` or `None`, and never raises past the adapter on a transport
    failure. Per-source auth/transport (NWS `user_agent`, AirNow/FIRMS/RIDB `api_key`,
    keyless USGS) lives entirely inside `from_config` + the instance, so the call site
    is uniform `adapter.probe(point)`. Secrets come only from the secrets store
    (rule #10), never the repo."""

    name: str  # "nws" | "airnow" | ... — set by each subclass
    kind: ConditionKind  # the condition this adapter answers
    ttl_seconds: int = 600  # per-source cache TTL (M3); overridden per adapter

    @abstractmethod
    def capabilities(self) -> LiveCapabilities:
        """Static declaration of what this adapter needs and where it has authority."""
        raise NotImplementedError

    @abstractmethod
    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        """Fetch the condition at `point` (optionally for a forecast/historical `when`).
        Returns a stamped `VerifiedFact`, or `None` on any failure (source-or-silence).
        Never raises past the boundary on a transport error (rule #1/#6)."""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> AdapterHealth:
        """Uniform health state — never raises. Drives registry primary→fallback."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        """Build from config, pulling the adapter's own credential. Returns `None`
        when the credential is absent — that source is simply not selected (a missing
        key = absent probe, never a fabricated reading), the deliberate `| None`
        self-drop asymmetry with the corpus seam (SS-10)."""
        raise NotImplementedError
