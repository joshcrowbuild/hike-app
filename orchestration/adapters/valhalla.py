"""Valhalla adapter — drive time/distance from an origin to a trailhead.

Self-hosted Valhalla (base_url from config). One-to-one `sources_to_targets`
matrix with auto costing. Source-or-silence: failure -> None.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from . import _http
from .base import VerifiedFact

SOURCE = "Valhalla (self-hosted)"


def fetch(
    origin: tuple[float, float],
    trailhead: tuple[float, float],
    base_url: str,
    *,
    costing: str = "auto",
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> VerifiedFact | None:
    c = client or _http.build_client(headers={"Content-Type": "application/json"})
    body = {
        "sources": [{"lat": origin[0], "lon": origin[1]}],
        "targets": [{"lat": trailhead[0], "lon": trailhead[1]}],
        "costing": costing,
    }
    doc = _http.post_json(c, base_url.rstrip("/") + "/sources_to_targets", body)
    matrix = doc.get("sources_to_targets") if isinstance(doc, dict) else None
    if not matrix or not matrix[0]:
        return None
    cell = matrix[0][0]
    if not isinstance(cell, dict) or cell.get("time") is None:
        return None

    return VerifiedFact(
        value={"drive_seconds": cell.get("time"), "distance_km": cell.get("distance")},
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={"authority": "derived", "freshness": "live"},
    )
