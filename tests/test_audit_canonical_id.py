"""Tests for scripts.audit_canonical_id (Epic 030, S4, DB-free).

Covers the pure collision-clustering helper only — no Neo4j session is opened.
"""

from __future__ import annotations

from ingestion.pipeline import _build_canonical_id
from scripts.audit_canonical_id import _prefix_id_legacy, find_same_source_clusters


def _row(source: str, source_id: str, raw_name: str) -> dict[str, str]:
    return {"source": source, "source_id": source_id, "raw_name": raw_name}


def test_flags_same_source_distinct_name_collision():
    rows = [
        _row("osm", "", "Blue/Ridge Trail"),
        _row("osm", "", "Blue Ridge Trail"),
    ]
    clusters = find_same_source_clusters(rows, _prefix_id_legacy)
    assert len(clusters) == 1


def test_corrected_function_resolves_the_legacy_collision():
    rows = [
        _row("osm", "", "Blue/Ridge Trail"),
        _row("osm", "", "Blue Ridge Trail"),
    ]
    corrected = find_same_source_clusters(rows, lambda s, sid, n: _build_canonical_id(s, sid, n))
    legacy = find_same_source_clusters(rows, _prefix_id_legacy)
    assert len(corrected) == 0
    assert len(legacy) == 1


def test_cross_source_sharing_is_not_flagged():
    rows = [
        _row("osm", "", "Old Rag Loop"),
        _row("nps", "", "Old Rag Loop"),
    ]
    clusters = find_same_source_clusters(rows, lambda s, sid, n: _build_canonical_id(s, sid, n))
    assert clusters == {}


def test_empty_rows_yield_no_clusters():
    assert find_same_source_clusters([], _prefix_id_legacy) == {}


def test_distinct_source_records_no_collision():
    rows = [_row("osm", "", "Old Rag Loop"), _row("osm", "", "Skyline Drive")]
    clusters = find_same_source_clusters(rows, lambda s, sid, n: _build_canonical_id(s, sid, n))
    assert clusters == {}
