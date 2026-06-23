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

import httpx

from . import _http
from .base import VerifiedFact

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
    return VerifiedFact(
        value={"hotspot_count": len(rows), "dataset": dataset, "window_days": days},
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "near_real_time"},
        disclosures=("A FIRMS hotspot is a thermal anomaly, not a confirmed fire.",),
    )
