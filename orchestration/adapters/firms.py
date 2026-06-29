"""NASA FIRMS adapter — active-fire hotspots near a point (MAP_KEY required).

Area CSV API over a small bbox around the point. A hotspot is a *thermal anomaly*,
not a confirmed fire (Stage 1) — disclosed. TTL ~10 min. Source-or-silence: a
failed call -> None; a successful call with zero detections -> a fact with
hotspot_count 0 (absence of fire is itself verified information, not silence).
"""

from __future__ import annotations

import csv
import io
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

SOURCE = "NASA FIRMS"
URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{dataset}/{bbox}/{days}"


def fetch(
    lat: float,
    lon: float,
    map_key: str,
    *,
    dataset: str = "VIIRS_SNPP_NRT",
    radius_deg: float = 0.5,
    days: int = 1,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> VerifiedFact | None:
    c = client or _http.build_client()
    bbox = f"{lon - radius_deg},{lat - radius_deg},{lon + radius_deg},{lat + radius_deg}"
    text = _http.get_text(c, URL.format(key=map_key, dataset=dataset, bbox=bbox, days=days))
    if text is None:
        return None

    rows = list(csv.DictReader(io.StringIO(text)))
    # Origin-at-boundary (CDP-03 / spike item 3): each detection names its satellite/
    # sensor (MODIS Aqua/Terra vs VIIRS Suomi-NPP/NOAA-20). Capturing the distinct
    # satellites — not just the requested `dataset` — preserves the genuine independence
    # signal: two detections from *different* satellites corroborate; two from the same
    # pass do not. The column is absent on some product schemas → empty list, never a lie.
    satellites = sorted({s for r in rows if (s := (r.get("satellite") or "").strip())})
    return VerifiedFact(
        value={
            "hotspot_count": len(rows),
            "dataset": dataset,
            "window_days": days,
            "satellites": satellites,
        },
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "near_real_time"},
        disclosures=("A FIRMS hotspot is a thermal anomaly, not a confirmed fire.",),
    )


class FirmsAdapter(LiveAdapter):
    """Active-fire hotspots via NASA FIRMS (MAP_KEY required). US-only (capability-gated)."""

    name = "firms"
    kind = ConditionKind.fire
    ttl_seconds = 600  # ~10 min (Stage 4 §4)

    def __init__(self, map_key: str, *, client: httpx.Client | None = None) -> None:
        self._map_key = map_key
        self._client = client

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(
            needs_point=True,
            needs_site_id=False,
            is_keyless=False,
            supports_region=frozenset({"US"}),
        )

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        return fetch(point.lat, point.lon, self._map_key, client=self._client)

    def health(self) -> AdapterHealth:
        client = self._client or _http.build_client()
        url = URL.format(
            key=self._map_key, dataset="VIIRS_SNPP_NRT", bbox="-78.9,38.0,-77.9,39.0", days=1
        )
        return health_from_status(_http.probe_status(client, url))

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls(settings.firms_map_key) if settings.firms_map_key else None
