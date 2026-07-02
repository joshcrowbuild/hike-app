"""Scout tests — row mapping, nearest-trailhead dedup, and top-K cap.

Drives scout with a fake session (duck-typed ScopedSession) so no database is
needed; asserts the candidate logic and that the origin reaches the query.
"""

from __future__ import annotations

from typing import Any

from orchestration.scout import scout


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        self.calls.append(query)
        return self.rows


class _SplitSession:
    """Returns different rows for the trailhead traversal vs the direct point search,
    keyed off the distinguishing Cypher text, so the sparse-trailhead top-up path can
    be exercised without a database."""

    def __init__(
        self, trailhead_rows: list[dict[str, Any]], direct_rows: list[dict[str, Any]]
    ) -> None:
        self.trailhead_rows = trailhead_rows
        self.direct_rows = direct_rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, _params = query
        self.calls.append(query)
        return self.direct_rows if "point IS NOT NULL" in cypher else self.trailhead_rows


def _row(cid: str, dist: float, th: str = "th:1") -> dict[str, Any]:
    return {"canonical_id": cid, "name": cid, "trailhead_id": th, "distance_m": dist}


def test_scout_dedups_to_nearest_trailhead_and_caps() -> None:
    rows = [_row("a", 300), _row("b", 100), _row("a", 50, "th:2")]  # 'a' twice
    out = scout(38.5, -78.4, _FakeSession(rows), k=2)  # type: ignore[arg-type]
    assert [c.canonical_id for c in out] == ["a", "b"]  # nearest-first, deduped, capped
    assert out[0].distance_m == 50
    assert out[0].trailhead_id == "th:2"  # kept the nearer trailhead for 'a'


def test_scout_passes_origin_param() -> None:
    fake = _FakeSession([])
    scout(38.5, -78.4, fake)  # type: ignore[arg-type]
    _cypher, params = fake.calls[0]
    assert params["origin"] == {"latitude": 38.5, "longitude": -78.4}


def test_scout_carries_trailhead_point_separate_from_trail_point() -> None:
    # H3: the drive-time prefilter needs the trailhead's own point, distinct from the
    # trail's centroid (`point`) — both must survive the row -> Candidate mapping.
    row = _row("a", 100)
    row["point"] = {"latitude": 40.0, "longitude": -80.0}
    row["trailhead_point"] = {"latitude": 38.6, "longitude": -78.5}
    out = scout(38.5, -78.4, _FakeSession([row]))  # type: ignore[arg-type]
    assert out[0].point == {"latitude": 40.0, "longitude": -80.0}
    assert out[0].trailhead_point == {"latitude": 38.6, "longitude": -78.5}


def test_scout_tops_up_from_direct_when_trailheads_sparse() -> None:
    # An urban region: one trailhead-accessed trail (far), many point-bearing trails
    # (near) with no trailhead. The top-up must surface the near trails, nearest-first,
    # while the trailhead trail keeps its trailhead_id.
    trailhead = [_row("far", 21_000.0, "th:far")]
    direct = [
        {"canonical_id": "near1", "name": "near1", "trailhead_id": None, "distance_m": 3000.0},
        {"canonical_id": "near2", "name": "near2", "trailhead_id": None, "distance_m": 5000.0},
        # 'far' also appears in the direct search; it must NOT overwrite the trailhead entry.
        {"canonical_id": "far", "name": "far", "trailhead_id": None, "distance_m": 20_000.0},
    ]
    session = _SplitSession(trailhead, direct)
    out = scout(37.54, -77.44, session, k=10)  # type: ignore[arg-type]
    assert [c.canonical_id for c in out] == ["near1", "near2", "far"]  # nearest-first
    far = next(c for c in out if c.canonical_id == "far")
    assert far.trailhead_id == "th:far"  # trailhead entry preserved, not the direct dup
    assert len(session.calls) == 2  # both queries ran (sparse → top-up)


def test_scout_skips_direct_when_trailheads_dense() -> None:
    # A dense region returns >= k trailhead trails, so the direct top-up never runs and
    # results are unchanged.
    trailhead = [_row(f"t{i}", float(i * 100)) for i in range(10)]
    session = _SplitSession(trailhead, [_row("should-not-appear", 1.0)])
    out = scout(38.5, -78.4, session, k=5)  # type: ignore[arg-type]
    assert [c.canonical_id for c in out] == ["t0", "t1", "t2", "t3", "t4"]
    assert len(session.calls) == 1  # only the trailhead query ran
