"""Structural privacy + atomicity suite for the commons fork (Epic 010 S5 / S2).

gap-audit C1's whole point: a privacy test against *absent* code passes vacuously
— a false guarantee. This suite is built so it FAILS if the fork is removed or
never wrote: the non-vacuity guard (AC-5.4) asserts a `:CommonsObservation` was
actually produced before the unlinkability assertions run.

The suite is DB-free (runs in `make check`/CI, AC-5.5): it inspects the Cypher +
de-identified params create_episode commits, which is a stronger proof than a
live reachability query for the "born severed" property — a node CREATEd with no
relationship syntax, never referenced again, can have no path of any length to a
:Person (Stage 9 §2.1: "a security test cannot prove a *transient* edge never
existed"; born-severed has no such window).

Test names follow: test_s{story}_{ac}_{description}
"""

from __future__ import annotations

from datetime import datetime

import pytest

from graph.client import ScopedSession
from ingestion import commons_fork
from ingestion.ingest_episode import FITSummary, compute_pace_on_grade, create_episode

_SALT = "test-salt-not-a-real-secret"


def _track(n: int = 30, step_lon: float = 0.0006) -> list[tuple[float, float]]:
    return [(38.5, -78.40 + i * step_lon) for i in range(n)]


def _summary() -> FITSummary:
    return FITSummary(
        watch_activity_id="garmin:act-1",
        total_distance_m=15000.0,
        total_ascent_m=735.0,
        total_descent_m=735.0,
        moving_time_s=10800.0,
        total_time_s=12000.0,
        avg_heart_rate=140,
        start_lat=38.5,
        start_lon=-78.40,
        end_lat=38.5,
        end_lon=-78.40 + 29 * 0.0006,
        sport="hiking",
        start_time=datetime(2026, 6, 24, 9, 0, 0),
        gps_track=_track(),
    )


def _commit_batch(summary: FITSummary, trail: str | None = "ct:x") -> list[tuple[str, dict]]:
    """Run create_episode through a recording ScopedSession; return the committed
    transaction batch (list of (cypher, merged_params))."""
    batches: list[list[tuple[str, dict]]] = []

    def runner(cypher: str, params: dict):
        return []

    def tx_runner(merged: list[tuple[str, dict]]):
        batches.append(list(merged))

    session = ScopedSession("mem:josh", [], runner, tx_runner)
    create_episode(summary, trail, "mem:josh", session, commons_salt=_SALT)
    assert len(batches) == 1
    return batches[0]


def _commons(batch: list[tuple[str, dict]]) -> tuple[str, dict]:
    hits = [(c, p) for c, p in batch if "CommonsObservation" in c]
    assert len(hits) == 1
    return hits[0]


# ── AC-5.4 — non-vacuity FIRST (the load-bearing guard) ──────────────────────


def test_s5_ac4_privacy_suite_not_vacuous() -> None:
    """AC-5.4: at least one :CommonsObservation is actually written for the
    ingested episode. If a regression silently stops writing the fork, the count
    drops to 0 and this goes RED — closing the C1 "vacuously pass against absent
    code" failure mode that the rest of the suite would otherwise hide."""
    batch = _commit_batch(_summary())
    co_count = sum(1 for c, _ in batch if "MERGE (co:CommonsObservation" in c)
    assert co_count >= 1


# ── AC-5.1 — no path of any length to a :Person/:Episode/:Outcome ────────────


def test_s5_ac1_observation_is_born_severed() -> None:
    """AC-5.1: the observation is CREATEd with zero relationships of any kind, no
    owner_id, no reference to a :Person/:Episode/:Outcome, and the `co` binding
    appears in no other statement — so no path of any length can exist."""
    batch = _commit_batch(_summary())
    co_cypher, _ = _commons(batch)
    for token in (
        "-[",
        "]->",
        "<-[",
        "]-(",
        "owner_id",
        ":Person",
        ":Episode",
        ":Outcome",
        "$viewer_id",
    ):
        assert token not in co_cypher, f"severance broken: {token!r} in commons CREATE"
    # `co` is never wired by any other statement in the transaction
    for cypher, _ in batch:
        if "CommonsObservation" in cypher:
            continue
        assert "(co" not in cypher and "co)" not in cypher


# ── AC-5.2 — endpoint-trim provably fired ────────────────────────────────────


