"""Conflation matching — pure scoring + classification (the Stage-3 de-risk core).

For a candidate (OSM, agency) pair: score name similarity (normalized fuzzy) and
geometry agreement (buffer-overlap + Hausdorff), then classify auto-accept /
review / no-match. Thresholds are tunable; calibration against real data is the
spike's job, but the algorithm is unit-tested here on synthetic geometries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry
from thefuzz import fuzz

_LAT_DEG_TO_M = 111_000.0  # metres per degree of latitude (constant)
_LON_DEG_TO_M = 85_000.0  # metres per degree of longitude at ~38°N (111_000 * cos(38°))
_SUFFIXES = re.compile(r"\b(trail|tr|trl|path|road|rd|fr|fs|loop|spur|route)\b")
_NONWORD = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Feature:
    name: str
    geom: BaseGeometry
    source: str = ""
    ref: str | None = None


@dataclass(frozen=True)
class Thresholds:
    name_min: int = 60
    name_auto: int = 85
    buffer_deg: float = 0.0003  # ~30 m
    overlap_auto: float = 0.5
    hausdorff_auto_m: float = 80.0
    hausdorff_review_m: float = 250.0


@dataclass(frozen=True)
class Agreement:
    overlap: float  # buffered-intersection / smaller buffered area
    hausdorff_m: float


@dataclass(frozen=True)
class Match:
    a: Feature
    b: Feature
    name_score: int
    agreement: Agreement
    verdict: str  # "auto-accept" | "review" | "no-match"


_DEFAULT = Thresholds()


def normalize_name(name: str) -> str:
    return _NONWORD.sub(" ", _SUFFIXES.sub(" ", name.lower())).strip()


def name_similarity(a: str, b: str) -> int:
    return int(fuzz.token_sort_ratio(normalize_name(a), normalize_name(b)))


def geometry_agreement(
    a: BaseGeometry, b: BaseGeometry, *, buffer_deg: float = _DEFAULT.buffer_deg
) -> Agreement:
    ba, bb = a.buffer(buffer_deg), b.buffer(buffer_deg)
    denom = min(ba.area, bb.area)
    overlap = (ba.intersection(bb).area / denom) if denom else 0.0
    # hausdorff_distance returns degrees; scale to metres using an aspect-correct
    # approximation (lon degrees are ~30% shorter than lat degrees at 38°N).
    # Average the two scale factors as a simple isotropic correction.
    deg_to_m = (_LAT_DEG_TO_M + _LON_DEG_TO_M) / 2  # ~98 000 m/deg
    return Agreement(overlap=overlap, hausdorff_m=a.hausdorff_distance(b) * deg_to_m)


def classify(name_score: int, agreement: Agreement, thresholds: Thresholds = _DEFAULT) -> str:
    t = thresholds
    geom_strong = agreement.overlap >= t.overlap_auto or agreement.hausdorff_m <= t.hausdorff_auto_m
    if name_score >= t.name_auto and geom_strong:
        return "auto-accept"
    geom_near = agreement.overlap > 0 or agreement.hausdorff_m <= t.hausdorff_review_m
    if name_score >= t.name_min and geom_near:
        return "review"
    return "no-match"


def match(
    a_features: list[Feature], b_features: list[Feature], *, thresholds: Thresholds = _DEFAULT
) -> list[Match]:
    """Cross-score all pairs above the name floor; return non-no-match results."""
    out: list[Match] = []
    for a in a_features:
        for b in b_features:
            score = name_similarity(a.name, b.name)
            if score < thresholds.name_min:  # block on name first (cheap)
                continue
            agreement = geometry_agreement(a.geom, b.geom, buffer_deg=thresholds.buffer_deg)
            verdict = classify(score, agreement, thresholds)
            if verdict != "no-match":
                out.append(Match(a, b, score, agreement, verdict))
    return out
