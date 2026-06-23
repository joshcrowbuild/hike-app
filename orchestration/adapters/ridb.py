"""Recreation.gov RIDB adapter — nearby facilities / permit requirements (API key).

The official RIDB facilities lookup (the corpus-ish *requirement* side). Live
permit/campsite *availability* is a separate, unofficial endpoint (Stage 1 /
Stage 4 §5) — risk-flagged and added later, not here. TTL: hours. Source-or-
silence: failure / empty -> None.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from . import _http
from .base import VerifiedFact

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
        confidence_inputs={"authority": "tier1_gov", "freshness": "slow"},
        disclosures=(
            "Live permit/campsite availability uses a separate unofficial endpoint; not included.",
        ),
    )
