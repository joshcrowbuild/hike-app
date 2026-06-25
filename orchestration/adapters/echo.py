"""Echo adapter — the in-repo proof-of-swap (Epic 013 S6).

A throwaway adapter that exists only to prove the modularity claim empirically: added
as one file + one registry-factory entry, with no edit to `verify()`'s or
`probes_for()`'s loop bodies, it is selected by the registry and passes the shared
conformance suite. It stands in for the not-yet-decided weather fallback (SS-11), so
the seam ships the swap mechanism without prematurely committing to a third-party
provider. Not a production source — `from_config` always returns an instance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from . import _http
from .base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
    health_from_status,
)

if TYPE_CHECKING:
    from orchestration.config import Settings

SOURCE = "EchoAdapter (proof-of-swap)"
DEFAULT_URL = "https://echo.invalid/"


class EchoAdapter(LiveAdapter):
    name = "echo"
    kind = ConditionKind.weather  # a redundant weather provider — the swap C6 says is impossible
    ttl_seconds = 60

    def __init__(self, base_url: str = DEFAULT_URL, *, client: httpx.Client | None = None) -> None:
        self._base_url = base_url
        self._client = client

    def _client_or_build(self) -> httpx.Client:
        return self._client or _http.build_client()

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(
            needs_point=True,
            needs_site_id=False,
            is_keyless=True,
            supports_region=frozenset({"US"}),
        )

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        doc = _http.get_json(
            self._client_or_build(), self._base_url, params={"lat": point.lat, "lon": point.lon}
        )
        if doc is None:
            return None  # source-or-silence
        return VerifiedFact(
            value={"echo": doc, "short_forecast": "echo"},
            source=SOURCE,
            fetched_at=when or datetime.now(timezone.utc),
            confidence_inputs={"authority": "derived", "freshness": "live"},
            disclosures=("Echo adapter is a proof-of-swap stand-in, not authoritative.",),
        )

    def health(self) -> AdapterHealth:
        return health_from_status(_http.probe_status(self._client_or_build(), self._base_url))

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls()  # throwaway proof — always available
