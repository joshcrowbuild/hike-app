"""Scout tests — row mapping, nearest-trailhead dedup, and top-K cap.

Drives scout with a fake session (duck-typed ScopedSession) so no database is
needed; asserts the candidate logic and that the origin reaches the query.
"""

from __future__ import annotations

from typing import Any

from orchestration.scout import scout, scout_by_name


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


def test_scout_maps_way_type_from_row() -> None:
    # way_type rides the candidate query row into the Candidate (Curator de-rank input).
    rows = [{**_row("a", 100), "way_type": "track"}]
    out = scout(38.5, -78.4, _FakeSession(rows), k=1)  # type: ignore[arg-type]
    assert out[0].way_type == "track"


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


def test_scout_dedupes_same_name_segments_keeping_longest() -> None:
    # D11: Richmond's "Canal Walk" is split into multiple CanonicalTrail segments
    # (different canonical_id, same name) — the feed must show one card, and it
    # should be the richest (longest) segment, not just whichever is nearest.
    rows = [
        {**_row("canal-a", 300), "name": "Canal Walk", "length_mi": 0.4},
        {**_row("canal-b", 100), "name": "Canal Walk", "length_mi": 1.8},
        {**_row("other", 200), "name": "Brown's Island Trail", "length_mi": 0.6},
    ]
    out = scout(37.54, -77.44, _FakeSession(rows), k=10)  # type: ignore[arg-type]
    assert [c.canonical_id for c in out] == ["canal-b", "other"]
    canal = next(c for c in out if c.canonical_id == "canal-b")
    assert canal.length_mi == 1.8


def test_scout_dedupe_name_match_is_case_and_whitespace_insensitive() -> None:
    rows = [
        {**_row("a", 100), "name": "Pipeline Trail", "length_mi": 0.5},
        {**_row("b", 400), "name": "  pipeline   trail  ", "length_mi": 2.0},
    ]
    out = scout(37.54, -77.44, _FakeSession(rows), k=10)  # type: ignore[arg-type]
    assert [c.canonical_id for c in out] == ["b"]


def test_scout_dedupe_ties_on_length_keep_nearest() -> None:
    rows = [
        {**_row("far", 500), "name": "Loop Trail", "length_mi": 1.0},
        {**_row("near", 50), "name": "Loop Trail", "length_mi": 1.0},
    ]
    out = scout(37.54, -77.44, _FakeSession(rows), k=10)  # type: ignore[arg-type]
    assert [c.canonical_id for c in out] == ["near"]


def test_scout_dedupe_keeps_distinct_unnamed_candidates() -> None:
    # An empty/missing name never collapses candidates into each other.
    rows = [
        {**_row("a", 100), "name": ""},
        {**_row("b", 200), "name": ""},
    ]
    out = scout(37.54, -77.44, _FakeSession(rows), k=10)  # type: ignore[arg-type]
    assert {c.canonical_id for c in out} == {"a", "b"}


def _name_row(cid: str, name: str, **extra: Any) -> dict[str, Any]:
    return {
        "canonical_id": cid,
        "name": name,
        "trailhead_id": None,
        "distance_m": None,
        **extra,
    }


def test_scout_by_name_preserves_fulltext_relevance_order() -> None:
    # Epic 038 / B001 Problem A: the FULLTEXT score ORDER returned by the query IS
    # the ranking (rule #2 — name-match relevance, never distance/confidence) — scout_by_name
    # must not re-sort these rows by distance (there is none to sort by).
    rows = [_name_row("b", "Old Rag Loop"), _name_row("a", "Old Rag Mountain")]
    out = scout_by_name("old rag", _FakeSession(rows))  # type: ignore[arg-type]
    assert [c.canonical_id for c in out] == ["b", "a"]  # row order preserved, not re-sorted


def test_scout_by_name_dedupes_same_name_segments() -> None:
    # D11: a same-name split trail still collapses to one card, keeping the richest
    # (longest) segment — same dedup discipline as the spatial scout() path.
    rows = [
        _name_row("canal-a", "Canal Walk", length_mi=0.4),
        _name_row("canal-b", "Canal Walk", length_mi=1.8),
        _name_row("other", "Rivanna Trail", length_mi=2.0),
    ]
    out = scout_by_name("canal", _FakeSession(rows))  # type: ignore[arg-type]
    assert [c.canonical_id for c in out] == ["canal-b", "other"]
    canal = next(c for c in out if c.canonical_id == "canal-b")
    assert canal.length_mi == 1.8


def test_scout_by_name_caps_to_k() -> None:
    rows = [_name_row(f"t{i}", f"Trail {i}") for i in range(5)]
    out = scout_by_name("trail", _FakeSession(rows), k=2)  # type: ignore[arg-type]
    assert len(out) == 2
    assert [c.canonical_id for c in out] == ["t0", "t1"]  # first-seen order preserved


def test_scout_by_name_empty_rows_yields_empty_candidates() -> None:
    out = scout_by_name("gibberish-xyz", _FakeSession([]))  # type: ignore[arg-type]
    assert out == []


def test_scout_by_name_blank_query_short_circuits_before_reaching_the_session() -> None:
    # An empty/whitespace-only query sanitizes to an empty Lucene query string, which
    # Neo4j's fulltext index rejects at query time — this must short-circuit to an
    # honest empty result BEFORE the session is ever called, never surface as a 500.
    fake = _FakeSession([{"canonical_id": "should-not-appear", "name": "x"}])
    assert scout_by_name("", fake) == []  # type: ignore[arg-type]
    assert scout_by_name("   ", fake) == []  # type: ignore[arg-type]
    assert fake.calls == []  # never reached Cypher


def test_scout_by_name_passes_query_and_k_params() -> None:
    fake = _FakeSession([])
    scout_by_name("Old Rag", fake, k=7)  # type: ignore[arg-type]
    _cypher, params = fake.calls[0]
    assert params["k"] == 7


def test_scout_dedupe_caps_to_k_after_collapsing_duplicates() -> None:
    # The name-collapse must free up feed slots for OTHER distinct trails, not just
    # shrink duplicate names below k — this is the actual dogfood symptom (D11):
    # duplicate segments were eating slots that should have gone to real trails.
    rows = [
        {**_row("canal-a", 100), "name": "Canal Walk", "length_mi": 0.4},
        {**_row("canal-b", 150), "name": "Canal Walk", "length_mi": 1.8},
        {**_row("c", 200), "name": "Trail C"},
        {**_row("d", 300), "name": "Trail D"},
    ]
    out = scout(37.54, -77.44, _FakeSession(rows), k=3)  # type: ignore[arg-type]
    assert [c.canonical_id for c in out] == ["canal-b", "c", "d"]
