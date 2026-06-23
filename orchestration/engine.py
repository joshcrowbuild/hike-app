"""The Phase-0 engine: Scout -> Verifier -> Curator (code-orchestrated workflow).

A fixed, authored DAG — not an autonomous agent (Stage 4 §1):

    Scout    - scoped Cypher candidate generation (graph), capped to top-K.
    Verifier - JIT live probes; source-or-silence in code; never persisted (#3).
    Curator  - hard guardrail filter (here) + judgment-tier taste ranking (later).

`plan_from_origin` composes Scout -> Verifier -> guardrail-filter and is testable
with a fake session + fake probes. Two pieces are still TODO and need a live
environment / the provider seam: the free-text `plan` entrypoint (intent -> origin)
and the taste/novelty/party ranking — results are distance-ordered until then.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graph.client import ScopedSession
from orchestration.adapters.base import VerifiedFact
from orchestration.confidence import Confidence, for_fact
from orchestration.config import Settings
from orchestration.curator import GuardrailVerdict, evaluate_guardrails, rank_ids
from orchestration.providers.base import ModelProvider
from orchestration.scout import Candidate, scout
from orchestration.verifier import Probe, verify


@dataclass(frozen=True)
class PlannedTrail:
    candidate: Candidate
    facts: dict[str, VerifiedFact]
    confidences: dict[str, Confidence]
    verdict: GuardrailVerdict


def _latlon(point: Any) -> tuple[float, float] | None:
    if point is None:
        return None
    lat = getattr(point, "latitude", None)
    lon = getattr(point, "longitude", None)
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    if isinstance(point, dict) and "latitude" in point and "longitude" in point:
        return float(point["latitude"]), float(point["longitude"])
    if isinstance(point, (tuple, list)) and len(point) == 2:
        return float(point[0]), float(point[1])
    return None


def plan_from_origin(
    lat: float,
    lon: float,
    session: ScopedSession,
    probes: dict[str, Probe],
    *,
    k: int = 10,
) -> list[PlannedTrail]:
    """Scout near (lat, lon), verify each candidate's conditions, drop any that
    trip a hard guardrail. Distance-ordered (taste ranking is added later)."""
    planned: list[PlannedTrail] = []
    for candidate in scout(lat, lon, session, k=k):
        clat, clon = _latlon(candidate.point) or (lat, lon)
        facts = verify(clat, clon, probes)
        verdict = evaluate_guardrails(facts)
        if verdict.blocked:
            continue  # constraints are hard filters (Stage 4 §6)
        confidences = {kind: for_fact(fact) for kind, fact in facts.items()}
        planned.append(PlannedTrail(candidate, facts, confidences, verdict))
    return planned


def rank_plan(
    planned: list[PlannedTrail],
    provider: ModelProvider,
    model: str,
    *,
    profile: str | None = None,
) -> list[PlannedTrail]:
    """Reorder guardrail-passing trails by the judgment-tier taste ranking. The
    soft half of the Curator; confidence is not an input (rule #2)."""
    by_id = {p.candidate.canonical_id: p for p in planned}
    items = [(p.candidate.canonical_id, p.candidate.name) for p in planned]
    order = rank_ids(items, provider, model, profile=profile)
    return [by_id[cid] for cid in order if cid in by_id]


def plan(query: str, viewer_id: str, settings: Settings) -> object:
    """Free-text entrypoint: parse intent -> origin, then plan_from_origin, then
    apply taste ranking. Needs the provider seam + a live environment — Stage 4."""
    raise NotImplementedError("engine.plan (free-text + taste ranking) is implemented in Stage 4")
