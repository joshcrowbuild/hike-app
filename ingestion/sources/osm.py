"""OsmSource — OSM (Overpass) geometry spine, behind the CorpusSource contract.

A thin adapter over the existing `ingestion.fetch.osm` transport (Overpass HTTP
with mirror failover) — the transport body is untouched (AC-3.5). OSM is the
geometry spine, but `role=spine` is now a *declaration* the registry reads, not
feature-set `a` hardcoded in the pipeline (SS-3). Keyless: `from_config` needs no
secret. An injectable client keeps tests network-free.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from ingestion.fetch import osm as _osm

from .base import ConflationRole, CorpusSource, Feature, Region, SourceKind

if TYPE_CHECKING:
    from orchestration.config import Settings

log = logging.getLogger(__name__)


class OsmSource(CorpusSource):
    name = "osm"
    kind = SourceKind.geometry
    role = ConflationRole.spine
    authority_tier = 2

    def __init__(self, *, client: httpx.Client | None = None, timeout: float = 90.0) -> None:
        super().__init__()
        self._client = client
        self._timeout = timeout

    @classmethod
    def from_config(cls, settings: Settings) -> OsmSource:
        # Keyless; nothing to pull from the secrets store.
        return cls()

    def fetch(self, region: Region) -> list[Feature]:
        # The adapter is the degrade boundary: any runtime failure (incl. a
        # malformed-200 the transport doesn't guard) returns [] (rule #6, AC-3.3).
        try:
            return _osm.fetch(region.bbox, client=self._client, timeout=self._timeout)
        except Exception as exc:
            log.warning("%s fetch failed, degrading to []: %s", self.name, exc)
            return []
