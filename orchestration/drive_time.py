"""Origin-relative drive-time pre-filter (Epic 013 S5, absorbing Epic 005).

Drive time is a function of *(origin, trailhead)*, not a point condition, so it
cannot ride the per-point `verify()` loop (Decision 1.1). This module sits between
Scout and the Verifier: it bounds the candidate set to what is actually reachable in
time (one isochrone call to prune, one K-target matrix call for exact per-candidate
times — Decision 1.3) and folds a sourced drive-time `VerifiedFact` onto each
survivor. Everything degrades-and-discloses: a router outage keeps every candidate
(crow-flies radius is then the only bound) with no fabricated time (Rules #1/#6).
Nothing here is ever written to the graph — drive time is origin-relative (Rule #3).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from orchestration.adapters.base import DriveTimeComputer, LatLon, VerifiedFact
from orchestration.intent import Intent
from orchestration.scout import Candidate

DRIVE_UNAVAILABLE = "Drive times unavailable this run; showing all trails within range."


def time_budget_s(intent: Intent, *, radius_m: float, drive_speed_kmh: float) -> float:
    """A stated time wins; otherwise derive the budget from the radius via the
    configured road speed (Decision 1.5). Always positive."""
    if intent.time_budget_s is not None:
        return float(intent.time_budget_s)
    speed_m_s = max(0.1, drive_speed_kmh * 1000.0 / 3600.0)
    return radius_m / speed_m_s


def _drive_seconds(fact: VerifiedFact) -> float | None:
    value = fact.value
    if isinstance(value, dict):
        secs = value.get("drive_seconds")
        if isinstance(secs, (int, float)) and not isinstance(secs, bool):
            return float(secs)
    return None


def point_in_polygon(pt: LatLon, polygon: list[LatLon]) -> bool:
    """Ray-casting point-in-polygon on (lat, lon). Boundary is best-effort; the exact
    ≤-budget guarantee (AC-4.3) lives in the matrix-only path."""
    if len(polygon) < 3:
        return False
    lat, lon = pt
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]
        denom = (lat_j - lat_i) or 1e-12
        if (lat_i > lat) != (lat_j > lat) and lon < (lon_j - lon_i) * (lat - lat_i) / denom + lon_i:
            inside = not inside
        j = i
    return inside


@dataclass(frozen=True)
class DriveTimeResult:
    kept: list[Candidate]
    facts_by_id: dict[str, VerifiedFact]  # canonical_id -> drive_time fact (survivors only)
    disclosure: str | None  # set once when the router gave nothing (degrade — AC-6.4)


def prefilter(
    origin: LatLon,
    candidates: list[Candidate],
    computer: DriveTimeComputer,
    budget_s: float,
    *,
    coord_of: Callable[[Candidate], LatLon | None],
) -> DriveTimeResult:
    """Prune candidates to those reachable within `budget_s` and attach each survivor's
    drive-time fact. Candidates with no own point are kept un-routed (no fabricated
    0-min, Decision 1.2). A router outage keeps everyone, no times, one disclosure."""
    with_coords: list[tuple[Candidate, LatLon]] = []
    no_coord: list[Candidate] = []
    for c in candidates:
        coord = coord_of(c)
        if coord is None:
            no_coord.append(c)  # keep, never route to the origin (no fabricated 0-min)
        else:
            with_coords.append((c, coord))

    if not with_coords:
        return DriveTimeResult(kept=list(no_coord), facts_by_id={}, disclosure=None)

    polygon = computer.isochrone(origin, budget_s)  # at most one /isochrone call
    if polygon:
        survivors = [(c, xy) for c, xy in with_coords if point_in_polygon(xy, polygon)]
    else:
        survivors = with_coords  # matrix-only fallback: prune by computed time below

    facts = computer.matrix(origin, [xy for _, xy in survivors])  # at most one matrix call
    # A genuine router outage is "no isochrone AND no matrix data at all" — NOT a
    # legitimate full prune (every candidate over budget, or all outside the isochrone),
    # which also leaves facts empty but is a correct, drive-time-bounded result. Only a
    # true outage falls back to the crow-flies radius + discloses.
    router_responded = bool(polygon) or any(fact is not None for fact in facts)
    if not router_responded:
        return DriveTimeResult(
            kept=[c for c, _ in with_coords] + no_coord,  # crow-flies is the only bound
            facts_by_id={},
            disclosure=DRIVE_UNAVAILABLE,
        )

    facts_by_id: dict[str, VerifiedFact] = {}
    kept_coord: list[Candidate] = []
    for (c, _xy), fact in zip(survivors, facts):
        if fact is None:
            kept_coord.append(c)  # absence of a time is never "too far" (degrade — AC-6.5)
            continue
        if not polygon:
            secs = _drive_seconds(fact)
            if secs is not None and secs > budget_s:
                continue  # matrix-only path: drop over-budget (≤ retained — AC-4.3)
        facts_by_id[c.canonical_id] = fact
        kept_coord.append(c)

    return DriveTimeResult(kept=kept_coord + no_coord, facts_by_id=facts_by_id, disclosure=None)
