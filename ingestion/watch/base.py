"""Device-seam base types — the normalized contract (device-integration-seam.md §2-3).

Sibling of `orchestration/providers/base.py`. One normalized contract, N vendor
adapters behind it. The downloaded FIT file is the normalization point: every
adapter yields FIT bytes, so the existing `parse_fit` consumes any device
identically. Vendor-specific auth/transport lives entirely inside each adapter.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

log = logging.getLogger(__name__)


class AdapterHealth(Enum):
    """Uniform health signal so re-auth prompts and backoff are handled the same
    way for every vendor (device-integration-seam.md §2)."""

    OK = "ok"
    NEEDS_REAUTH = "needs_reauth"
    RATE_LIMITED = "rate_limited"
    DOWN = "down"


@dataclass(frozen=True)
class Capabilities:
    """What a device can provide. Drives per-device degrade-and-disclose: a vendor
    without a readiness API → the readiness filter is simply *absent* for that user,
    not broken (rule #6)."""

    has_fit: bool
    has_readiness: bool
    has_activity_title: bool


@dataclass(frozen=True)
class ActivityRef:
    """Lightweight activity list item. `id` is namespaced (`"<vendor>:<id>"`,
    Stage 6 §2.2) so Episode MERGE keys never collide across vendors."""

    id: str
    source: str
    title: str | None = None
    start_time: datetime | None = None
    sport: str | None = None

    def __post_init__(self) -> None:
        # Make the namespacing guarantee STRUCTURAL (fail loudly at the boundary):
        # a colon-less id would produce a cross-vendor-collidable episode_id.
        prefix = self.id.split(":", 1)[0] if ":" in self.id else ""
        if not prefix:
            raise ValueError(f"ActivityRef id must be namespaced '<vendor>:<id>', got {self.id!r}")


@dataclass(frozen=True)
class RawActivity:
    """An ActivityRef plus its downloaded FIT bytes — the normalization point."""

    ref: ActivityRef
    fit_bytes: bytes

    @property
    def id(self) -> str:
        """Namespaced id (delegates to ref) — what create_episode keys on."""
        return self.ref.id


@dataclass(frozen=True)
class ReadinessSignal:
    """JIT readiness reading (Body Battery / recovery). NEVER persisted as a belief
    (Stage 6 §5.3 / S5-9). Feeds the readiness filter (Epic 007)."""

    value: float
    kind: str  # "body_battery" | "recovery" | ...
    source: str
    fetched_at: datetime


class DeviceAdapter(ABC):
    """One adapter per vendor. Every method that can fail at the network boundary
    degrades to a signal, not an exception that escapes the adapter (rule #6).
    Secrets come only from the secrets manager (rule #10), never the repo.
    Construction is lazy — `__init__` never makes a network call (AC-1.5)."""

    name: str  # "garmin" | "coros" | ... — set by each subclass

    @abstractmethod
    def capabilities(self) -> Capabilities:
        """Static declaration of what this device provides."""
        raise NotImplementedError

    @abstractmethod
    def list_activities(
        self,
        since: datetime | None,
        *,
        sport: str = "hiking",
        limit: int = 20,
    ) -> list[ActivityRef]:
        """Recent activities, newest-first, namespaced ids."""
        raise NotImplementedError

    @abstractmethod
    def download_fit(self, ref: ActivityRef) -> bytes:
        """Raw FIT bytes for an activity. Raises if `capabilities().has_fit` is False."""
        raise NotImplementedError

    @abstractmethod
    def fetch_readiness(self, *, at: datetime | None = None) -> ReadinessSignal | None:
        """Current readiness, or None when `capabilities().has_readiness` is False."""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> AdapterHealth:
        """Uniform health state — never raises."""
        raise NotImplementedError

    def fetch_new_activities(self, since: datetime | None) -> list[RawActivity]:
        """Default: list activities, download each to FIT bytes (preserves the
        Stage 6 §2.1 interface name). A vendor without FIT capability yields nothing
        (degrade-and-disclose); a single failed download is skipped, not fatal."""
        if not self.capabilities().has_fit:
            log.warning("%s has no FIT capability; no activities ingested", self.name)
            return []
        out: list[RawActivity] = []
        for ref in self.list_activities(since):
            try:
                fit = self.download_fit(ref)
            except Exception as exc:  # one bad download must not lose the batch
                log.warning("%s: FIT download failed for %s: %s", self.name, ref.id, exc)
                continue
            out.append(RawActivity(ref=ref, fit_bytes=fit))
        return out
