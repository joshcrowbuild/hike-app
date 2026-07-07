"""Corpus-source registry — config-driven, mirroring the model + watch registries.

The single place that knows which corpus sources exist. `run_pipeline` iterates
the list `enabled_sources` returns and never names a source literally again (the
modularity guarantee — source-seams §6). Resolution is via each source's
`from_config` classmethod, so the name map points *at* `from_config` rather than
at the standalone factory functions the older registries use (the deliberate
SS-1 departure). `spine()` makes OSM-as-spine a validated declaration, not an
assumption (SS-3).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from orchestration.config import Settings

from .base import ConflationRole, CorpusSource, SourceKind
from .echo import EchoSource
from .nps import NpsSource
from .osm import OsmSource
from .osm_pbf import OsmPbfSource
from .usfs import UsfsSource
from .usgs_3dep import UsgsThreeDEPSource

# name -> CorpusSource subclass. Add a source here to register it (step 3 of the
# §6 checklist). `echo` is the throwaway drop-in proof (S6). `usgs-3dep` is the
# first ENRICHMENT source (Epic 017) — a default member of ADVENTURE_CORPUS_SOURCES
# so a re-ingest always re-applies elevation; regions without a DEM configured
# (ADVENTURE_3DEP_DEM) degrade to a no-op via `from_config` rather than failing.
# `osm-pbf` (Epic 036) is a second, deterministic geometry-spine transport
# (pyosmium over a local Geofabrik extract) — additive: registered here but NOT
# a member of the default ADVENTURE_CORPUS_SOURCES tuple (orchestration.config),
# so `"osm"` (Overpass) stays the default spine and nothing in the shipped
# default pipeline calls it yet.
SOURCE_REGISTRY: dict[str, type[CorpusSource]] = {
    "osm": OsmSource,
    "osm-pbf": OsmPbfSource,
    "nps": NpsSource,
    "usfs": UsfsSource,
    "echo": EchoSource,
    "usgs-3dep": UsgsThreeDEPSource,
}


def known_source_names() -> list[str]:
    """The registered source names — the CLI `--source` choices derive from this
    so the choice list is never a literal (AC-2.5)."""
    return list(SOURCE_REGISTRY)


def enabled_sources(
    settings: Settings, *, names: Sequence[str] | None = None
) -> list[CorpusSource]:
    """Instantiate the sources named in ADVENTURE_CORPUS_SOURCES (or the explicit
    `names` override the CLI `--source` flag passes), via each source's
    `from_config`. Order follows the config order (AC-2.1). An unknown name raises
    `ValueError` at the registry boundary, naming the offender (AC-2.2)."""
    wanted = list(settings.corpus_sources) if names is None else list(names)
    out: list[CorpusSource] = []
    for name in wanted:
        cls = SOURCE_REGISTRY.get(name)
        if cls is None:
            known = ", ".join(sorted(SOURCE_REGISTRY)) or "(none)"
            raise ValueError(
                f"Unknown corpus source {name!r} in ADVENTURE_CORPUS_SOURCES. Known: {known}"
            )
        out.append(cls.from_config(settings))
    return out


def spine(sources: Iterable[CorpusSource]) -> CorpusSource:
    """The one geometry source declaring `role=spine`. Raises `ValueError` if zero
    or more than one geometry source claims it — a region must have exactly one
    geometry spine (SS-3, AC-2.3)."""
    spines = [
        s for s in sources if s.kind is SourceKind.geometry and s.role is ConflationRole.spine
    ]
    if len(spines) != 1:
        names = ", ".join(s.name for s in spines) or "(none)"
        raise ValueError(
            f"exactly one geometry source must declare role=spine; found {len(spines)} ({names})"
        )
    return spines[0]
