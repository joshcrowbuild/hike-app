"""Verifier tests — probe wiring from config + source-or-silence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import VerifiedFact
from orchestration.config import Settings
from orchestration.verifier import build_probes, verify


def _fact(value: Any) -> VerifiedFact:
    return VerifiedFact(value=value, source="test", fetched_at=datetime.now(timezone.utc))


def test_build_probes_includes_only_configured_sources() -> None:
    s = Settings.from_env({"NWS_USER_AGENT": "ua", "AIRNOW_API_KEY": "k"})
    probes = build_probes(s)
    # usgs is keyless (always on); fire/permits unconfigured -> absent (no fabrication)
    assert set(probes) == {"water", "weather", "air"}


def test_verify_drops_silent_probes() -> None:
    probes = {
        "weather": lambda lat, lon: _fact({"short_forecast": "Sunny"}),
        "air": lambda lat, lon: None,  # source-or-silence: contributes nothing
    }
    facts = verify(38.5, -78.4, probes)
    assert set(facts) == {"weather"}
    assert facts["weather"].value["short_forecast"] == "Sunny"
