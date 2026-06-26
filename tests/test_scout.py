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
