"""EchoSource — a throwaway geometry source proving the one-file drop-in (S6).

The empirical proof of the seam (SS-12): enabling `echo` is *exactly* one new file
(this one) + the registry name-map entry + appending `echo` to
ADVENTURE_CORPUS_SOURCES — with ZERO diff to `run_pipeline`. It returns a small
fixed `Feature` list and passes the shared conformance suite unmodified, so the
modularity claim is asserted, not just designed. `authority_tier=3`: a low-trust
illustrative source, never a spine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shapely.geometry import LineString

from .base import ConflationRole, CorpusSource, Feature, Region, SourceKind

if TYPE_CHECKING:
    from orchestration.config import Settings

_ECHO_FEATURES = [
    Feature(
        name="Echo Ridge Trail",
        geom=LineString([(-78.30, 38.60), (-78.29, 38.61)]),
        source="ECHO",
        ref="echo/1",
    ),
    Feature(
        name="Echo Hollow Loop",
        geom=LineString([(-78.40, 38.50), (-78.39, 38.51)]),
        source="ECHO",
        ref="echo/2",
    ),
]


class EchoSource(CorpusSource):
    name = "echo"
    kind = SourceKind.geometry
    role = ConflationRole.conflate
    authority_tier = 3

    @classmethod
    def from_config(cls, settings: Settings) -> EchoSource:
        return cls()

    def fetch(self, region: Region) -> list[Feature]:
        return list(_ECHO_FEATURES)
