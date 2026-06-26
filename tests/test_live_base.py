"""Epic 013 S1 — the LiveAdapter contract + behavioral types.

Pins the shape of the seam: the ABC's four methods, the value types, and the
unchanged VerifiedFact. No network.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
    health_from_status,
)

# ── AC-1.2 — Point value type ──


def test_s1_ac2_point_roundtrips() -> None:
    p = Point(lat=38.5, lon=-78.4)
    assert (p.lat, p.lon) == (38.5, -78.4)
    assert p == Point(38.5, -78.4)  # value equality
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.lat = 0.0  # type: ignore[misc]


# ── AC-1.3 — ConditionKind membership ──


def test_s1_ac3_condition_kind_members() -> None:
    assert {k.value for k in ConditionKind} == {
        "weather",
        "air",
        "fire",
        "water",
        "permits",
        "drive_time",
    }


# ── AC-1.4 — AdapterHealth values (value-equal to the watch seam) ──


def test_s1_ac4_adapter_health_values() -> None:
    assert {m.value for m in AdapterHealth} == {"ok", "needs_reauth", "rate_limited", "down"}


# ── AC-1.5 — LiveCapabilities shape, distinct from the device seam ──


def test_s1_ac5_live_capabilities_shape_and_distinct() -> None:
    caps = LiveCapabilities(
        needs_point=True, needs_site_id=False, is_keyless=True, supports_region=frozenset({"US"})
    )
    assert caps.needs_point and not caps.needs_site_id and caps.is_keyless
    assert caps.supports_region == frozenset({"US"})
    # Region-agnostic default.
    assert LiveCapabilities(True, False, True).supports_region == frozenset()
    # Deliberately NOT the watch seam's Capabilities (no shared symbol).
    from ingestion.watch.base import Capabilities as WatchCapabilities

    assert LiveCapabilities is not WatchCapabilities


# ── AC-1.6 — VerifiedFact unchanged ──


def test_s1_ac6_verified_fact_fields_unchanged() -> None:
    fields = {f.name for f in dataclasses.fields(VerifiedFact)}
    assert fields == {"value", "source", "fetched_at", "confidence_inputs", "disclosures"}


# ── AC-1.1 / AC-1.7 — the ABC contract + enforcement ──


def test_s1_ac1_ac7_abc_enforces_all_methods() -> None:
    # A subclass omitting an abstract method cannot be instantiated.
    class Incomplete(LiveAdapter):
        name = "incomplete"
        kind = ConditionKind.weather

        def capabilities(self) -> LiveCapabilities:
            return LiveCapabilities(True, False, True)

        # probe / health / from_config omitted

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_s1_ac7_probe_accepts_point_and_when() -> None:
    class Ok(LiveAdapter):
        name = "ok"
        kind = ConditionKind.weather

        def capabilities(self) -> LiveCapabilities:
            return LiveCapabilities(True, False, True)

        def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
            return VerifiedFact(
                value={"echo": (point.lat, point.lon, when)},
                source="ok",
                fetched_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
            )

        def health(self) -> AdapterHealth:
            return AdapterHealth.OK

        @classmethod
        def from_config(cls, settings: object) -> "LiveAdapter | None":
            return cls()

    a = Ok()
    assert a.probe(Point(1.0, 2.0)) is not None  # when defaults to None
    when = datetime(2026, 6, 25, tzinfo=timezone.utc)
    fact = a.probe(Point(1.0, 2.0), when)
    assert fact is not None and fact.value == {"echo": (1.0, 2.0, when)}


# ── health classification (shared helper used by every adapter's health()) ──


def test_health_from_status_mapping() -> None:
    assert health_from_status(200) is AdapterHealth.OK
    assert health_from_status(204) is AdapterHealth.OK
    assert health_from_status(401) is AdapterHealth.NEEDS_REAUTH
    assert health_from_status(403) is AdapterHealth.NEEDS_REAUTH
    assert health_from_status(429) is AdapterHealth.RATE_LIMITED
    assert health_from_status(500) is AdapterHealth.DOWN
    assert health_from_status(None) is AdapterHealth.DOWN
