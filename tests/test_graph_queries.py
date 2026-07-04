"""Tests for the scoped query builders + the scoped-write seam (Epic 011).

Pure / no database: the builders are `(args) -> (cypher, params)` functions and
the guard is a string check, so everything here runs without Neo4j. The fuzz
test (S4) drives every write builder through `ScopedSession.run_write` with a
recording fake runner and adversarial viewer/owner/grant triples, asserting no
builder can write a node owned by anyone but the viewer.

Test names follow: test_s{story}_{ac}_{description}
"""

from __future__ import annotations

import random
import re

import pytest

from graph import queries
from graph.client import ScopedSession
from graph.queries import OWNED_LABELS, UnscopedWriteError

# ── Existing read-builder coverage (pre-Epic-011) ────────────────────────────


def test_candidate_query_shape() -> None:
    cypher, params = queries.candidate_trails_near(38.5, -78.4, 40_000, 5)
    assert "ACCESSES" in cypher
    assert "point.distance" in cypher
    assert "LIMIT $prefetch" in cypher
    assert params["origin"] == {"latitude": 38.5, "longitude": -78.4}
    assert params["radius_m"] == 40_000
    assert params["prefetch"] == 25  # k*5


def test_candidate_query_returns_trailhead_point_distinct_from_trail_point() -> None:
    # H3: the drive-time prefilter must route from the trailhead's own point, not the
    # trail centroid — the query has to project both under distinct aliases.
    cypher, _params = queries.candidate_trails_near(38.5, -78.4, 40_000, 5)
    assert "h.point AS trailhead_point" in cypher
    assert "t.point AS point" in cypher


def test_personal_query_is_owner_scoped() -> None:
    # The access-control-at-query-layer invariant (#4): owned reads carry the scope.
    cypher, params = queries.episode_fields_read("ep:old-rag-2025-09")
    assert "e.owner_id" in cypher
    assert "$viewer_id" in cypher
    assert "$granted_ids" in cypher
    assert params["eid"] == "ep:old-rag-2025-09"


def test_trail_detail_query_shape_and_deterministic_trailhead() -> None:
    # World read (Epic 016 S1 / Epic 017 S4): no owner scope, and the trailhead pick
    # is deterministic (ORDER BY) so a multi-trailhead trail serves a stable point.
    cypher, params = queries.trail_detail("ct:old-rag-loop")
    assert params == {"cid": "ct:old-rag-loop"}
    assert "HAS_SEGMENT" in cypher and "ACCESSES" in cypher
    assert "route_geom_wkt" in cypher and "profile_distances_m" in cypher
    assert "ORDER BY h.trailhead_id" in cypher  # deterministic trailhead choice
    assert "owner_id" not in cypher  # world nodes only — no access scope


def test_trail_source_corroboration_is_world_read_counting_distinct_origins() -> None:
    # CDP-01: distinct upstream origins per SAME_AS cluster — a world read (no owner
    # scope), counting DISTINCT SourceRecord.source (not echoed feeds).
    cypher, params = queries.trail_source_corroboration(["ct:old-rag-loop", "ct:x"])
    assert "SAME_AS" in cypher
    assert "(t)<-[:SAME_AS]-(sr:SourceRecord)" in cypher
    assert "collect(DISTINCT source)" in cypher  # distinct origins, never echoes
    assert "ORDER BY source" in cypher  # deterministic sorted `sources` contract
    assert "size(sources)" in cypher
    assert "owner_id" not in cypher  # world nodes only — no access scope
    assert "$viewer_id" not in cypher
    assert params == {"cids": ["ct:old-rag-loop", "ct:x"]}


def test_owner_scope_clause() -> None:
    clause = queries.owner_scope("x")
    assert clause == "(x.owner_id = $viewer_id OR x.owner_id IN $granted_ids)"


# ── S3 — the write builders (the single author of owned-node write Cypher) ────
#
# Each entry: (label, (cypher, params)). The list IS the coverage surface the
# guard and fuzz test are measured against.


