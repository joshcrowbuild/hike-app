"""Per-kind condition dispositions on the card (Epic 018 S4 / CDP-02).

Every point kind gets exactly one ConditionStatus so absence is legible, distinct
silence — never a blank the client must guess about, never a false-clear:

  present / stale_degraded — a sourced reading renders as a feed line (aged past
                             its horizon it stays shown, flagged, never deleted)
  no_hazard                — the source ANSWERED "nothing to flag" (calm silence)
  no_data                  — the source ANSWERED "nothing covers this spot"
  unavailable              — probed, no source answered (couldn't verify)
  not_fetched              — not probed in this deployment (no signal either way)

Presentation only — none of this feeds ranking or confidence (Rule #2).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestration.adapters.base import ConditionKind, VerifiedFact
from orchestration.curator import GuardrailVerdict
from orchestration.engine import PlannedTrail, feed_card
from orchestration.scout import Candidate

_NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


def _fact(value: object, *, source: str = "src gov", age_s: float = 60.0) -> VerifiedFact:
    return VerifiedFact(value=value, source=source, fetched_at=_NOW - timedelta(seconds=age_s))


def _planned(
    facts: dict[ConditionKind, VerifiedFact],
    probed: frozenset[ConditionKind] = frozenset(),
) -> PlannedTrail:
    return PlannedTrail(
        Candidate("t1", "Trail One", "th", 1000.0),
        facts,
        {},
        GuardrailVerdict(False),
        probed_kinds=probed,
    )


def _status(card, kind: ConditionKind):  # type: ignore[no-untyped-def]
    return next(s for s in card.conditions if s.kind == kind.value)


def test_every_point_kind_gets_exactly_one_status_in_canonical_order() -> None:
    card = feed_card(_planned({}), now=_NOW)
    assert [s.kind for s in card.conditions] == [
        "weather",
        "air",
        "fire",
        "water",
        "closures",
        "permits",
    ]


def test_fresh_fact_is_present_and_renders_a_line() -> None:
    facts = {ConditionKind.weather: _fact({"short_forecast": "Sunny", "active_alerts": []})}
    card = feed_card(_planned(facts, probed=frozenset(facts)), now=_NOW)
    status = _status(card, ConditionKind.weather)
    assert status.state == "present"
    assert status.source and status.checked_at is not None
    assert len(card.lines) == 1  # the reading renders


def test_probed_but_silent_is_unavailable_and_unprobed_is_not_fetched() -> None:
    # Rule #1's split: "we asked and nobody answered" is not the same claim as
    # "we never asked" — the two must be distinct states on the wire.
    card = feed_card(_planned({}, probed=frozenset({ConditionKind.weather})), now=_NOW)
    assert _status(card, ConditionKind.weather).state == "unavailable"
    assert _status(card, ConditionKind.air).state == "not_fetched"
    assert card.lines == []  # neither fabricates a line


def test_checked_clear_is_no_hazard_silence_not_a_line() -> None:
    # FIRMS 0 detections / NPS 0 relevant alerts: an ANSWERED clear renders as calm
    # silence (no "0 detections" noise line) but keeps its source + timestamp.
    facts = {
        ConditionKind.fire: _fact({"hotspot_count": 0}),
        ConditionKind.closures: _fact({"park": "SNP", "alerts": [], "count": 0}),
    }
    card = feed_card(_planned(facts, probed=frozenset(facts)), now=_NOW)
    for kind in (ConditionKind.fire, ConditionKind.closures):
        status = _status(card, kind)
        assert status.state == "no_hazard"
        assert status.source and status.checked_at is not None
    assert card.lines == []


def test_coverage_gap_is_no_data_silence_with_the_adapter_disclosure() -> None:
    facts = {
        ConditionKind.water: VerifiedFact(
            value={"gauge_available": False},
            source="USGS Water Data",
            fetched_at=_NOW,
            disclosures=("No USGS gauge within the search radius of this point.",),
        ),
        ConditionKind.closures: _fact({"in_range": False, "radius_miles": 40.0}),
    }
    card = feed_card(_planned(facts, probed=frozenset(facts)), now=_NOW)
    water = _status(card, ConditionKind.water)
    assert water.state == "no_data"
    assert "No USGS gauge" in water.detail
    assert _status(card, ConditionKind.closures).state == "no_data"
    assert card.lines == []


def test_nonzero_hazard_is_present_never_silenced() -> None:
    # The clear-vs-hazard boundary: 1 detection is a reading, not silence.
    facts = {ConditionKind.fire: _fact({"hotspot_count": 1})}
    card = feed_card(_planned(facts, probed=frozenset(facts)), now=_NOW)
    assert _status(card, ConditionKind.fire).state == "present"
    assert len(card.lines) == 1


def test_fact_past_its_horizon_is_stale_degraded_but_still_renders() -> None:
    # Honesty is relocation, not deletion: an aged fact keeps its line, flagged.
    facts = {ConditionKind.water: _fact({"latest_discharge_cfs": 123.0}, age_s=4000.0)}
    card = feed_card(_planned(facts, probed=frozenset(facts)), now=_NOW)
    assert _status(card, ConditionKind.water).state == "stale_degraded"
    assert len(card.lines) == 1  # still shown, with its age


def test_drive_time_stays_a_line_with_no_condition_status() -> None:
    # Origin-relative, not a point condition: it renders but never gets a status.
    facts = {ConditionKind.drive_time: _fact({"drive_seconds": 1800.0})}
    card = feed_card(_planned(facts), now=_NOW)
    assert len(card.lines) == 1
    assert all(s.kind != "drive_time" for s in card.conditions)


def test_states_never_feed_ranking_inputs() -> None:
    # Rule #2 structurally: ConditionStatus carries no score-shaped field.
    from orchestration.engine import ConditionStatus

    fields = set(ConditionStatus.__dataclass_fields__)
    assert fields == {"kind", "state", "source", "checked_at", "detail"}
