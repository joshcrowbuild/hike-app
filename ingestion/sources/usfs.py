"""UsfsSource — USFS NFS trails (local bulk GeoJSON) behind the CorpusSource contract.

A thin adapter over the existing `ingestion.fetch.usfs` transport (local-file,
bbox-clipped) — body untouched (AC-3.5). The USFS EDW REST service 403s from
non-USFS IPs (decision-log-additions-proposed §34), so USFS ingests from a local
GeoJSON whose path is the adapter's private `from_config` detail (read from
`Settings`, never hardcoded — rule #10).

`from_config` fails loud (ValueError) only on an explicitly-blank path
configuration; an unset path falls back to the fetcher's default. A *runtime*
missing/corrupt file degrades to `[]` inside `fetch` (rule #6) — so the default
pipeline runs even before the multi-GB national file is downloaded.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ingestion.fetch import usfs as _usfs

from .base import ConflationRole, CorpusSource, Feature, Region, SourceKind

if TYPE_CHECKING:
    from orchestration.config import Settings

log = logging.getLogger(__name__)


class UsfsSource(CorpusSource):
    name = "usfs"
    kind = SourceKind.geometry
    role = ConflationRole.conflate
    authority_tier = 1

    def __init__(self, *, geojson_path: Path | str | None = None) -> None:
        super().__init__()
        # None → the transport's own default path (data/usfs/trails.geojson).
        self._geojson_path = geojson_path

    @classmethod
    def from_config(cls, settings: Settings) -> UsfsSource:
        raw = settings.usfs_geojson_path
        if raw is not None and not str(raw).strip():
            # Explicitly-blank config is a misconfiguration — fail loud (SS-10).
            raise ValueError(
                "ADVENTURE_USFS_GEOJSON is set but blank; unset it to use the "
                "default path, or give a real GeoJSON path"
            )
        return cls(geojson_path=raw)

    def fetch(self, region: Region) -> list[Feature]:
        # The adapter is the degrade boundary: a missing/corrupt file (or any other
        # runtime failure) returns [] rather than raising (rule #6, AC-3.3).
        try:
            return _usfs.fetch(region.bbox, geojson_path=self._geojson_path)
        except Exception as exc:
            log.warning("%s fetch failed, degrading to []: %s", self.name, exc)
            return []
