"""Tests for ingestion.pipeline._build_canonical_id (Epic 030, S1-S3, DB-free).

Covers the two collision modes: (a) distinct names slugifying to the same
short string with no old-guard length threshold crossed, and (b) distinct
names sharing a long common prefix that survives truncation. Both must now
produce distinct canonical_ids; identical/ref-present inputs must still
conflate (S3).
"""

from __future__ import annotations

from ingestion.pipeline import _build_canonical_id

# ── S1 — short-slug guard applies unconditionally, hashes the full name ───────


def test_short_identical_slug_names_get_distinct_ids():
    a = _build_canonical_id("osm", None, "Blue/Ridge Trail")
    b = _build_canonical_id("osm", None, "Blue Ridge Trail")
    assert a != b


def test_double_space_vs_single_space_get_distinct_ids():
    a = _build_canonical_id("osm", None, "Foo  Bar")
    b = _build_canonical_id("osm", None, "Foo Bar")
    assert a != b


# ── S2 — long shared-prefix truncation no longer collides ─────────────────────


def test_long_shared_prefix_names_get_distinct_ids():
    prefix = "Appalachian Trail Northbound Section Through The Ridge " * 2
    a = _build_canonical_id("osm", None, prefix + "Alpha")
    b = _build_canonical_id("osm", None, prefix + "Beta")
    assert len(prefix) >= 55
    assert a != b


def test_pathologically_long_name_id_is_bounded():
    name = "A" * 5000
    cid = _build_canonical_id("osm", None, name)
    assert len(cid) <= 128


# ── S3 — identical names still conflate; ref path unchanged ───────────────────


def test_identical_names_are_idempotent():
    a = _build_canonical_id("nps", None, "Old Rag Loop")
    b = _build_canonical_id("nps", None, "Old Rag Loop")
    assert a == b


def test_ref_present_branch_unchanged():
    assert _build_canonical_id("osm", "relation/123", "Anything") == "ct:osm:relation_123"