def _write_builder_outputs() -> list[tuple[str, tuple[str, dict]]]:
    """Every owned-node write builder, invoked with owner-namespaced ids.

    Ids are namespaced to `owner` (not `viewer`) on purpose — the fuzz test sets
    owner ∉ {viewer} ∪ granted to prove the *written* owner is still the viewer.
    """
    owner = "mem:adversary"
    eid = f"ep:{owner}:act-1"
    bid = f"belief:{owner}:pace_on_grade_moderate"
    oid = f"outcome:{owner}:act-1"
    sbid = f"belief:{owner}:stated_preference:act-1"
    return [
        (
            "Episode",
            queries.upsert_episode(
                eid,
                watch_activity_id="garmin:act-1",
                source="fit_file",
                distance_m=15000.0,
                ascent_m=800.0,
                descent_m=800.0,
                moving_min=180.0,
                duration_min=200.0,
                avg_heart_rate=140,
                pace_on_grade=14.5,
                now="2026-06-24T00:00:00+00:00",
            ),
        ),
        ("Episode", queries.wire_person_did_episode(eid)),
        ("Episode", queries.wire_episode_on_trail(eid, "ct:old-rag-loop")),
        ("PhysicalProfile", queries.upsert_physical_profile_pace(14.5)),
        ("PhysicalProfile", queries.upsert_physical_profile_maxima(15000.0, 800.0)),
        ("PhysicalProfile", queries.upsert_physical_profile_last_episode("2026-06-24")),
        ("Belief", queries.upsert_pace_belief(bid, "14.5")),
        ("Belief", queries.wire_belief_derived_from_episode(bid, eid)),
        ("Belief", queries.recount_belief_corroboration(bid, 3)),
        ("Belief", queries.wire_belief_about_person(bid)),
        (
            "Outcome",
            queries.upsert_outcome(
                eid,
                outcome_id=oid,
                overall=2,
                delta_question="What stood out?",
                delta_answer="loved the exposed ridge",
                skipped=False,
            ),
        ),
        ("Outcome", queries.wire_episode_has_outcome(eid)),
        ("Belief", queries.upsert_stated_belief(sbid, "loved the exposed ridge")),
    ]


def _recording_session(viewer_id: str, granted_ids: list[str]):
    """A ScopedSession over a fake runner that records (cypher, merged_params)."""
    calls: list[tuple[str, dict]] = []

    def runner(cypher: str, params: dict):
        calls.append((cypher, params))
        return []

    return ScopedSession(viewer_id, granted_ids, runner), calls


_OWNER_BIND_RE = re.compile(r"owner_id\s*[=:]\s*(\$\w+)")


# ── S1 — the guard refuses unscoped owned writes, passes scoped + world writes ─


def test_s1_ac2_unscoped_owned_write_raises() -> None:
    """AC-1.2: a MERGE/SET on an owned label with no scope clause raises."""
    with pytest.raises(UnscopedWriteError):
        queries.assert_scoped_write("MERGE (e:Episode {episode_id: $eid}) SET e.foo = $bar")


def test_s1_ac2_unscoped_write_never_calls_runner() -> None:
    """AC-1.2: run_write raises before the runner is invoked."""
    session, calls = _recording_session("mem:josh", [])
    with pytest.raises(UnscopedWriteError):
        session.run_write(("MERGE (e:Episode {episode_id: $eid}) SET e.foo = $bar", {"eid": "x"}))
    assert calls == []  # runner never reached


def test_s1_ac3_owner_scope_clause_passes() -> None:
    """AC-1.3: a mutate carrying owner_scope(var) passes the guard."""
    cypher = f"MATCH (pp:PhysicalProfile) WHERE {queries.owner_scope('pp')} SET pp.x = 1"
    queries.assert_scoped_write(cypher)  # does not raise


def test_s1_ac3_create_binding_passes() -> None:
    """AC-1.3: a create binding owner_id = $viewer_id passes the guard."""
    queries.assert_scoped_write("MERGE (e:Episode {episode_id: $eid}) SET e.owner_id = $viewer_id")


def test_s1_ac4_world_only_write_needs_no_scope() -> None:
    """AC-1.4: a write touching only world/public labels passes untouched."""
    queries.assert_scoped_write("MERGE (t:CanonicalTrail {canonical_id: $cid}) SET t.name = $name")


def test_s1_ac5_owned_labels_manifest() -> None:
    """AC-1.5: the manifest is exactly the owner-keyed labels; severed/no-owner
    labels are excluded."""
    assert OWNED_LABELS == frozenset(
        {"Episode", "Belief", "PhysicalProfile", "Outcome", "PartyProfile"}
    )
    assert "CommonsObservation" not in OWNED_LABELS  # person-severed by design (C1)
    assert "Dependent" not in OWNED_LABELS  # no owner_id (schema:171)


def test_s1_ac6_free_owner_param_does_not_satisfy_guard() -> None:
    """AC-1.6: binding owner_id to a free $owner (≠ $viewer_id) fails the guard."""
    with pytest.raises(UnscopedWriteError):
        queries.assert_scoped_write("MERGE (e:Episode {episode_id: $eid}) SET e.owner_id = $owner")


# ── S3 — every builder is pure and passes the guard ──────────────────────────


def test_s3_ac2_every_write_builder_passes_the_guard() -> None:
    """AC-3.2: feeding each builder's Cypher through the guard never raises —
    the primary, structural check that builders are scoped."""
    for _label, (cypher, _params) in _write_builder_outputs():
        queries.assert_scoped_write(cypher)  # must not raise


