"""Verifier edge cases — probe wiring, empty sets, and source-or-silence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import VerifiedFact
from orchestration.config import Settings
from orchestration.verifier import build_probes, verify


def _fact(value: Any) -> VerifiedFact:
    return VerifiedFact(value=value, source="test", fetched_at=datetime.now(timezone.utc))


def test_build_probes_with_all_credentials_present() -> None:
    s = Settings.from_env(
        {
            "NWS_USER_AGENT": "ua",
            "AIRNOW_API_KEY": "air",
            "FIRMS_MAP_KEY": "firms",
            "RIDB_API_KEY": "ridb",
        }
    )
    probes = build_probes(s)
    assert set(probes) == {"water", "weather", "air", "fire", "permits"}


def test_build_probes_no_credentials_only_water() -> None:
    s = Settings.from_env({})
    probes = build_probes(s)
    assert set(probes) == {"water"}


def test_build_probes_does_not_include_unconfigured_sources() -> None:
    s = Settings.from_env({"NWS_USER_AGENT": "ua"})
    probes = build_probes(s)
    assert set(probes) == {"water", "weather"}
    assert "air" not in probes
    assert "fire" not in probes


def test_verify_empty_probe_map_returns_empty() -> None:
    assert verify(0.0, 0.0, {}) == {}


def test_verify_all_probes_silent_returns_empty() -> None:
    probes = {"a": lambda lat, lon: None, "b": lambda lat, lon: None}
    assert verify(0.0, 0.0, probes) == {}


def test_verify_keeps_only_non_none_results() -> None:
    probes = {
        "weather": lambda lat, lon: _fact({"temp": 60}),
        "air": lambda lat, lon: None,
        "fire": lambda lat, lon: _fact({"count": 0}),
    }
    facts = verify(38.5, -78.4, probes)
    assert set(facts) == {"weather", "fire"}
    assert facts["weather"].value == {"temp": 60}
    assert facts["fire"].value == {"count": 0}


def test_verify_passes_lat_lon_to_probes() -> None:
    seen: list[tuple[float, float]] = []

    def probe(lat: float, lon: float) -> VerifiedFact | None:
        seen.append((lat, lon))
        return _fact({"ok": True})

    verify(1.23, 4.56, {"x": probe})
    assert seen == [(1.23, 4.56)]


def test_verify_preserves_probe_key_names() -> None:
    probes = {"custom-key": lambda lat, lon: _fact({"x": 1})}
    facts = verify(0.0, 0.0, probes)
    assert "custom-key" in facts


def test_build_probes_returns_callable_probes() -> None:
    s = Settings.from_env({"NWS_USER_AGENT": "ua"})
    probes = build_probes(s)
    for kind, probe in probes.items():
        assert callable(probe)
        assert isinstance(kind, str)
