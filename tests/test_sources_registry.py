"""Epic 012 S2 — config-driven registry: enabled_sources, spine, config parsing.

Mirrors the bar the gap-audit names: a real contract + a config-driven registry
resolving by name, raising at the boundary on an unknown name (exactly as
watch/registry.enabled_adapters and providers/registry._build do).
"""

from __future__ import annotations

import pytest

from ingestion.sources.base import ConflationRole, CorpusSource, SourceKind
from ingestion.sources.echo import EchoSource
from ingestion.sources.nps import NpsSource
from ingestion.sources.osm import OsmSource
from ingestion.sources.registry import (
    enabled_sources,
    known_source_names,
    spine,
)
from orchestration.config import Settings

# ── AC-2.4 — Settings parses ADVENTURE_CORPUS_SOURCES (default preserved) ──────


def test_ac2_4_default_when_absent():
    s = Settings.from_env({})
    assert s.corpus_sources == ("osm", "nps", "usfs", "usgs-3dep")


def test_ac2_4_parses_comma_separated():
    s = Settings.from_env({"ADVENTURE_CORPUS_SOURCES": "osm, nps , echo"})
    assert s.corpus_sources == ("osm", "nps", "echo")


def test_ac2_4_usfs_path_read_from_settings():
    s = Settings.from_env({"ADVENTURE_USFS_GEOJSON": "/data/trails.geojson"})
    assert s.usfs_geojson_path == "/data/trails.geojson"


def test_ac2_4_usfs_path_none_when_unset():
    assert Settings.from_env({}).usfs_geojson_path is None


# ── AC-2.1 — enabled_sources: one instance per name, order follows config ──────


def test_ac2_1_resolves_in_config_order():
    s = Settings.from_env({"ADVENTURE_CORPUS_SOURCES": "nps,osm,echo"})
    srcs = enabled_sources(s)
    assert [x.name for x in srcs] == ["nps", "osm", "echo"]
    assert all(isinstance(x, CorpusSource) for x in srcs)


def test_ac2_1_default_resolves_four_sources():
    # No ADVENTURE_3DEP_DEM configured — usgs-3dep still resolves (it degrades to
    # a no-op sampler in from_config rather than raising; see test_usgs_3dep.py).
    srcs = enabled_sources(Settings.from_env({}))
    assert [x.name for x in srcs] == ["osm", "nps", "usfs", "usgs-3dep"]


def test_ac2_1_names_override_for_cli_source_flag():
    s = Settings.from_env({})  # default osm,nps,usfs
    srcs = enabled_sources(s, names=["osm"])
    assert [x.name for x in srcs] == ["osm"]


# ── AC-2.2 — unknown name raises at the registry boundary, naming the offender ─


def test_ac2_2_unknown_source_raises_naming_it():
    s = Settings.from_env({"ADVENTURE_CORPUS_SOURCES": "osm,bogus"})
    with pytest.raises(ValueError, match="bogus"):
        enabled_sources(s)


# ── AC-2.5 (partial) — CLI choices derive from the registry's known names ──────


def test_known_source_names_lists_registered():
    names = known_source_names()
    assert set(names) >= {"osm", "nps", "usfs", "echo"}


# ── AC-2.3 / AC-4.4 — spine: exactly one role=spine, else ValueError ───────────


def test_ac2_3_spine_returns_the_one_spine():
    srcs = enabled_sources(Settings.from_env({}))
    assert spine(srcs).name == "osm"
    assert spine(srcs).role is ConflationRole.spine


def test_ac2_3_zero_spines_raises():
    # echo + nps are both role=conflate → no spine.
    with pytest.raises(ValueError, match="exactly one geometry source"):
        spine([EchoSource(), NpsSource()])


def test_ac4_4_two_spines_raises():
    class SecondSpine(OsmSource):
        name = "osm2"
        role = ConflationRole.spine

    with pytest.raises(ValueError, match="exactly one geometry source"):
        spine([OsmSource(), SecondSpine()])


def test_ac4_4_default_config_has_exactly_one_spine():
    srcs = enabled_sources(Settings.from_env({}))
    spines = [s for s in srcs if s.kind is SourceKind.geometry and s.role is ConflationRole.spine]
    assert len(spines) == 1