def test_s3_ac4_no_builder_takes_a_free_owner_param() -> None:
    """AC-3.4 / AC-1.6: the only owner a builder may write is $viewer_id."""
    for _label, (cypher, params) in _write_builder_outputs():
        assert "owner" not in params  # no caller-supplied owner param
        for bound in _OWNER_BIND_RE.findall(cypher):
            assert bound == "$viewer_id", f"owner_id bound to {bound}, not $viewer_id"


def test_s3_ac2_owned_upserts_pin_owner_in_the_merge_key() -> None:
    """Review hardening: the natural-key upserts (Episode/Belief, whose ids are
    globally unique) pin owner_id IN the MERGE key, so a foreign id can never
    MATCH and re-own/clobber another member's node — ownership is enforced by the
    seam, not by the id-naming convention."""
    ep_cypher, _ = queries.upsert_episode(
        "ep:x:1",
        watch_activity_id="garmin:1",
        source="fit_file",
        distance_m=1.0,
        ascent_m=1.0,
        descent_m=1.0,
        moving_min=1.0,
        duration_min=1.0,
        avg_heart_rate=1,
        pace_on_grade=1.0,
        now="t",
    )
    assert "MERGE (e:Episode {episode_id: $eid, owner_id: $viewer_id})" in ep_cypher
    bel_cypher, _ = queries.upsert_pace_belief("belief:x:pace_on_grade_moderate", "1.0")
    assert "MERGE (b:Belief {belief_id: $bid, owner_id: $viewer_id})" in bel_cypher


def test_upsert_episode_persists_date_from_start_date() -> None:
    """Epic 003 AC-3.2 prerequisite: upsert_episode writes e.date = date($start_date) — the
    field the 18-month retrieval window filters on — and defaults start_date to None
    (null-safe) when omitted, so existing callers are unaffected."""
    cypher, params = queries.upsert_episode(
        "ep:josh:1",
        watch_activity_id="g:1",
        source="fit_file",
        distance_m=1.0,
        ascent_m=1.0,
        descent_m=1.0,
        moving_min=1.0,
        duration_min=1.0,
        avg_heart_rate=1,
        pace_on_grade=1.0,
        now="2026-06-24T00:00:00+00:00",
        start_date="2026-06-24",
    )
    assert "e.date              = date($start_date)" in cypher
    assert params["start_date"] == "2026-06-24"

    _, params_default = queries.upsert_episode(
        "ep:josh:2",
        watch_activity_id="g:2",
        source="fit_file",
        distance_m=1.0,
        ascent_m=1.0,
        descent_m=1.0,
        moving_min=1.0,
        duration_min=1.0,
        avg_heart_rate=1,
        pace_on_grade=1.0,
        now="t",
    )
    assert params_default["start_date"] is None  # null-safe default for existing callers


def test_last_episode_builder_is_owner_scoped_running_max() -> None:
    """The PhysicalProfile.last_episode_at builder is owner-scoped (passes the guard) and
    advances as a running maximum so an out-of-order backfill never regresses it."""
    cypher, params = queries.upsert_physical_profile_last_episode("2026-06-24")
    queries.assert_scoped_write(cypher)  # owned-write guard: must not raise
    norm = " ".join(cypher.split())
    assert "MERGE (pp:PhysicalProfile {owner_id: $viewer_id})" in norm
    assert "date($episode_date) > pp.last_episode_at" in norm  # running max, never regresses
    assert params["episode_date"] == "2026-06-24"


def test_s2_ac4_recount_preserves_promotion_case() -> None:
    """AC-2.4: the owner-scoped recount keeps the confidence-promotion CASE
    (n≥threshold → 0.7 else 0.3) bound to $threshold — the production write path
    for confidence, which `pace_confidence()` no longer drives. Red-on-regression
    if the CASE, the 0.7 branch, or the threshold binding is dropped."""
    cypher, params = queries.recount_belief_corroboration("belief:x:pace_on_grade_moderate", 3)
    assert "CASE WHEN n >= $threshold THEN 0.7 ELSE 0.3 END" in cypher
    assert "b.corroboration_n = n" in cypher
    assert params["threshold"] == 3


# ── S4 — property/fuzz test over the write builders ──────────────────────────


def _poisoned_cross_owner_write(owner_param_id: str) -> tuple[str, dict]:
    """A builder that forgets the seam and binds owner_id to a free $owner — the
    exact mistake the guard must reject. Used to prove the fuzz machinery is
    adversarial, not tautological."""
    return (
        "MERGE (e:Episode {episode_id: $eid}) SET e.owner_id = $owner",
        {"eid": f"ep:{owner_param_id}:x", "owner": owner_param_id},
    )


