"""NpsSource — NPS trails (ArcGIS FeatureServer) behind the CorpusSource contract.

A thin adapter over the existing `ingestion.fetch.nps` transport (paginated
ArcGIS REST) — body untouched (AC-3.5). NPS is authoritative for existence +
geometry on NPS-managed land (Decision Log §27), so `authority_tier=1`; it
conflates onto the spine (`role=conflate`). Keyless. Injectable client keeps
tests network-free.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from ingestion.fetch import nps as _nps

from .base import ConflationRole, CorpusSource, Feature, Region, SourceKind

if TYPE_CHECKING:
    from orchestration.config import Settings

log = logging.getLogger(__name__)


class NpsSource(CorpusSource):
    name = "nps"
    kind = SourceKind.geometry
    role = ConflationRole.conflate
    authority_tier = 1

    def __init__(self, *, client: httpx.Client | None = None, timeout: float = 60.0) -> None:
        super().__init__()
        self._client = client
        self._timeout = timeout

    @classmethod
    def from_config(cls, settings: Settings) -> NpsSource:
        # Keyless; nothing to pull from the secrets store.
        return cls()

    def fetch(self, region: Region) -> list[Feature]:
        # The adapter is the degrade boundary: any runtime failure returns []
        # rather than raising past the contract (rule #6, AC-3.3).
        try:
            return _nps.fetch(region.bbox, client=self._client, timeout=self._timeout)
        except Exception as exc:
            log.warning("%s fetch failed, degrading to []: %s", self.name, exc)
            return []
