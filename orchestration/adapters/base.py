"""Live-data adapters — base types (Stage 4 Verifier tools).

Each adapter is a pure function `(location) -> VerifiedFact | None`. Source-or-
silence (rule #1) is enforced *here in code*, not by a model: an adapter either
returns a fact stamped with its source + timestamp, or returns None. The engine
never surfaces an unsourced fact as stated. Live readings are held in a short-TTL
cache and never persisted as graph nodes (rule #3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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
