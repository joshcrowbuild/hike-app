"""Tests for ingestion.checks.facet_diff — the leveled abs+rel facet-diff engine
(Epic 027 S1). Pure-Python, no DB.
"""

from __future__ import annotations

from ingestion.checks.facet_diff import (
    LEVELS,
    breached_hard,
    breached_level,
    diff_facets,
    get_rel,
    ingest_stats_path,
    sorted_by_abs_delta,
)

# ── AC-1.3 — get_rel ───────────────────────────────────────────────────────────


def test_get_rel_pre_zero_yields_100():
    assert get_rel(delta=5, pre=0) == 100.0


def test_get_rel_computes_percentage():
    assert get_rel(delta=-30, pre=100) == 30.0
    assert get_rel(delta=30, pre=100) == 30.0


# ── AC-1.2 — abs-AND-rel gate (both required) ──────────────────────────────────


def test_breach_requires_both_abs_and_rel():
    # Over abs (200 > hard's 25) but under rel (rel_pct=10 <= hard's 20) → no breach.
    assert breached_level(delta=200, rel_pct=10.0) != "hard"
    # Over rel but under abs → no breach at hard.
    assert breached_level(delta=5, rel_pct=90.0) != "hard"
    # Over both → breaches hard.
    assert breached_level(delta=200, rel_pct=90.0) == "low"  # also clears low (coarsest)


# ── AC-1.4 — four ordered levels; hard more sensitive than low ─────────────────


def test_four_levels_ordered_hard_more_sensitive_than_low():
    assert list(LEVELS) == ["low", "medium", "hard", "strict"]
    # A delta/rel pair that breaches hard's (25, 20) but not low's (100, 50).
    assert breached_level(delta=30, rel_pct=25.0) == "hard"
    # Same pair does not clear low.
    low_abs, low_rel = LEVELS["low"]
    assert not (abs(30) > low_abs and 25.0 > low_rel)


def test_breached_level_none_when_nothing_cleared():
    assert breached_level(delta=1, rel_pct=1.0) is None


# ── Design Decision 4 / AC-1.6 — severity encoding (coarsest cleared, not finest) ──


def test_breached_level_reports_coarsest_not_most_sensitive():
    # Breaches low's (100, 50) pair → reports 'low', not 'strict'.
    assert breached_level(delta=500, rel_pct=90.0) == "low"
    # Clears only strict's (10, 10) pair → reports 'strict'.
    assert breached_level(delta=15, rel_pct=15.0) == "strict"


def test_breached_hard_selector_mixed_set():
    rows = diff_facets(
        {"source=osm": 1000, "source=usfs": 1000, "way_type=path": 1000},
        {
            "source=osm": 400,  # big collapse -> breaches low (coarsest)
            "source=usfs": 990,  # tiny change -> no breach
            "way_type=path": 850,  # breaches only strict
        },
    )
    hard = breached_hard(rows)
    hard_keys = {f"{r.dimension}={r.value}" for r in hard}
    assert hard_keys == {"source=osm"}
    for r in hard:
        assert r.breached_level != "strict"
    # way_type=path breaches only strict and must NOT be in breached_hard.
    way_type_row = next(r for r in rows if r.value == "path")
    assert way_type_row.breached_level == "strict"
    assert way_type_row not in hard


# ── AC-1.5 — appeared / disappeared buckets ────────────────────────────────────


def test_disappeared_bucket_has_delta_negative_pre():
    rows = diff_facets({"source=nps": 50}, {})
    row = next(r for r in rows if r.dimension == "source" and r.value == "nps")
    assert row.post == 0
    assert row.delta == -50
    assert row.pre == 50


def test_appeared_bucket_has_rel_pct_100():
    rows = diff_facets({}, {"source=echo": 12})
    row = next(r for r in rows if r.dimension == "source" and r.value == "echo")
    assert row.pre == 0
    assert row.post == 12
    assert row.delta == 12
    assert row.rel_pct == 100.0


def test_diff_facets_covers_every_bucket_in_either_snapshot():
    pre = {"way_type=path": 100, "way_type=track": 50}
    post = {"way_type=path": 98, "named=true": 900}
    rows = diff_facets(pre, post)
    keys = {f"{r.dimension}={r.value}" for r in rows}
    assert keys == {"way_type=path", "way_type=track", "named=true"}


# ── sorting ─────────────────────────────────────────────────────────────────────


def test_sorted_by_abs_delta_descending():
    rows = diff_facets(
        {"a=1": 100, "a=2": 100, "a=3": 100},
        {"a=1": 95, "a=2": 10, "a=3": 99},
    )
    ordered = sorted_by_abs_delta(rows)
    deltas = [abs(r.delta) for r in ordered]
    assert deltas == sorted(deltas, reverse=True)


# ── AC-4.1 — shared path resolver ───────────────────────────────────────────────


def test_ingest_stats_path_default_dir(monkeypatch):
    monkeypatch.delenv("ADVENTURE_INGEST_STATS_DIR", raising=False)
    assert str(ingest_stats_path("shenandoah-gwj")) == "data/ingest_stats/shenandoah-gwj.json"


def test_ingest_stats_path_env_override(monkeypatch):
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", "/tmp/custom-stats")
    assert str(ingest_stats_path("richmond")) == "/tmp/custom-stats/richmond.json"


def test_ingest_stats_path_base_override_wins_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", "/should/not/be/used")
    path = ingest_stats_path("obx", base=tmp_path)
    assert path == tmp_path / "obx.json"
