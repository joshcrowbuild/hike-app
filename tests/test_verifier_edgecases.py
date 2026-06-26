"""Verifier edge cases — kind-keyed failover, drive_time skip, source-or-silence.

Rewritten for the Epic-013 reshape: `build_probes` is gone (its credential-gating
now lives in `adapters/registry.py`, covered by `test_live_registry.py`), and
`verify` takes a `Point` + a `{ConditionKind: [LiveAdapter]}` map with health-driven
primary→fallback. These tests pin the keep-only-what-returned (rule #1) contract and
the failover/skip logic against a duck-typed fake adapter (verify never isinstance-checks).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
)
from orchestration.verifier import verify

if TYPE_CHECKING:
    from orchestration.config import Settings


def _fact(value: object) -> VerifiedFact:
    return VerifiedFact(value=value, source="test", fetched_at=datetime.now(timezone.utc))


class FakeAdapter(LiveAdapter):
    """Minimal real LiveAdapter for verify() tests — only health()/probe() are exercised."""

    name = "fake"
    kind = ConditionKind.weather

    def __init__(
        self, *, fact: VerifiedFact | None = None, health: AdapterHealth = AdapterHealth.OK
    ) -> None:
        self._fact = fact
        self._health = health
        self.health_calls = 0
        self.probe_points: list[Point] = []

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(
            needs_point=True,
            needs_site_id=False,
            is_keyless=True,
            supports_region=frozenset({"US"}),
        )

    def health(self) -> AdapterHealth:
        self.health_calls += 1
        return self._health

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        self.probe_points.append(point)
        return self._fact

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls()  # unused by verify(); present only to satisfy the contract


def test_verify_empty_probe_map_returns_empty() -> None:
    assert verify(Point(0.0, 0.0), {}) == {}


def test_verify_all_silent_returns_empty() -> None:
    # Every adapter returns None → source-or-silence (rule #1): nothing surfaces.
    probes: dict[ConditionKind, list[LiveAdapter]] = {
        ConditionKind.weather: [FakeAdapter(fact=None)],
        ConditionKind.air: [FakeAdapter(fact=None)],
    }
    assert verify(Point(0.0, 0.0), probes) == {}


def test_verify_keeps_only_returning_kinds() -> None:
    probes: dict[ConditionKind, list[LiveAdapter]] = {
        ConditionKind.weather: [FakeAdapter(fact=_fact({"temp": 60}))],
        ConditionKind.air: [FakeAdapter(fact=None)],
        ConditionKind.fire: [FakeAdapter(fact=_fact({"count": 0}))],
    }
    facts = verify(Point(38.5, -78.4), probes)
    assert set(facts) == {ConditionKind.weather, ConditionKind.fire}
    assert facts[ConditionKind.weather].value == {"temp": 60}
    assert facts[ConditionKind.fire].value == {"count": 0}


def test_verify_passes_point_to_probe() -> None:
    a = FakeAdapter(fact=_fact({"ok": True}))
    p = Point(1.23, 4.56)
    verify(p, {ConditionKind.weather: [a]})
    assert a.probe_points == [p]


def test_verify_preserves_condition_kind_keys() -> None:
    facts = verify(Point(0.0, 0.0), {ConditionKind.permits: [FakeAdapter(fact=_fact({"x": 1}))]})
    assert ConditionKind.permits in facts


def test_verify_skips_drive_time() -> None:
    # drive_time is origin-relative (resolved in ranking/pre-filter, AC-5.3) — never probed here.
    a = FakeAdapter(fact=_fact({"minutes": 30}))
    facts = verify(Point(0.0, 0.0), {ConditionKind.drive_time: [a]})
    assert facts == {}
    assert a.probe_points == []


def test_verify_fails_over_when_primary_unhealthy() -> None:
    down = FakeAdapter(fact=_fact({"from": "primary"}), health=AdapterHealth.DOWN)
    up = FakeAdapter(fact=_fact({"from": "fallback"}))
    facts = verify(Point(0.0, 0.0), {ConditionKind.weather: [down, up]})
    assert facts[ConditionKind.weather].value == {"from": "fallback"}
    assert down.probe_points == []  # health gate skipped it before any GET


def test_verify_lone_adapter_skips_health_check() -> None:
    # No fallback → no wasted health() round-trip; probe directly and let None drive silence.
    a = FakeAdapter(fact=_fact({"ok": True}))
    verify(Point(0.0, 0.0), {ConditionKind.weather: [a]})
    assert a.health_calls == 0
    assert len(a.probe_points) == 1


def test_verify_first_success_wins_per_kind() -> None:
    first = FakeAdapter(fact=_fact({"n": 1}))
    second = FakeAdapter(fact=_fact({"n": 2}))
    facts = verify(Point(0.0, 0.0), {ConditionKind.weather: [first, second]})
    assert facts[ConditionKind.weather].value == {"n": 1}
    assert second.probe_points == []  # short-circuited after the first success
