"""Epic 004 S1 — config-driven registry + Settings.from_env exposure."""

from __future__ import annotations

import pytest

from ingestion.watch.registry import ADAPTER_REGISTRY, enabled_adapters
from orchestration.config import Settings

# ── AC-1.4 — Settings exposes ADVENTURE_WATCH_ADAPTERS ────────────────────────


def test_s1_ac4_settings_default_empty():
    s = Settings.from_env({})
    assert s.watch_adapters == ()


def test_s1_ac4_settings_parses_comma_list():
    s = Settings.from_env({"ADVENTURE_WATCH_ADAPTERS": "garmin, coros"})
    assert s.watch_adapters == ("garmin", "coros")


def test_s1_ac4_empty_config_means_no_devices():
    s = Settings.from_env({})
    assert enabled_adapters(s) == []


# ── AC-1.3 — registry resolution + unknown name ───────────────────────────────


def test_s1_ac3_unknown_adapter_raises_valueerror():
    s = Settings.from_env({"ADVENTURE_WATCH_ADAPTERS": "suunto"})
    with pytest.raises(ValueError, match="suunto"):
        enabled_adapters(s)


def test_s1_ac3_known_adapters_instantiate():
    s = Settings.from_env(
        {
            "ADVENTURE_WATCH_ADAPTERS": "garmin,coros",
            "GARMIN_EMAIL": "a@b.c",
            "GARMIN_PASSWORD": "pw",
            "COROS_CLIENT_ID": "cid",
            "COROS_CLIENT_SECRET": "sec",
        }
    )
    adapters = enabled_adapters(s)
    assert [a.name for a in adapters] == ["garmin", "coros"]


def test_registry_has_garmin_and_coros():
    assert set(ADAPTER_REGISTRY) >= {"garmin", "coros"}


# ── AC-1.5 — construction is lazy, no network call ────────────────────────────


def test_s1_ac5_construction_makes_no_network_call():
    # Build with missing secrets — must NOT raise at construction time (lazy).
    s = Settings.from_env({"ADVENTURE_WATCH_ADAPTERS": "garmin,coros"})
    adapters = enabled_adapters(s)  # no GARMIN_*/COROS_* set — still constructs
    assert len(adapters) == 2
    # Secrets only matter when a real call is attempted (not here).
