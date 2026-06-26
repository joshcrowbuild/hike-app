"""Context assembly for engine.plan() — Epic 003.

Assembles a compact personal-context block at query time from:
  - Active Beliefs (decay-filtered, confidence > floor, capped to 20)
  - PhysicalProfile capability summary
  - Relevant Episodes on candidate trails (18-month window, capped to 10)

The assembled string is injected as the `profile` parameter into rank_ids()
so the Curator can make capability-aware, history-aware recommendations without
ever seeing raw biometric data or provisional beliefs.

Rules honored:
  - Rule #4: all three Cypher queries scope on owner_id / viewer_id
  - Rule #7: inferred beliefs labeled as such; stated beliefs as facts
  - AC-5.4: context assembled once per plan() call, passed to one rank_ids() call
  - AC-6: anonymous / unknown viewer returns empty → plan() proceeds unchanged
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

log = logging.getLogger(__name__)

# Limits (per Stage 5 §4)
MAX_BELIEFS = 20
MAX_EPISODES = 10
MAX_CONTEXT_CHARS = 500
CONFIDENCE_FLOOR = 0.4
_EIGHTEEN_MONTHS_DAYS = 548  # 18 months ≈ 548 days


Runner = Any  # Callable[(cypher, params) → list[dict]]


# ── Pure helpers ──────────────────────────────────────────────────────────────


def decayed_confidence(belief: dict) -> float:
    """Compute confidence after exponential decay, consistent with Stage 5 §3."""
    confidence = float(belief.get("confidence") or 0.0)
    if not belief.get("decays"):
        return confidence
    last_updated = belief.get("last_updated_at")
    half_life = int(belief.get("decay_half_life_days") or 90)
    if last_updated is None or half_life <= 0:
        return confidence
    # Normalise: Neo4j Date objects and Python date objects both support subtraction
    if hasattr(last_updated, "to_native"):
        last_updated = last_updated.to_native()  # Neo4j Date → Python date
    age_days = (date.today() - last_updated).days
    return confidence * (0.5 ** (age_days / half_life))


# ── Cypher queries ────────────────────────────────────────────────────────────


def fetch_beliefs(viewer_id: str, runner: Runner) -> list[dict]:
    """Fetch active Beliefs for the viewer, decay-filtered and capped to MAX_BELIEFS.

    AC-1.1: Only beliefs with decayed_confidence > CONFIDENCE_FLOOR are returned.
    AC-1.2: Provisional beliefs (confidence=0.3, corr_n<3) are excluded.
    AC-1.3: Query scoped to viewer_id (Rule #4).
    AC-1.4: Capped at MAX_BELIEFS.
    AC-1.5: Empty list on no results — no crash.
    """
    rows = runner(
        (
            "MATCH (b:Belief) "
            "WHERE b.owner_id = $viewer_id "
            "RETURN b.key AS key, b.value AS value, b.axis AS axis, b.type AS type, "
            "       b.confidence AS confidence, b.corroboration_n AS corroboration_n, "
            "       b.decays AS decays, b.decay_half_life_days AS decay_half_life_days, "
            "       b.last_updated_at AS last_updated_at "
            "ORDER BY b.last_updated_at DESC "
            "LIMIT $limit",
            {"viewer_id": viewer_id, "limit": MAX_BELIEFS * 3},  # over-fetch for decay filter
        )
    )

    active = [b for b in (rows or []) if decayed_confidence(b) > CONFIDENCE_FLOOR]
    return active[:MAX_BELIEFS]


def fetch_profile(viewer_id: str, runner: Runner) -> dict | None:
    """Fetch the viewer's PhysicalProfile capability summary.

    AC-2.1: Scoped to viewer_id (Rule #4).
    AC-2.2: Returns None when no profile exists.
    AC-2.3: Never reads raw biometric time series.
    """
    rows = runner(
        (
            "MATCH (pp:PhysicalProfile) "
            "WHERE pp.owner_id = $viewer_id "
            "RETURN pp.pace_on_grade AS pace_on_grade, "
            "       pp.max_distance_m AS max_distance_m, "
            "       pp.max_ascent_m AS max_ascent_m, "
            "       pp.episode_count AS episode_count",
            {"viewer_id": viewer_id},
        )
    )
    if not rows:
        return None
    return dict(rows[0])


def fetch_relevant_episodes(
    viewer_id: str,
    candidate_ids: list[str],
    runner: Runner,
) -> list[dict]:
    """Fetch recent Episodes on candidate trails (18-month window, capped at MAX_EPISODES).

    AC-3.1: Filtered to candidate_ids.
    AC-3.2: 18-month date cap.
    AC-3.3: Capped at MAX_EPISODES.
    AC-3.4: Scoped to viewer_id (Rule #4).
    AC-3.5: Empty list when no episodes — no crash.
    """
    if not candidate_ids:
        return []

    cutoff = date.today() - timedelta(days=_EIGHTEEN_MONTHS_DAYS)
    rows = runner(
        (
            "MATCH (p:Person {member_id: $viewer_id})-[:DID]->(e:Episode)"
            "-[:ON]->(t:CanonicalTrail) "
            "WHERE e.owner_id = $viewer_id "
            "  AND t.canonical_id IN $candidate_ids "
            "  AND e.date >= $cutoff "
            "RETURN t.name AS trail_name, e.date AS date, e.overall_outcome AS overall "
            "ORDER BY e.date DESC "
            "LIMIT $limit",
            {
                "viewer_id": viewer_id,
                "candidate_ids": candidate_ids,
                "cutoff": cutoff,
                "limit": MAX_EPISODES,
            },
        )
    )
    return list(rows or [])[:MAX_EPISODES]


# ── Assembly ─────────────────────────────────────────────────────────────────


def assemble_context(
    beliefs: list[dict],
    profile: dict | None,
    episodes: list[dict],
) -> str:
    """Assemble a compact personal-context string for the Curator's rank_ids() call.

    AC-4.2: Returns "" when all inputs are empty (anonymous / no data path).
    AC-4.3: Never includes raw biometric fields (HR time series, VO2max, sleep).
    AC-4.4: stated beliefs as facts; inferred beliefs qualified.
    AC-4.5: Output capped at MAX_CONTEXT_CHARS.
    """
    if not beliefs and profile is None and not episodes:
        return ""

    parts: list[str] = ["[PERSONAL CONTEXT — private, not for disclosure]"]

    # Capability summary (profile)
    if profile:
        pace = profile.get("pace_on_grade")
        max_dist_km = (profile.get("max_distance_m") or 0) / 1000
        max_asc = profile.get("max_ascent_m")
        cap_parts = []
        if pace:
            cap_parts.append(f"pace ~{pace:.1f} min/km on moderate grade")
        if max_dist_km:
            cap_parts.append(f"max {max_dist_km:.0f}km")
        if max_asc:
            cap_parts.append(f"max {max_asc:.0f}m ascent")
        if cap_parts:
            parts.append(f"Capability: {', '.join(cap_parts)}.")

    # Preferences from beliefs
    prefs_stated = [
        b for b in beliefs if b.get("axis") == "preference" and b.get("type") == "stated"
    ]
    prefs_inferred = [
        b for b in beliefs if b.get("axis") == "preference" and b.get("type") == "inferred"
    ]
    if prefs_stated:
        values = ", ".join(b.get("key", "?").replace("_", " ") for b in prefs_stated[:3])
        parts.append(f"Stated preferences: {values}.")
    if prefs_inferred:
        values = ", ".join(b.get("key", "?").replace("_", " ") for b in prefs_inferred[:3])
        parts.append(f"Inferred from past hikes: {values}.")

    # Prior visits
    if episodes:
        visit_parts = []
        for ep in episodes[:3]:
            name = ep.get("trail_name", "unknown trail")
            d = ep.get("date")
            visit_parts.append(f"{name} visited {d}" if d else name)
        parts.append(f"Prior visits: {'; '.join(visit_parts)}.")

    parts.append("[END PERSONAL CONTEXT]")

    result = "\n".join(parts)
    if len(result) > MAX_CONTEXT_CHARS:
        result = result[: MAX_CONTEXT_CHARS - 3] + "..."
    return result
