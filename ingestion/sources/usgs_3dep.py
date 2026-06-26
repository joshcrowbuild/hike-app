"""UsgsThreeDEPSource — the first enrichment source: USGS 3DEP elevation profiles.

The producer half of Epic 017. As an `enrichment` source it never enters the
matcher; post-conflation it samples elevation along each canonical trail's
assembled route (`CanonicalNode.geom_wkt`) and emits `EnrichmentFact`s — the
parallel-array + scalar encoding the loader writes onto `CanonicalTrail` (AC-3.1):

    profile_distances_m, profile_elevations_m,                # the curve (parallel)
    total_gain_m, total_loss_m, max_grade_pct,                # derived scalars
    elev_source, elev_resolution_m, elev_version             # provenance (Rule #7)

The DEM read sits behind the injectable `ElevationSampler` (`elevation.py`), so the
profile math is testable with a fake sampler; `RasterioDEMSampler` is the real
local-raster transport (D1), lazy-importing rasterio/pyproj so importing this
module costs nothing in a DEM-less environment.

Source-or-silence (Rule #1 / D3): a trail with no route, or outside DEM coverage,
gets no facts — the trail's `elevationProfile` is then `null`, never a faked curve.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ingestion.elevation import (
    DEFAULT_MIN_COVERAGE,
    ElevationProfile,
    ElevationSampler,
    build_profile_from_wkt,
)

from .base import CanonicalNode, ConflationRole, CorpusSource, EnrichmentFact, Region, SourceKind

if TYPE_CHECKING:
    from ingestion.conflate.match import Feature
    from orchestration.config import Settings

log = logging.getLogger(__name__)

ELEV_SOURCE = "usgs-3dep"
_DEFAULT_DEM_VERSION = "3dep-1/3-arcsec"


class RasterioDEMSampler:
    """Reads ground elevation from a local DEM raster (D1). Lazy: rasterio/pyproj
    are imported on first use, and the dataset opened once and reused. Returns
    `None` outside the raster's bounds or on nodata — the source-or-silence signal
    the profile builder honors (D3)."""

    def __init__(self, dem_path: str) -> None:
        self._dem_path = dem_path
        self._dataset: object | None = None
        self._to_dem: object | None = None  # WGS84 → DEM-CRS transformer, if needed
        self._nodata: float | None = None

    def _ensure_open(self) -> object:
        if self._dataset is None:
            import rasterio

            dataset = rasterio.open(self._dem_path)
            self._dataset = dataset
            self._nodata = dataset.nodata
            crs = dataset.crs
            if crs is not None and crs.to_epsg() != 4326:
                from pyproj import Transformer

                self._to_dem = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        return self._dataset

    def sample(self, lon: float, lat: float) -> float | None:
        from rasterio.windows import Window

        dataset = self._ensure_open()
        x, y = lon, lat
        if self._to_dem is not None:
            x, y = self._to_dem.transform(lon, lat)  # type: ignore[attr-defined]
        try:
            row, col = dataset.index(x, y)  # type: ignore[attr-defined]
            if not (0 <= row < dataset.height and 0 <= col < dataset.width):  # type: ignore[attr-defined]
                return None
            value = dataset.read(1, window=Window(col, row, 1, 1))[0, 0]  # type: ignore[attr-defined]
        except Exception:
            return None
        fvalue = float(value)
        if self._nodata is not None and fvalue == float(self._nodata):
            return None
        if fvalue != fvalue:  # NaN
            return None
        return fvalue

    def close(self) -> None:
        if self._dataset is not None:
            self._dataset.close()  # type: ignore[attr-defined]
            self._dataset = None


class UsgsThreeDEPSource(CorpusSource):
    name = "usgs-3dep"
    kind = SourceKind.enrichment
    role = ConflationRole.enrich
    authority_tier = 1  # USGS is authoritative for elevation

    def __init__(
        self,
        *,
        sampler: ElevationSampler | None = None,
        resolution_m: float = 20.0,
        dem_version: str = _DEFAULT_DEM_VERSION,
        min_coverage: float = DEFAULT_MIN_COVERAGE,
    ) -> None:
        if resolution_m <= 0:
            # A non-positive spacing is a misconfiguration — fail loud here rather than
            # let it surface later as a swallowed ZeroDivisionError (silent null).
            raise ValueError(f"resolution_m must be positive; got {resolution_m!r}")
        self._sampler = sampler
        self._resolution_m = resolution_m
        self._dem_version = dem_version
        self._min_coverage = min_coverage
        super().__init__()

    @classmethod
    def from_config(cls, settings: Settings) -> UsgsThreeDEPSource:
        # A missing DEM path is a misconfiguration — fail loud here (corpus seam,
        # SS-10), never a silent self-drop.
        if not settings.dem_path:
            raise ValueError(
                "usgs-3dep source requires ADVENTURE_3DEP_DEM (path to a local 3DEP DEM raster)"
            )
        return cls(
            sampler=RasterioDEMSampler(settings.dem_path),
            resolution_m=settings.elev_resolution_m,
        )

    def fetch(self, region: Region) -> list[Feature]:
        raise NotImplementedError(
            f"{type(self).__name__} is an enrichment source and does not fetch"
        )

    def enrich(self, canonical: CanonicalNode) -> list[EnrichmentFact]:
        """Sample 3DEP along the trail's assembled route and emit the profile facts.
        Degrade-and-disclose (rule #6): no sampler, no geometry, no coverage, or a
        sampling error → `[]` (the trail's profile stays `null`)."""
        if self._sampler is None:
            return []
        wkt = getattr(canonical, "geom_wkt", None)
        if not wkt:
            return []
        try:
            profile = build_profile_from_wkt(
                wkt,
                self._sampler,
                resolution_m=self._resolution_m,
                source=ELEV_SOURCE,
                min_coverage=self._min_coverage,
            )
        except Exception as exc:
            log.warning(
                "3DEP enrich failed for %s, degrading to no fact: %s", canonical.canonical_id, exc
            )
            return []
        if profile is None:
            return []
        return self._facts(canonical.canonical_id, profile)

    def _facts(self, canonical_id: str, profile: ElevationProfile) -> list[EnrichmentFact]:
        resolution = f"{self._resolution_m:g}m"

        def fact(attribute: str, value: object) -> EnrichmentFact:
            return EnrichmentFact(
                source=self.name,
                attribute=attribute,
                value=value,
                canonical_id=canonical_id,
                recorded_resolution=resolution,
            )

        # Parallel primitive arrays + scalars (Neo4j has no list-of-map type — AC-3.1).
        return [
            fact("profile_distances_m", profile.distances_m),
            fact("profile_elevations_m", profile.elevations_m),
            fact("total_gain_m", profile.total_gain_m),
            fact("total_loss_m", profile.total_loss_m),
            fact("max_grade_pct", profile.max_grade_pct),
            fact("elev_source", profile.source),
            fact("elev_resolution_m", profile.resolution_m),
            fact("elev_version", self._dem_version),
        ]
