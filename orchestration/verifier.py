"""Verifier — JIT live verification (Stage 4 §4).

Calls a set of point-probes for a candidate's location and keeps only the facts
that actually came back. Source-or-silence (rule #1) is structural: a probe that
returns None contributes nothing — the engine can never surface an unsourced
fact. Live readings are returned, never persisted as graph nodes (rule #3).

`build_probes` wires the Stage-1 adapters from config, including only the sources
whose credentials are present (a missing key = that probe is simply absent, not a
fabricated reading). Drive time (Valhalla) is origin-relative, not a point
condition, so it is handled in ranking rather than here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial

from orchestration.adapters import airnow, firms, nws, ridb, usgs_water
from orchestration.adapters.base import VerifiedFact
from orchestration.config import Settings

Probe = Callable[[float, float], VerifiedFact | None]


def build_probes(settings: Settings) -> dict[str, Probe]:
    probes: dict[str, Probe] = {"water": usgs_water.fetch}  # keyless
    if settings.nws_user_agent:
        probes["weather"] = partial(nws.fetch, user_agent=settings.nws_user_agent)
    if settings.airnow_api_key:
        probes["air"] = partial(airnow.fetch, api_key=settings.airnow_api_key)
    if settings.firms_map_key:
        probes["fire"] = partial(firms.fetch, map_key=settings.firms_map_key)
    if settings.ridb_api_key:
        probes["permits"] = partial(ridb.fetch, api_key=settings.ridb_api_key)
    return probes


def verify(lat: float, lon: float, probes: Mapping[str, Probe]) -> dict[str, VerifiedFact]:
    """Run each probe at (lat, lon); keep only the facts that returned."""
    facts: dict[str, VerifiedFact] = {}
    for kind, probe in probes.items():
        fact = probe(lat, lon)
        if fact is not None:
            facts[kind] = fact
    return facts
