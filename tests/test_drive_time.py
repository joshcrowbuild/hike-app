"""Epic 013 S5 / Epic 005 — Valhalla drive-time adapter + the Scout pre-filter.

Mocked Valhalla responses (success, over-budget, total outage, partial failure) drive
the batch matrix/isochrone calls and the origin-relative pre-filter. Asserts the cost
bound (one matrix + one isochrone, independent of N), source-or-silence, and
degrade-and-disclose. No network — httpx.MockTransport.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from orchestration.adapters import valhalla
from orchestration.adapters.base import Point, VerifiedFact
from orchestration.adapters.valhalla import ValhallaAdapter
from orchestration.drive_time import DRIVE_UNAVAILABLE, point_in_polygon, prefilter, time_budget_s
from orchestration.intent import Intent
from orchestration.scout import Candidate

_ORIGIN = (38.50, -78.40)
_NOW = datetime(2026, 6, 24, tzinfo=timezone.utc)


def _candidate(cid: str, lat: float | None, lon: float | None = None) -> Candidate:
    point = {"latitude": lat, "longitude": lon} if lat is not None else None
    return Candidate(canonical_id=cid, name=cid, trailhead_id="th", distance_m=100.0, point=point)


def _coord_of(c: Candidate):  # type: ignore[no-untyped-def]
    p = c.point
    if isinstance(p, dict) and p.get("latitude") is not None:
        return (p["latitude"], p["longitude"])
    return None


# ── Time budget (Epic 005 S3) ──


def test_s3_budget_from_stated_time_wins() -> None:
    assert time_budget_s(Intent(time_budget_s=2700), radius_m=40000, drive_speed_kmh=60.0) == 2700.0


def test_s3_budget_derived_from_radius() -> None:
    # 40 km at 60 km/h ≈ 2400 s.
    budget = time_budget_s(Intent(), radius_m=40000, drive_speed_kmh=60.0)
    assert 2300 < budget < 2500


# ── Batch adapter calls (Epic 005 S4) ──


def test_s4_matrix_one_call_k_targets() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "sources_to_targets": [
                    [{"time": 600, "distance": 10}, {"time": 1800, "distance": 30}]
                ]
            },
        )

    facts = valhalla.fetch_matrix(
        _ORIGIN,
        [(38.6, -78.5), (38.7, -78.6)],
        "http://v:8002",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert calls["n"] == 1  # K targets ⇒ exactly one /sources_to_targets POST
    assert facts[0] is not None and facts[0].value["drive_seconds"] == 600
    assert facts[1] is not None and facts[1].value["drive_seconds"] == 1800


def test_s4_isochrone_returns_polygon() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "geometry": {
                            "coordinates": [
                                [[-78.6, 38.4], [-78.2, 38.4], [-78.2, 38.7], [-78.6, 38.7]]
                            ]
                        }
                    }
                ]
            },
        )

    poly = valhalla.fetch_isochrone(
        _ORIGIN, 2400, "http://v:8002", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert poly is not None
    assert (38.4, -78.6) in poly  # converted to (lat, lon)


def test_s4_matrix_degrades_on_malformed_200() -> None:
    # A dict-shaped (not list) sources_to_targets must degrade to all-None, not raise.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sources_to_targets": {"oops": 1}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    facts = valhalla.fetch_matrix(_ORIGIN, [(38.6, -78.5)], "http://v", client=client)
    assert facts == [None]


def test_s4_isochrone_degrades_on_multipolygon_and_null() -> None:
    # A MultiPolygon (ring-of-rings) and null coordinates must yield None, never raise.
    for coords in (
        [[[[-78.6, 38.4], [-78.2, 38.4]]]],  # nested → MultiPolygon-ish
        [[[None, None], [None, None]]],  # null coordinate values
    ):

        def handler(request: httpx.Request, _c: object = coords) -> httpx.Response:
            return httpx.Response(200, json={"features": [{"geometry": {"coordinates": _c}}]})

        poly = valhalla.fetch_isochrone(
            _ORIGIN, 2400, "http://v", client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        assert poly is None


def test_point_in_polygon_inside_outside() -> None:
    square = [(38.4, -78.6), (38.4, -78.2), (38.7, -78.2), (38.7, -78.6)]
    assert point_in_polygon((38.5, -78.4), square) is True
    assert point_in_polygon((39.9, -78.4), square) is False


# ── The pre-filter: prune + per-candidate fact + cost bound (S4/S5) ──


class _FakeComputer:
    """A DriveTimeComputer with controllable isochrone/matrix + call counters."""

    def __init__(self, polygon=None, times=None) -> None:  # type: ignore[no-untyped-def]
        self._polygon = polygon
        self._times = times  # list of drive_seconds | None, aligned to targets
        self.iso_calls = 0
        self.matrix_calls = 0

    def isochrone(self, origin, time_budget_s):  # type: ignore[no-untyped-def]
        self.iso_calls += 1
        return self._polygon

    def matrix(self, origin, targets):  # type: ignore[no-untyped-def]
        self.matrix_calls += 1
        out = []
        for i in range(len(targets)):
            secs = self._times[i] if self._times and i < len(self._times) else 600
            out.append(
                None
                if secs is None
                else VerifiedFact(
                    value={"drive_seconds": secs}, source="Valhalla (self-hosted)", fetched_at=_NOW
                )
            )
        return out

    def health(self):  # type: ignore[no-untyped-def]
        return None


def test_s4_matrix_only_drops_over_budget() -> None:
    # No isochrone → matrix-only path; budget 1000 s drops the 1800 s candidate.
    comp = _FakeComputer(polygon=None, times=[600, 1800])
    cands = [_candidate("near", 38.6, -78.5), _candidate("far", 38.7, -78.6)]
    res = prefilter(_ORIGIN, cands, comp, 1000.0, coord_of=_coord_of)
    kept = [c.canonical_id for c in res.kept]
    assert kept == ["near"]  # far dropped (1800 > 1000)
    assert "near" in res.facts_by_id and "far" not in res.facts_by_id
    assert comp.iso_calls == 1 and comp.matrix_calls == 1  # cost bound: ≤1 each


def test_s5_point_with_no_coord_kept_unrouted() -> None:
    comp = _FakeComputer(polygon=None, times=[600])
    cands = [_candidate("ok", 38.6, -78.5), _candidate("nogeo", None)]
    res = prefilter(_ORIGIN, cands, comp, 5000.0, coord_of=_coord_of)
    kept = {c.canonical_id for c in res.kept}
    assert kept == {"ok", "nogeo"}  # no-coord candidate kept, never routed
    assert "nogeo" not in res.facts_by_id  # no fabricated 0-min


def test_s4_all_over_budget_prunes_without_false_outage() -> None:
    # The router responded (real times), every candidate is over budget → all pruned,
    # and NO false "router unavailable" disclosure (regression: outage ≠ full prune).
    comp = _FakeComputer(polygon=None, times=[1800, 2400])
    cands = [_candidate("far1", 38.6, -78.5), _candidate("far2", 38.7, -78.6)]
    res = prefilter(_ORIGIN, cands, comp, 1000.0, coord_of=_coord_of)
    assert res.kept == []  # both legitimately too far → pruned, not restored
    assert res.facts_by_id == {}
    assert res.disclosure is None  # router worked → no crow-flies fallback notice


def test_s6_total_outage_keeps_all_with_disclosure() -> None:
    # Router down: no isochrone, matrix all None → keep everyone, one disclosure.
    comp = _FakeComputer(polygon=None, times=[None, None])
    cands = [_candidate("a", 38.6, -78.5), _candidate("b", 38.7, -78.6)]
    res = prefilter(_ORIGIN, cands, comp, 1000.0, coord_of=_coord_of)
    assert {c.canonical_id for c in res.kept} == {"a", "b"}  # none dropped on outage
    assert res.facts_by_id == {}  # no fabricated times
    assert res.disclosure == DRIVE_UNAVAILABLE


def test_s6_partial_failure_degrades_per_candidate() -> None:
    # Matrix returns a time for one, None for the other → the timed one is budget-checked,
    # the untimed one is kept (absence is never "too far"), no feed-level disclosure.
    comp = _FakeComputer(polygon=None, times=[600, None])
    cands = [_candidate("timed", 38.6, -78.5), _candidate("untimed", 38.7, -78.6)]
    res = prefilter(_ORIGIN, cands, comp, 5000.0, coord_of=_coord_of)
    assert {c.canonical_id for c in res.kept} == {"timed", "untimed"}
    assert "timed" in res.facts_by_id and "untimed" not in res.facts_by_id
    assert res.disclosure is None  # some times present → not a feed-level outage


# ── ValhallaAdapter contract behavior (S5) ──


def test_s5_adapter_probe_needs_origin() -> None:
    # Unbound origin → probe returns None (never a fabricated time).
    adapter = ValhallaAdapter("http://v:8002")
    assert adapter.probe(Point(38.6, -78.5)) is None


def test_s5_adapter_from_config_none_without_base_url() -> None:
    from orchestration.config import Settings

    assert ValhallaAdapter.from_config(Settings.from_env({})) is None
    built = ValhallaAdapter.from_config(Settings.from_env({"VALHALLA_BASE_URL": "http://v:8002"}))
    assert isinstance(built, ValhallaAdapter)