def test_s5_ac2_trim_fired_beyond_radius() -> None:
    """AC-5.2: the trimmed_track startpoint is >250m from the raw track startpoint."""
    summary = _summary()
    _, co_params = _commons(_commit_batch(summary))
    wkt = co_params["trimmed_track"]
    assert wkt and wkt.startswith("LINESTRING(")
    first = wkt[len("LINESTRING(") :].split(",")[0].strip().split()
    lon, lat = float(first[0]), float(first[1])
    raw_start = summary.gps_track[0]
    assert commons_fork._haversine_m((lat, lon), raw_start) > commons_fork.TRIM_RADIUS_M


def test_s5_no_gps_yields_null_trimmed_track() -> None:
    """AC-3.3 companion: the no-GPS case produces trimmed_track = null (not an
    error), and is skipped by the trim-fired assertion."""
    summary = _summary()
    summary.gps_track = []
    _, co_params = _commons(_commit_batch(summary))
    assert co_params["trimmed_track"] is None


# ── AC-5.3 — no raw quasi-identifier on the observation ──────────────────────


def test_s5_ac3_no_raw_quasi_identifier() -> None:
    """AC-5.3: the raw full track is absent and no observation property equals the
    raw pace, distance, ascent, or date."""
    summary = _summary()
    _, co_params = _commons(_commit_batch(summary))
    domain = {k: v for k, v in co_params.items() if k not in ("viewer_id", "granted_ids")}
    vals = list(domain.values())
    raw_pace = compute_pace_on_grade(summary)
    assert raw_pace not in vals and str(raw_pace) not in vals
    assert summary.total_distance_m not in vals
    assert summary.total_ascent_m not in vals
    assert not any("2026-06-24" in str(v) for v in vals)  # raw date never crosses
    # the trimmed twin has strictly fewer points than the raw track (full track absent)
    assert co_params["trimmed_track"].count(",") < len(summary.gps_track) - 1


# ── AC-2.5 — atomic rollback: a post-fork failure persists nothing ───────────


def test_s2_ac5_post_fork_failure_rolls_back_all_four() -> None:
    """AC-2.5: with the four writes in one managed transaction, a failure injected
    mid-transaction (at/after the fork) commits NONE of them — neither the
    :Episode nor the :CommonsObservation survives. Models the managed transaction:
    the batch is applied to the store only if the whole work function completes."""
    committed: list[tuple[str, dict]] = []

    def runner(cypher: str, params: dict):
        return []

    def failing_tx(merged: list[tuple[str, dict]]):
        pending: list[tuple[str, dict]] = []
        for i, (cypher, params) in enumerate(merged):
            if i >= 3:  # fail at/after the commons fork (4th statement)
                raise RuntimeError("injected post-fork failure")
            pending.append((cypher, params))
        committed.extend(pending)  # reached only on full success → atomic commit

    session = ScopedSession("mem:josh", [], runner, failing_tx)
    with pytest.raises(RuntimeError):
        create_episode(_summary(), "ct:x", "mem:josh", session, commons_salt=_SALT)
    # rollback: nothing persisted — no Episode, no CommonsObservation
    assert committed == []
    assert not any("Episode" in c for c, _ in committed)
    assert not any("CommonsObservation" in c for c, _ in committed)


def test_s3_ac7_write_path_invokes_no_provider() -> None:
    """AC-3.7: the de-id/commons write path is pure arithmetic — no model/provider
    call (Rule #5). Monkeypatch the provider registry to explode, then run the full
    create_episode commons path; it must complete without resolving a provider, so a
    future edit routing band/bucket derivation through an LLM goes red here."""
    import orchestration.providers.registry as reg

    original = reg.resolve

    def _boom(*args, **kwargs):
        raise AssertionError("a provider was resolved on the commons write path")

    reg.resolve = _boom  # type: ignore[assignment]
    try:
        batch = _commit_batch(_summary())  # runs build_observation + the fork write
    finally:
        reg.resolve = original  # type: ignore[assignment]
    assert any("CommonsObservation" in c for c, _ in batch)  # the fork still fired


def test_s2_ac0_success_commits_all_four_together() -> None:
    """AC-2.0 (success side): on a clean run all four writes land in the one
    committed batch — the atomic counterpart to the rollback test."""
    committed: list[tuple[str, dict]] = []

    def runner(cypher: str, params: dict):
        return []

    def tx_runner(merged: list[tuple[str, dict]]):
        committed.extend(merged)  # commit the whole batch

    session = ScopedSession("mem:josh", [], runner, tx_runner)
    create_episode(_summary(), "ct:old-rag-loop", "mem:josh", session, commons_salt=_SALT)
    kinds = " ".join(c for c, _ in committed)
    assert "MERGE (e:Episode" in kinds
    assert ":DID]->(e)" in kinds
    assert ":ON]->(t)" in kinds
    assert "MERGE (co:CommonsObservation" in kinds
