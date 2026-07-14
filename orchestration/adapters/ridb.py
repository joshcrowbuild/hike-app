"""Recreation.gov RIDB adapter — nearby facilities / permit requirements (API key).

The official RIDB facilities lookup (the corpus-ish *requirement* side). Live
permit/campsite *availability* is a separate, unofficial endpoint (Stage 1 /
Stage 4 §5) — risk-flagged and added later, not here. TTL: hours. Source-or-
silence: failure / empty -> None.
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

SOURCE = "Recreation.gov RIDB"
URL = "https://ridb.recreation.gov/api/v1/facilities"


def fetch(
    lat: float,
    lon: float,
    api_key: str,
    *,
    radius_miles: int = 25,
    limit: int = 10,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> VerifiedFact | None:
    c = client or _http.build_client(headers={"apikey": api_key})
    doc = _http.get_json(
        c, URL, params={"latitude": lat, "longitude": lon, "radius": radius_miles, "limit": limit}
    )
    records = doc.get("RECDATA") if isinstance(doc, dict) else None
    if not records:
        return None

    facilities = [
        {
            "id": r.get("FacilityID"),
            "name": r.get("FacilityName"),
            "reservable": r.get("Reservable"),
        }
        for r in records
        if isinstance(r, dict)
    ]
    return VerifiedFact(
        value={"facilities": facilities, "count": len(facilities)},
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        # source_kind "primary" (CDP-06 retune): Recreation.gov RIDB is the single
        # federal system of record for these facilities — a designated institutional
        # origin, not an unverified aggregate.
        confidence_inputs={
            "authority": "tier1_gov",
            "freshness": "slow",
            "source_kind": "primary",
        },
        disclosures=(
            "Live permit/campsite availability uses a separate unofficial endpoint; not included.",
        ),
    )


class RidbAdapter(LiveAdapter):
    """Nearby facilities / permit requirements via Recreation.gov RIDB (API key)."""

    name = "ridb"
    kind = ConditionKind.permits
    # Facility / permit-requirement data is near-static (rules and nearby facilities
    # change on the order of days, not hours), so a 1-day window is right and spends the
    # keyed RIDB quota once per day per locale (CDP-08 "permits days").
    ttl_seconds = 86400  # ~1 day — permits window (CDP-08)

    def __init__(self, api_key: str, *, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client

    def _client_or_build(self) -> httpx.Client:
        return self._client or _http.build_client(headers={"apikey": self._api_key})

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(
            needs_point=True,
            needs_site_id=False,
            is_keyless=False,
            supports_region=frozenset({"US"}),
        )

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        return fetch(point.lat, point.lon, self._api_key, client=self._client)

    def health(self) -> AdapterHealth:
        status = _http.probe_status(
            self._client_or_build(),
            URL,
            params={"latitude": 38.5, "longitude": -78.4, "radius": 25, "limit": 1},
        )
        return health_from_status(status)

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls(settings.ridb_api_key) if settings.ridb_api_key else None
