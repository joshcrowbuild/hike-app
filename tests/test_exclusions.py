"""regions/exclusions.json is the source of truth for the trail-filter denylists
(Epic 025) — these tests pin that the module-compiled patterns match the file
verbatim, and that a malformed config fails loud rather than degrading to an
empty (corpus-polluting) denylist."""

from __future__ import annotations

import json
import re

import pytest

from ingestion import trail_filter


def test_ac2_4_module_patterns_match_exclusions_json():
    with open(trail_filter.EXCLUSIONS_PATH) as f:
        data = json.load(f)

    compiled = trail_filter._load_exclusion_patterns()
    for key in ("public_route_ref", "tiger_route_base", "residential_street_suffix", "name_deny"):
        assert compiled[key].pattern == data[key]
        assert compiled[key].flags & re.IGNORECASE


def test_ac2_5_missing_key_raises(tmp_path):
    bad = tmp_path / "exclusions.json"
    bad.write_text(json.dumps({"public_route_ref": r"\d"}))  # missing 3 required keys

    trail_filter._load_exclusion_patterns.cache_clear()
    with pytest.raises(KeyError):
        trail_filter._load_exclusion_patterns(str(bad))


def test_ac2_5_non_string_value_raises(tmp_path):
    bad = tmp_path / "exclusions.json"
    bad.write_text(
        json.dumps(
            {
                "public_route_ref": 123,  # not a string
                "tiger_route_base": r"\d",
                "residential_street_suffix": r"\d",
                "name_deny": r"\d",
            }
        )
    )

    trail_filter._load_exclusion_patterns.cache_clear()
    with pytest.raises(TypeError):
        trail_filter._load_exclusion_patterns(str(bad))


def test_ac2_5_malformed_json_raises(tmp_path):
    bad = tmp_path / "exclusions.json"
    bad.write_text("{not valid json")

    trail_filter._load_exclusion_patterns.cache_clear()
    with pytest.raises(json.JSONDecodeError):
        trail_filter._load_exclusion_patterns(str(bad))


def test_ac2_5_invalid_regex_raises(tmp_path):
    bad = tmp_path / "exclusions.json"
    bad.write_text(
        json.dumps(
            {
                "public_route_ref": "(unclosed",  # invalid regex
                "tiger_route_base": r"\d",
                "residential_street_suffix": r"\d",
                "name_deny": r"\d",
            }
        )
    )

    trail_filter._load_exclusion_patterns.cache_clear()
    with pytest.raises(re.error):
        trail_filter._load_exclusion_patterns(str(bad))


def test_ac2_5_missing_file_raises(tmp_path):
    missing = tmp_path / "does-not-exist.json"

    trail_filter._load_exclusion_patterns.cache_clear()
    with pytest.raises(FileNotFoundError):
        trail_filter._load_exclusion_patterns(str(missing))
