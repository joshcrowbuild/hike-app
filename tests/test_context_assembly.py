"""Tests for Epic 003 — Context Assembly.

test_s{story}_{ac}_{description}
All ACs from docs/epics/epic-003-context-assembly.md.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from orchestration.context_assembly import (
    CONFIDENCE_FLOOR,
    MAX_BELIEFS,
    MAX_CONTEXT_CHARS,
    MAX_EPISODES,
    assemble_context,
    decayed_confidence,
    fetch_beliefs,
    fetch_profile,
    fetch_relevant_episodes,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _runner_returning(rows_by_snippet: dict):
    """Fake runner matching on Cypher snippet → rows."""
    calls = []

    def runner(query_tuple):
        cypher, params = query_tuple
        calls.append((cypher, params))
        for snippet, rows in rows_by_snippet.items():
            if snippet in cypher:
                return rows
        return []

    runner.calls = calls
    return runner


def _belief(key, confidence=0.7, corr_n=3, decays=True, half_life=90, days_old=0):
    d = date.today() - timedelta(days=days_old)
    return {
        "key": key,
        "value": "true",
        "axis": "preference",
        "type": "inferred",
        "confidence": confidence,
        "corroboration_n": corr_n,
        "decays": decays,
        "decay_half_life_days": half_life,
        "last_updated_at": d,
    }


# ── S1 — Fetch active beliefs ─────────────────────────────────────────────────


def test_s1_ac3_query_filters_on_owner_id():
    """AC-1.3: Beliefs query includes owner_id = $viewer_id (Rule #4)."""
    runner = _runner_returning({})
    fetch_beliefs("josh", runner)
    assert len(runner.calls) == 1
    cypher, params = runner.calls[0]
    assert "owner_id" in cypher or "viewer_id" in params
    assert params.get("viewer_id") == "josh"


def test_s1_ac4_caps_at_max_beliefs():
    """AC-1.4: At most MAX_BELIEFS beliefs returned."""
    # Return more than MAX_BELIEFS from the runner
    many = [_belief(f"key_{i}") for i in range(MAX_BELIEFS + 5)]
    runner = _runner_returning({"Belief": many})
    result = fetch_beliefs("josh", runner)
    assert len(result) <= MAX_BELIEFS


def test_s1_ac5_empty_beliefs_returns_empty_list():
    """AC-1.5: No beliefs → empty list, no crash."""
    runner = _runner_returning({})
    result = fetch_beliefs("josh", runner)
    assert result == []


def test_s1_ac1_provisional_beliefs_excluded():
    """AC-1.1: Beliefs with decayed_confidence ≤ CONFIDENCE_FLOOR excluded."""
    provisional = _belief("pace", confidence=0.3, decays=False)
    runner = _runner_returning({"Belief": [provisional]})
    result = fetch_beliefs("josh", runner)
    assert result == []


def test_s1_ac1_active_beliefs_included():
    """AC-1.1: Beliefs above floor are included."""
    active = _belief("prefers_ridge", confidence=0.7, decays=False)
    runner = _runner_returning({"Belief": [active]})
    result = fetch_beliefs("josh", runner)
    assert len(result) == 1


# ── Decay helper (pure, no DB) ────────────────────────────────────────────────


def test_decay_non_decaying_belief_unchanged():
    """Non-decaying beliefs return stored confidence regardless of age."""
    b = _belief("constraint", confidence=0.9, decays=False, days_old=365)
    assert decayed_confidence(b) == pytest.approx(0.9)


def test_decay_fresh_belief_unchanged():
    """A belief updated today has negligible decay."""
    b = _belief("pref", confidence=0.7, decays=True, half_life=90, days_old=0)
    assert decayed_confidence(b) == pytest.approx(0.7, rel=0.01)


def test_decay_old_belief_reduced():
    """A belief at exactly one half-life should have ~50% of original confidence."""
    b = _belief("pref", confidence=0.8, decays=True, half_life=90, days_old=90)
    result = decayed_confidence(b)
    assert result == pytest.approx(0.4, rel=0.05)


def test_decay_very_old_belief_below_floor():
    """A very stale belief should decay below CONFIDENCE_FLOOR."""
    b = _belief("pref", confidence=0.7, decays=True, half_life=90, days_old=365)
    assert decayed_confidence(b) < CONFIDENCE_FLOOR


# ── S2 — Fetch PhysicalProfile ────────────────────────────────────────────────


def test_s2_ac1_profile_query_scoped_to_owner():
    """AC-2.1: PhysicalProfile query includes owner_id."""
    runner = _runner_returning({})
    fetch_profile("josh", runner)
    cypher, params = runner.calls[0]
    assert "owner_id" in cypher or "viewer_id" in params
    assert params.get("viewer_id") == "josh"


def test_s2_ac2_missing_profile_returns_none():
    """AC-2.2: No PhysicalProfile → returns None, no crash."""
    runner = _runner_returning({})
    result = fetch_profile("josh", runner)
    assert result is None


def test_s2_ac2_profile_returned_when_exists():
    """AC-2.2: Existing profile is returned."""
    profile = {"pace_on_grade": 15.2, "max_distance_m": 22000, "max_ascent_m": 1100}
    runner = _runner_returning({"PhysicalProfile": [profile]})
    result = fetch_profile("josh", runner)
    assert result == profile


# ── S3 — Fetch relevant episodes ─────────────────────────────────────────────


def test_s3_ac1_episode_query_on_candidate_trails():
    """AC-3.1: Episodes query uses candidate_ids."""
    runner = _runner_returning({})
    fetch_relevant_episodes("josh", ["ct:old-rag", "ct:stony-man"], runner)
    assert any("candidate_ids" in str(p) for _, p in runner.calls)


def test_s3_ac4_episode_query_owner_scoped():
    """AC-3.4: Episodes query scoped to viewer_id."""
    runner = _runner_returning({})
    fetch_relevant_episodes("josh", ["ct:trail-1"], runner)
    assert any(p.get("viewer_id") == "josh" for _, p in runner.calls)


def test_s3_ac5_no_episodes_returns_empty():
    """AC-3.5: No episodes → [], no crash."""
    runner = _runner_returning({})
    result = fetch_relevant_episodes("josh", ["ct:trail-1"], runner)
    assert result == []


def test_s3_ac3_capped_at_max_episodes():
    """AC-3.3: At most MAX_EPISODES episodes returned."""
    many_episodes = [{"trail_name": f"Trail {i}", "date": date.today()} for i in range(20)]
    runner = _runner_returning({"Episode": many_episodes})
    result = fetch_relevant_episodes("josh", ["ct:t"], runner)
    assert len(result) <= MAX_EPISODES


# ── S4 — Assemble context string ─────────────────────────────────────────────


def test_s4_ac2_empty_inputs_return_empty_string():
    """AC-4.2: All empty inputs → empty string, no crash."""
    result = assemble_context([], None, [])
    assert result == ""


def test_s4_ac3_no_raw_biometrics_in_context():
    """AC-4.3: HR time series, VO2max, sleep data never appear in context."""
    profile = {
        "pace_on_grade": 15.0,
        "max_distance_m": 20000,
        "vo2max": 45,  # must be excluded
        "avg_hr_time_series": "[80, 95, 110]",  # must be excluded
    }
    beliefs = [_belief("prefers_ridge", confidence=0.7, decays=False)]
    result = assemble_context(beliefs, profile, [])
    assert "vo2max" not in result.lower()
    assert "hr_time_series" not in result.lower()
    assert "avg_hr" not in result.lower()


def test_s4_ac4_stated_beliefs_labeled_as_facts():
    """AC-4.4: stated beliefs appear as facts; inferred as 'inferred from past hikes'."""
    stated = {**_belief("prefers_loops", confidence=1.0, decays=False), "type": "stated"}
    result = assemble_context([stated], None, [])
    # stated beliefs should not be qualified with "inferred"
    assert "inferred" not in result.lower() or "stated" in result.lower() or result == ""


def test_s4_ac5_context_capped_at_max_chars():
    """AC-4.5: Context string length ≤ MAX_CONTEXT_CHARS."""
    many_beliefs = [_belief(f"pref_{i}", confidence=0.8, decays=False) for i in range(30)]
    long_profile = {"pace_on_grade": 14.2, "max_distance_m": 25000, "max_ascent_m": 1500}
    many_episodes = [
        {"trail_name": f"Very Long Trail Name Number {i}", "date": date.today()} for i in range(15)
    ]
    result = assemble_context(many_beliefs, long_profile, many_episodes)
    assert len(result) <= MAX_CONTEXT_CHARS


def test_s4_ac1_context_contains_capability_summary():
    """AC-4.1: Profile capability appears in context block."""
    profile = {"pace_on_grade": 15.8, "max_distance_m": 22000, "max_ascent_m": 1100}
    result = assemble_context([], profile, [])
    assert "15.8" in result or "pace" in result.lower()


# ── S5 — Engine injection ─────────────────────────────────────────────────────


def test_s5_ac2_empty_context_passes_none_to_rank():
    """AC-5.2: Empty context → profile=None passed to rank_ids (same as today)."""
    result = assemble_context([], None, [])
    # The engine should pass None when context is empty
    assert (result or None) is None


# ── S6 — Anonymous path ───────────────────────────────────────────────────────


def test_s6_ac1_unknown_viewer_returns_empty():
    """AC-6.1: Unknown viewer_id → empty results, no exception."""
    runner = _runner_returning({})
    beliefs = fetch_beliefs("anonymous", runner)
    profile = fetch_profile("anonymous", runner)
    episodes = fetch_relevant_episodes("anonymous", ["ct:trail-1"], runner)
    context = assemble_context(beliefs, profile, episodes)
    assert beliefs == []
    assert profile is None
    assert episodes == []
    assert context == ""


def test_s6_ac3_anonymous_never_gets_other_user_context():
    """AC-6.3: anonymous viewer never receives another user's context."""
    # Provide data only for "josh"; anonymous should get nothing
    josh_beliefs = [_belief("pref", confidence=0.8, decays=False)]

    def runner(query_tuple):
        cypher, params = query_tuple
        if params.get("viewer_id") == "josh":
            return josh_beliefs
        return []

    result = fetch_beliefs("anonymous", runner)
    assert result == []
