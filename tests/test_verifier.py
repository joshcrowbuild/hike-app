"""Verifier tests — kind-keyed iteration with health-driven primary→fallback.

Source-or-silence (keep only what returned) is preserved byte-for-byte across the
Epic 013 reshape; what is new is the kind-keyed failover. Fake adapters with
controllable health() + probe() — no network.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
)
from orchestration.adapters.registry import TTLCache
from orchestration.curator import evaluate_guardrails
from orchestration.verifier import verify

_POINT = Point(38.5, -78.4)


def _fact(value: Any, *, source: str = "test", at: datetime | None = None) -> VerifiedFact:
    return VerifiedFact(value=value, source=source, fetched_at=at or datetime.now(timezone.utc))


class _FakeAdapter(LiveAdapter):
    def __init__(
        self,
        name: str,
        kind: ConditionKind,
        *,
        health: AdapterHealth = AdapterHealth.OK,
        fact: VerifiedFact | None = None,
    ) -> None:
        self.name = name
        self.kind = kind
        self._health = health
        self._fact = fact
        self.probe_calls = 0
        self.health_calls = 0

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        self.probe_calls += 1
        return self._fact

    def health(self) -> AdapterHealth:
        self.health_calls += 1
        return self._health

    @classmethod
    def from_config(cls, settings: Any) -> "LiveAdapter | None":
        return None


# ── AC-3.2 / AC-3.3 / AC-3.4 — keep only what returned, keyed by ConditionKind ──


def test_s3_ac2_returns_kind_keyed_facts() -> None:
    w = _FakeAdapter("w", ConditionKind.weather, fact=_fact({"short_forecast": "Sunny"}))
    a = _FakeAdapter("a", ConditionKind.air, fact=None)  # source-or-silence: contributes nothing
    facts = verify(_POINT, {ConditionKind.weather: [w], ConditionKind.air: [a]})
    assert set(facts) == {ConditionKind.weather}
    assert facts[ConditionKind.weather].value["short_forecast"] == "Sunny"


def test_s3_ac3_kind_absent_when_all_adapters_silent() -> None:
    a1 = _FakeAdapter("a1", ConditionKind.air, fact=None)
    a2 = _FakeAdapter("a2", ConditionKind.air, fact=None)
    facts = verify(_POINT, {ConditionKind.air: [a1, a2]})
    assert ConditionKind.air not in facts  # never present with a fabricated value


def test_s3_ac4_source_and_timestamp_passed_through_unmodified() -> None:
    when = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    w = _FakeAdapter("w", ConditionKind.weather, fact=_fact({"x": 1}, source="NWS api", at=when))
    facts = verify(_POINT, {ConditionKind.weather: [w]})
    assert facts[ConditionKind.weather].source == "NWS api"
    assert facts[ConditionKind.weather].fetched_at == when


# ── AC-2.4 / AC-2.5 / AC-2.6 — health-driven primary→fallback ──


def test_s2_ac4_down_primary_falls_to_secondary() -> None:
    primary = _FakeAdapter(
        "p", ConditionKind.weather, health=AdapterHealth.DOWN, fact=_fact({"p": 1})
    )
    secondary = _FakeAdapter("s", ConditionKind.weather, fact=_fact({"s": 1}))
    facts = verify(_POINT, {ConditionKind.weather: [primary, secondary]})
    assert primary.probe_calls == 0  # down → never probed
    assert secondary.probe_calls == 1
    assert facts[ConditionKind.weather].value == {"s": 1}


def test_s2_ac5_rate_limited_primary_falls_to_secondary() -> None:
    primary = _FakeAdapter(
        "p", ConditionKind.weather, health=AdapterHealth.RATE_LIMITED, fact=_fact({"p": 1})
    )
    secondary = _FakeAdapter("s", ConditionKind.weather, fact=_fact({"s": 1}))
    verify(_POINT, {ConditionKind.weather: [primary, secondary]})
    assert primary.probe_calls == 0 and secondary.probe_calls == 1


def test_s2_ac6_first_success_wins_secondary_not_called() -> None:
    primary = _FakeAdapter("p", ConditionKind.weather, fact=_fact({"p": 1}))
    secondary = _FakeAdapter("s", ConditionKind.weather, fact=_fact({"s": 1}))
    facts = verify(_POINT, {ConditionKind.weather: [primary, secondary]})
    assert primary.probe_calls == 1 and secondary.probe_calls == 0
    assert facts[ConditionKind.weather].value == {"p": 1}


def test_single_adapter_kind_skips_health_check() -> None:
    # A lone adapter has no failover candidate, so health() is not worth a round-trip.
    only = _FakeAdapter("only", ConditionKind.weather, fact=_fact({"v": 1}))
    verify(_POINT, {ConditionKind.weather: [only]})
    assert only.probe_calls == 1 and only.health_calls == 0


# ── AC-5.4 (via verify) — a fresh cache hit short-circuits health() AND probe() ──


def test_s5_ac4_cache_hit_short_circuits_health_and_probe() -> None:
    primary = _FakeAdapter("p", ConditionKind.weather, fact=_fact({"v": 1}))
    secondary = _FakeAdapter("s", ConditionKind.weather, fact=_fact({"v": 2}))
    cache = TTLCache(clock=lambda: 1000.0)  # frozen clock → always within TTL
    probes = {ConditionKind.weather: [primary, secondary]}

    first = verify(_POINT, probes, cache=cache)  # seeds the cache from the primary
    assert first[ConditionKind.weather].value == {"v": 1}
    base_probe, base_health = primary.probe_calls, primary.health_calls

    second = verify(_POINT, probes, cache=cache)  # cache hit → no health, no probe
    assert second[ConditionKind.weather].value == {"v": 1}
    assert primary.probe_calls == base_probe  # served from cache, no second probe
    assert primary.health_calls == base_health  # peek short-circuits the liveness check
    assert secondary.probe_calls == 0


# ── AC-5.3 — drive_time is excluded from the per-point loop ──


def test_s5_ac3_drive_time_excluded_from_verify() -> None:
    dt = _FakeAdapter("valhalla", ConditionKind.drive_time, fact=_fact({"drive_seconds": 1800}))
    facts = verify(_POINT, {ConditionKind.drive_time: [dt]})
    assert ConditionKind.drive_time not in facts
    assert dt.probe_calls == 0  # never probed in the per-point loop


# ── AC-3.5 — a guardrail-block path still fires through the registry-routed facts ──


def test_s3_ac5_guardrail_block_fires_through_registry() -> None:
    w = _FakeAdapter(
        "nws", ConditionKind.weather, fact=_fact({"active_alerts": ["Red Flag Warning"]})
    )
    facts = verify(_POINT, {ConditionKind.weather: [w]})
    verdict = evaluate_guardrails(facts)  # ConditionKind-keyed facts → still blocks
    assert verdict.blocked
    assert any("Red Flag" in b for b in verdict.blocks)
