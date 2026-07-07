"""OsmPbfSource — deterministic OSM (pyosmium) geometry spine, behind the
CorpusSource contract.

A thin adapter over `ingestion.fetch.osm_pbf` (local-file, pyosmium-read
transport) — the transport body is untouched. Same declared `role=spine`,
`authority_tier=2` as `OsmSource` (Overpass), so it is a drop-in geometry
spine: `ingestion.sources.registry.spine()` resolves by declared role, not by
name, so naming `"osm-pbf"` instead of `"osm"` in `ADVENTURE_CORPUS_SOURCES` is
all a future cutover needs.

`from_config` mirrors `UsfsSource`'s SS-10 split verbatim: an explicitly-blank
`ADVENTURE_OSM_PBF` fails loud (misconfiguration), an unset one falls back to
the transport's own default path. A *runtime* missing/corrupt file degrades to
`[]` inside `fetch` (rule #6) — the adapter is the degrade boundary. The
transport function is injected (default `ingestion.fetch.osm_pbf.fetch`) so a
test can drive `fetch(region)` with a fake/raising transport, file-free.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ingestion.fetch import osm_pbf as _osm_pbf

from .base import ConflationRole, CorpusSource, Feature, Region, SourceKind

if TYPE_CHECKING:
    from orchestration.config import Settings

log = logging.getLogger(__name__)

_Transport = Callable[..., list[Feature]]


class OsmPbfSource(CorpusSource):
    name = "osm-pbf"
    kind = SourceKind.geometry
    role = ConflationRole.spine
    authority_tier = 2

    def __init__(
        self,
        *,
        pbf_path: Path | str | None = None,
        transport: _Transport = _osm_pbf.fetch,
    ) -> None:
        super().__init__()
        # None → the transport's own default path (data/osm/region.osm.pbf).
        self._pbf_path = pbf_path
        self._transport = transport

    @classmethod
    def from_config(cls, settings: Settings) -> OsmPbfSource:
        raw = settings.osm_pbf_path
        if raw is not None and not str(raw).strip():
            # Explicitly-blank config is a misconfiguration — fail loud (SS-10).
            raise ValueError(
                "ADVENTURE_OSM_PBF is set but blank; unset it to use the "
                "default path, or give a real .osm.pbf path"
            )
        return cls(pbf_path=raw)

    def fetch(self, region: Region) -> list[Feature]:
        # The adapter is the degrade boundary: a missing/corrupt file (or any
        # other runtime failure) returns [] rather than raising (rule #6).
        try:
            return self._transport(region.bbox, pbf_path=self._pbf_path)
        except Exception as exc:
            log.warning("%s fetch failed, degrading to []: %s", self.name, exc)
            return []