def test_s4_ac1_ac2_no_builder_writes_a_non_viewer_owner() -> None:
    """AC-4.1/4.2: for randomized (viewer, owner, granted) triples — the
    `owner`-namespace is deliberately driven OUTSIDE {viewer} ∪ granted — every
    real builder still binds owner_id only to $viewer_id (the written owner is the
    session viewer regardless of the id-namespace), AND a poisoned writer that
    binds the adversarial $owner is rejected by run_write. Cross-owner write is
    impossible, not merely unlikely."""
    rng = random.Random(20260624)
    adversarial_seen = 0
    for _ in range(400):
        viewer = f"mem:v{rng.randint(0, 9999)}"
        owner = f"mem:o{rng.randint(0, 9999)}"  # id-namespace, distinct space from viewer/granted
        granted = [f"mem:g{rng.randint(0, 3)}" for _ in range(rng.randint(0, 3))]
        allowed = {viewer, *granted}
        assert owner not in allowed  # disjoint namespaces → owner is always adversarial
        adversarial_seen += 1

        session, calls = _recording_session(viewer, granted)
        # real builders, with ids namespaced to the *adversarial* owner
        eid = f"ep:{owner}:act"
        bid = f"belief:{owner}:pace_on_grade_moderate"
        for query in (
            queries.upsert_episode(
                eid,
                watch_activity_id="garmin:act",
                source="fit_file",
                distance_m=1.0,
                ascent_m=1.0,
                descent_m=1.0,
                moving_min=1.0,
                duration_min=1.0,
                avg_heart_rate=1,
                pace_on_grade=1.0,
                now="t",
            ),
            queries.wire_person_did_episode(eid),
            queries.upsert_physical_profile_pace(1.0),
            queries.upsert_pace_belief(bid, "1.0"),
            queries.recount_belief_corroboration(bid, 3),
        ):
            session.run_write(query)

        for cypher, merged in calls:
            assert merged["viewer_id"] == viewer  # the seam injected the handed viewer
            assert "owner" not in merged  # no free owner param ever reaches the runner
            # every owner_id the statement binds resolves to the viewer, never `owner`
            for bound in _OWNER_BIND_RE.findall(cypher):
                assert bound == "$viewer_id"
                assert owner not in cypher  # the adversarial owner is nowhere bound

        # the guard rejects a writer that tries to bind the adversarial owner
        with pytest.raises(UnscopedWriteError):
            session.run_write(_poisoned_cross_owner_write(owner))

    assert adversarial_seen == 400  # every iteration exercised an out-of-set owner


def test_s4_ac3_malformed_builder_fails_closed() -> None:
    """AC-4.3: a builder that forgets the scope clause is caught by run_write —
    proving the guard fails closed for a future writer that omits the clause."""

    def _malformed_episode_writer(eid: str) -> tuple[str, dict]:
        # deliberately omits owner_scope / owner_id = $viewer_id
        return ("MERGE (e:Episode {episode_id: $eid}) SET e.distance_m = 1", {"eid": eid})

    session, calls = _recording_session("mem:josh", [])
    with pytest.raises(UnscopedWriteError):
        session.run_write(_malformed_episode_writer("ep:mem:josh:x"))
    assert calls == []


def test_s4_ac4_manifest_coverage_is_explicit() -> None:
    """AC-4.4: coverage is measured against the OWNED_LABELS manifest. A new owned
    label can't be added without classifying its writer (covered vs deferred), so
    the manifest stays the single source of truth the test goes red against."""
    # Outcome is now routed through builders (review finding #1) — the carve-out that
    # excused the live Outcome handler from the seam is gone. PartyProfile stays
    # deferred only because Stage 8 has not built its writer yet (no live handler).
    seam_covered = {"Episode", "Belief", "PhysicalProfile", "Outcome"}
    deferred_writers = {"PartyProfile"}  # Stage 8 — no writer exists yet
    assert seam_covered | deferred_writers == set(OWNED_LABELS)

    covered: set[str] = set()
    for _label, (cypher, _params) in _write_builder_outputs():
        for label in OWNED_LABELS:
            if re.search(rf":\s*{label}\b", cypher):
                covered.add(label)
    assert seam_covered <= covered  # each seam label has ≥1 scoped builder


def test_s4_ac5_world_write_builder_passes_run_write_for_anonymous() -> None:
    """AC-4.5: a world-node write builder passes run_write for an anonymous viewer
    with empty grants — the seam does not over-block public writes."""
    from graph import load

    captured: list[tuple[str, dict]] = []

    def capture(cypher: str, params: dict):
        captured.append((cypher, params))

    load.load_canonical_trail(capture, "ct:x", "X Trail", lat=38.5, lon=-78.4)
    assert captured, "load_canonical_trail should emit a write"

    session, calls = _recording_session("anonymous", [])
    for cypher, params in captured:
        session.run_write((cypher, params))  # must not raise
    assert len(calls) == len(captured)
