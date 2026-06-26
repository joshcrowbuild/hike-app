"""Tests for graph.load.load_enrichment_facts (Epic 017 S1 — the deferred write).

The loader closes the pipeline's explicit "no graph write yet" gap: it persists
`EnrichmentFact`s onto their target CanonicalTrail nodes, generically (attribute →
property), grouped per node into one idempotent MERGE+SET. Network-free via a fake
runner. The seam/protocol is reused (real `EnrichmentFact`), not rebuilt.
"""

from __future__ import annotations

import pytest

from graph.load import load_enrichment_facts
from ingestion.sources.base import EnrichmentFact


def _fact(attr, value, cid):
    return EnrichmentFact(source="x", attribute=attr, value=value, canonical_id=cid)


def test_groups_facts_per_node_one_merge_each():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    n = load_enrichment_facts(
        runner,
        [
            _fact("total_gain_m", 100.0, "ct:1"),
            _fact("total_loss_m", 80.0, "ct:1"),
            _fact("total_gain_m", 50.0, "ct:2"),
        ],
    )
    assert n == 2  # two distinct nodes written
    assert len(calls) == 2  # one MERGE per node, not per fact
    c1 = next(p for _, p in calls if p["cid"] == "ct:1")
    assert {c1["v0"], c1["v1"]} == {100.0, 80.0}  # both properties set on ct:1
    assert all("MERGE (t:CanonicalTrail" in cy for cy, _ in calls)


def test_writes_list_property_for_parallel_arrays():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    load_enrichment_facts(
        runner,
        [_fact("profile_distances_m", [0.0, 10.0, 20.0], "ct:1")],
    )
    cypher, params = calls[0]
    assert "t.profile_distances_m = $v0" in cypher
    assert params["v0"] == [0.0, 10.0, 20.0]


def test_later_fact_wins_for_same_attribute_on_a_node():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    load_enrichment_facts(
        runner, [_fact("total_gain_m", 1.0, "ct:1"), _fact("total_gain_m", 2.0, "ct:1")]
    )
    params = calls[0][1]
    assert params["v0"] == 2.0  # last value wins; one SET clause
    assert calls[0][0].count("total_gain_m") == 1


def test_skips_facts_without_canonical_id():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    n = load_enrichment_facts(runner, [EnrichmentFact(source="x", attribute="g", value=1.0)])
    assert n == 0 and calls == []  # nothing to attach it to


def test_rejects_unsafe_attribute_name():
    runner = lambda c, p: None  # noqa: E731
    with pytest.raises(ValueError):
        load_enrichment_facts(runner, [_fact("return", 1, "ct:1")])  # reserved word
    with pytest.raises(ValueError):
        load_enrichment_facts(runner, [_fact("bad-name", 1, "ct:1")])  # not an identifier


def test_idempotent_shape_all_merge():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    load_enrichment_facts(runner, [_fact("elev_source", "usgs-3dep", "ct:1")])
    assert all("MERGE" in cy for cy, _ in calls)
