"""CorpusSource seam — the normalized corpus contract (source-seams §2-3, SS-2).

One contract, N source adapters behind it. Every adapter yields the existing
`Feature` (`ingestion.conflate.match`) — this seam wraps proven output rather
than reshaping it (SS-2). The three declarations a source carries do the work the
pipeline used to hardcode:

- `kind` (geometry | enrichment) — geometry features enter conflation; enrichment
  facts join onto already-canonical nodes and never touch the matcher (SS-4).
- `role` (spine | conflate | enrich) — exactly one geometry source declares
  `spine`, which is how OSM-as-spine stops being feature-set `a` hardcoded in
  `run_pipeline` and becomes a property the registry reads (SS-3).
- `authority_tier` (1 | 2 | 3) — a per-source authority *floor* the load loop
  reads instead of special-casing OSM as canonical (SS-4). Per-attribute
  best-view overrides remain in the best-view layer; this scalar is only a floor.

Boundary discipline (rules #1/#6): `fetch()` returns `[]` on any runtime failure
and never raises past the adapter (degrade-and-disclose). A *misconfiguration* —
a missing/blank required path — fails loud inside `from_config` (`ValueError`).
`from_config` always returns a source (never `None`): a corpus source is gated on
its presence in the config list, so absence there is loud, not a silent self-drop
— deliberately asymmetric with the live seam's credential-gated `| None` (SS-10).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from ingestion.conflate.match import Feature

if TYPE_CHECKING:
    from orchestration.config import Settings

# Re-export Feature so adapters import the normalized type from the seam, but it
# stays the SAME object — `Feature is match.Feature` (AC-1.3), never redefined.
__all__ = [
    "CanonicalNode",
    "ConflationRole",
    "CorpusSource",
    "EnrichmentFact",
    "Feature",
    "Region",
    "SourceKind",
]


class SourceKind(Enum):
    """What a source contributes (SS-4). `geometry` produces `Feature`s that enter
    conflation; `enrichment` joins facts onto already-canonical nodes."""

    geometry = "geometry"
    enrichment = "enrichment"


class ConflationRole(Enum):
    """A geometry source's role in conflation (SS-3). Exactly one active geometry
    source declares `spine`; the rest declare `conflate`. Enrichment sources
    declare `enrich` (they never enter the matcher)."""

    spine = "spine"
    conflate = "conflate"
    enrich = "enrich"


@dataclass(frozen=True)
class Region:
    """The geographic scope passed to `fetch`. Carries a bbox today; the same
    object admits a polygon when Stage 3 §2's polygon-clip lands (so adapters take
    a region object, not a loose bbox tuple — AC-1.3). `bbox` is
    (south, west, north, east), matching the fetch layer's convention."""

    region_id: str
    bbox: tuple[float, float, float, float]
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalNode:
    """A just-conflated canonical trail, handed to enrichment sources' `enrich`.
    The minimal identity an enrichment join needs (id + name + a point); enrichment
    sources spatial-join or key-match against it post-conflation (SS-4).

    `geom_wkt` is the node's **assembled route** (Epic 016 S1) when one was
    precomputed — the same line the API serves — so a geometry-consuming enrichment
    source (USGS 3DEP, Epic 017) samples along the trail without re-walking the
    segment graph. `None` when the trail has no route (drives source-or-silence)."""

    canonical_id: str
    name: str
    lat: float | None = None
    lon: float | None = None
    geom_wkt: str | None = None
    # The spine feature's OSM way-type (path|footway|track|…), carried so it can be
    # persisted on the CanonicalTrail. `None` for non-OSM-origin nodes.
    way_type: str | None = None


@dataclass(frozen=True)
class EnrichmentFact:
    """One attribute an enrichment source attaches to a canonical node, carrying
    the provenance + freshness substrate best-view will need when a real
    enrichment source lands (AC-5.4). `recorded_resolution` is the confidence /
    freshness input the design names (e.g. a 3DEP DEM's "10m")."""

    source: str
    attribute: str
    value: Any
    canonical_id: str | None = None
    recorded_resolution: str | None = None


class CorpusSource(ABC):
    """One adapter per corpus source. The transport (Overpass HTTP + mirror
    failover, ArcGIS pagination, a local bulk file, a COG raster sample) is the
    adapter's private business; everything downstream sees one `list[Feature]`.

    Geometry sources implement `fetch`; enrichment sources implement `enrich`
    (and leave `fetch` raising). Construction validates the declared
    `kind`/`role`/`authority_tier` are self-consistent and fail loud otherwise
    (AC-1.4/AC-1.5)."""

    name: str  # "osm" | "nps" | "usfs" | ... — set by each subclass
    kind: SourceKind
    role: ConflationRole
    authority_tier: int  # 1 | 2 | 3 — a per-source authority floor (SS-4)

    def __init__(self) -> None:
        self._validate()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # A geometry source that implements `enrich` but leaves `fetch` un-overridden
        # is a mis-declaration; surface it as ValueError at definition rather than a
        # later abstract-instantiation TypeError (AC-1.5). `__abstractmethods__` is
        # not yet populated at __init_subclass__ time, so detect the override by
        # identity instead.
        kind = getattr(cls, "kind", None)
        if (
            kind is SourceKind.geometry
            and cls.fetch is CorpusSource.fetch
            and cls.enrich is not CorpusSource.enrich
        ):
            raise ValueError(
                f"{cls.__name__} declares kind=geometry but implements enrich, not fetch"
            )

    def _validate(self) -> None:
        if self.authority_tier not in (1, 2, 3):
            raise ValueError(
                f"{type(self).__name__}.authority_tier must be 1, 2, or 3; "
                f"got {self.authority_tier!r}"
            )
        if not isinstance(self.kind, SourceKind):
            raise ValueError(f"{type(self).__name__}.kind must be a SourceKind; got {self.kind!r}")
        if self.kind is SourceKind.geometry:
            if self.role not in (ConflationRole.spine, ConflationRole.conflate):
                raise ValueError(
                    f"{type(self).__name__} is a geometry source; role must be "
                    f"spine or conflate, not {self.role!r}"
                )
        else:  # SourceKind.enrichment
            if self.role is not ConflationRole.enrich:
                raise ValueError(
                    f"{type(self).__name__} is an enrichment source; role must be "
                    f"enrich, not {self.role!r}"
                )
            if type(self).enrich is CorpusSource.enrich:
                raise ValueError(
                    f"{type(self).__name__} is an enrichment source but does not implement enrich()"
                )

    @abstractmethod
    def fetch(self, region: Region) -> list[Feature]:
        """Geometry sources: pull features within `region`. Returns `[]` on any
        runtime failure — never raises past the adapter (rule #6, AC-3.3)."""
        raise NotImplementedError

    def enrich(self, canonical: CanonicalNode) -> list[EnrichmentFact]:
        """Enrichment sources: facts to attach to a just-conflated canonical node.
        Geometry sources leave this raising (AC-5.1)."""
        raise NotImplementedError(f"{type(self).__name__} is a geometry source and does not enrich")

    @classmethod
    def from_config(cls, settings: Settings) -> CorpusSource:
        """Build the source from config — its own paths/keys come from the secrets
        store here (rule #10), never the repo. Always returns a source; a missing
        required path is a misconfiguration that raises `ValueError` here (SS-10).
        Subclasses override; the base default makes the contract explicit."""
        raise NotImplementedError(f"{cls.__name__} must implement from_config")
