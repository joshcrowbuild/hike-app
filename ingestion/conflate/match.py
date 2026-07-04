"""Conflation matching — pure scoring + classification (the Stage-3 de-risk core).

For a candidate (OSM, agency) pair: score name similarity (normalized fuzzy) and
geometry agreement (buffer-overlap + Hausdorff + containment), then classify
auto-accept / review / no-match. `match()` returns the single best OSM candidate
per agency feature (argmax), not every passing pair.

Redesign (Wave-2 adversarial-review response): the old matcher was structurally
broken for agency↔OSM conflation. Two root causes and their fixes:

  1. NAME NORMALISATION. The old scorer reused the pipeline's `normalize_name`,
     which strips *discriminating* suffixes (spur/loop) but keeps *generic*
     qualifiers (National/Scenic/Recreation) — exactly backwards for matching.
     Result: "Appalachian National Scenic Trail" scored ~58 against OSM
     "Appalachian Trail" and never conflated. `normalize_for_match` (matcher-local,
     distinct from `normalize_name`) strips generic qualifiers, expands true
     abbreviations, and KEEPS discriminating suffixes so a spur can't be stamped
     with its parent trail's authoritative name.

  2. DECISION RULE. The old `match()` emitted ALL passing pairs (no argmax) behind
     a hard name<60 prefilter that blocked geometry evaluation. Geometry is now the
     PRIMARY signal (name is a tiebreak), there is no name prefilter, and each
     agency feature yields at most one match. Strong-geometry + weak-name routes to
     REVIEW, never auto-accept.

Thresholds are Wave-2 PLACEHOLDERS — calibration against real corpus data is the
spike's job; the algorithm is unit-tested here on synthetic + real name pairs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry
from thefuzz import fuzz

_LAT_DEG_TO_M = 111_000.0  # metres per degree of latitude (constant)
_LON_DEG_TO_M = 85_000.0  # metres per degree of longitude at ~38°N (111_000 * cos(38°))
# Isotropic deg→m scale (lon degrees are ~30% shorter than lat at 38°N; average the two).
_DEG_TO_M = (_LAT_DEG_TO_M + _LON_DEG_TO_M) / 2  # ~98 000 m/deg
_SUFFIXES = re.compile(r"\b(trail|tr|trl|path|road|rd|fr|fs|loop|spur|route)\b")
_NONWORD = re.compile(r"[^a-z0-9]+")

# ── Matcher-local name canonicalisation (see module note #1) ───────────────────
#
# DO NOT fold this into the pipeline's `normalize_name`: that function is the
# OSM-consolidation GROUPING key and deliberately strips spur/loop so segments of
# one trail group together. For agency↔OSM *matching* we need the opposite emphasis.

# Generic qualifiers agencies decorate names with but OSM usually omits. Stripped as
# whole tokens before scoring so "Appalachian National Scenic Trail" == OSM
# "Appalachian Trail". "trail"/"path" are generic here (unlike the DISCRIMINATING
# suffixes below, which we keep). Wave-2-CALIBRATED PLACEHOLDER — extend from real
# mismatches.
_GENERIC_TOKENS = frozenset(
    {"national", "scenic", "recreation", "recreational", "trail", "trails", "path"}
)

# True abbreviations → canonical form. NOT a suffix strip: these rewrite a token's
# spelling so both sides share one form ("Big Cr" == "Big Creek"). Applied per token
# before generic-stripping. Wave-2-CALIBRATED PLACEHOLDER set.
_ABBREV = {
    "mtn": "mountain",
    "mt": "mount",
    "cr": "creek",
    "ck": "creek",
    "fk": "fork",
    "rd": "road",
    "br": "branch",
}

# Route-role suffixes that make a trail a DISTINCT entity — never stripped, and a
# mismatch in this set vetoes auto-accept (see `_discriminating_tokens`). "Mount
# Rogers Trail" and "Mount Rogers Spur Trail" must never merge: stamping the parent's
# authoritative name onto a spur/tie is a Rule #1 (source-or-silence) violation.
_DISCRIMINATING = frozenset({"spur", "loop", "tie", "connector", "cutoff"})


@dataclass(frozen=True)
class Feature:
    name: str
    geom: BaseGeometry
    source: str = ""
    ref: str | None = None
    # The OSM `highway` value (path|footway|track|bridleway|steps|…) for a spine
    # feature, carried through conflation so it can be persisted on the node and used
    # by the Curator to de-rank roadlike/access ways (feed-quality follow-up). None for
    # non-OSM sources or when the tag was absent.
    way_type: str | None = None
    # TODO(wave-2): capture the OSM `ref=` TAG (e.g. "AT", the human route code) into a
    # NEW field distinct from `ref`. `ref` here is the element id ("way/123", osm.py) —
    # `_build_canonical_id` depends on that — while a source like USFS puts its TRAIL_NO
    # ("4551") in `ref`. So an `a.ref == b.ref` ID-key match can NEVER fire across OSM and
    # an agency and is intentionally NOT attempted here. A real cross-source id join needs
    # the OSM route code in its own field first. OUT OF SCOPE for this redesign.


@dataclass(frozen=True)
class Thresholds:
    # All Wave-2-CALIBRATED PLACEHOLDERS — tune against real conflation data.
    # floor to be a candidate at all (below this: no-match even on strong geometry)
    name_min: int = 60
    # LOWERED from 85: geometry-primary + the discriminating veto carry precision
    name_auto: int = 80
    buffer_deg: float = 0.0003  # ~30 m
    overlap_auto: float = 0.5
    containment_auto: float = 0.9  # one line lies (near-)fully within the other's buffer
    hausdorff_auto_m: float = 80.0
    hausdorff_review_m: float = 250.0


@dataclass(frozen=True)
class Agreement:
    overlap: float  # buffered-intersection / smaller buffered area
    hausdorff_m: float
    # Max fraction of either line lying within the other's buffer. A short agency
    # segment ON a long OSM trail scores ~1 here even though its share of the long
    # trail is small — the containment signal Rule #5 protects (KEEP, don't reject).
    # Additive/defaulted so positional `Agreement(overlap, hausdorff_m)` still holds.
    containment: float = 0.0


@dataclass(frozen=True)
class Match:
    a: Feature
    b: Feature
    name_score: int
    agreement: Agreement
    verdict: str  # "auto-accept" | "review" | "no-match"


_DEFAULT = Thresholds()


def normalize_name(name: str) -> str:
    """The pipeline's OSM-consolidation GROUPING key. Strips suffixes incl. spur/loop.
    DO NOT change — `ingestion.pipeline.consolidate_osm_segments` groups on it and the
    matcher deliberately does NOT use it (see `normalize_for_match`)."""
    return _NONWORD.sub(" ", _SUFFIXES.sub(" ", name.lower())).strip()


def normalize_for_match(name: str) -> str:
    """Canonicalise a name for agency↔OSM SCORING (module note #1). Distinct from
    `normalize_name`: strips generic qualifiers, expands true abbreviations, and KEEPS
    discriminating suffixes (spur/loop/…) so distinct routes stay distinct."""
    tokens: list[str] = []
    for tok in _NONWORD.sub(" ", name.lower()).split():
        tok = _ABBREV.get(tok, tok)
        if tok in _GENERIC_TOKENS:
            continue
        tokens.append(tok)
    result = " ".join(tokens)
    # Never normalise a name entirely away: a name that was ALL generic tokens
    # (e.g. "Trail", "National Scenic Trail") falls back to its token-preserved form so
    # two such names don't both become "" and score a false 100 against each other.
    return result or _NONWORD.sub(" ", name.lower()).strip()


def _discriminating_tokens(normalized: str) -> frozenset[str]:
    return frozenset(normalized.split()) & _DISCRIMINATING


def name_similarity(a: str, b: str) -> int:
    """Order-insensitive fuzzy score on the match-normalised names. token_sort_ratio
    (not token_set_ratio) so an EXTRA discriminating token still lowers the score —
    a set-ratio would treat 'X' ⊂ 'X Spur' as a perfect 100 and collapse the spur."""
    return int(fuzz.token_sort_ratio(normalize_for_match(a), normalize_for_match(b)))


def _name_match(a: str, b: str) -> tuple[int, bool]:
    """(score, discriminating_conflict) for a name pair. `conflict` is True when the two
    names carry different route-role suffixes (one is a spur/loop/tie/… the other isn't)
    — such a pair may be flagged for review but MUST NOT auto-accept."""
    na, nb = normalize_for_match(a), normalize_for_match(b)
    score = int(fuzz.token_sort_ratio(na, nb))
    conflict = _discriminating_tokens(na) != _discriminating_tokens(nb)
    return score, conflict


def geometry_agreement(
    a: BaseGeometry, b: BaseGeometry, *, buffer_deg: float = _DEFAULT.buffer_deg
) -> Agreement:
    ba, bb = a.buffer(buffer_deg), b.buffer(buffer_deg)
    denom = min(ba.area, bb.area)
    overlap = (ba.intersection(bb).area / denom) if denom else 0.0
    # Containment reuses the two buffers (no extra buffering): fraction of each LINE that
    # lies within the OTHER's buffer; take the max. length==0 (point geometry) → 0.0.
    la, lb = a.length, b.length
    c_ab = (a.intersection(bb).length / la) if la else 0.0
    c_ba = (b.intersection(ba).length / lb) if lb else 0.0
    containment = max(c_ab, c_ba)
    return Agreement(
        overlap=overlap,
        hausdorff_m=a.hausdorff_distance(b) * _DEG_TO_M,
        containment=containment,
    )


def classify(
    name_score: int,
    agreement: Agreement,
    thresholds: Thresholds = _DEFAULT,
    *,
    discriminating_conflict: bool = False,
) -> str:
    """Bucket a scored pair. Geometry-primary: no spatial agreement is decisive
    (no-match) regardless of name. A strong-geometry + [name_min, name_auto) name
    routes to REVIEW, never auto-accept. `discriminating_conflict` (a spur/loop/tie
    mismatch) vetoes auto-accept — this is how Rule #5's KEEP-the-sub-segment stays
    safe: containment can make geometry strong, but a differing route-role name is
    still only ever a review, never an authoritative stamp."""
    t = thresholds
    geom_strong = (
        agreement.overlap >= t.overlap_auto
        or agreement.hausdorff_m <= t.hausdorff_auto_m
        or agreement.containment >= t.containment_auto
    )
    geom_near = (
        agreement.overlap > 0
        or agreement.hausdorff_m <= t.hausdorff_review_m
        or agreement.containment > 0
    )
    if not geom_near:
        return "no-match"  # geometry-primary: same name, different place → not a match
    if name_score >= t.name_auto and geom_strong and not discriminating_conflict:
        return "auto-accept"
    # A plausible name + near geometry, or strong geometry + a weak/conflicting name.
    if name_score >= t.name_min:
        return "review"
    return "no-match"


def match(
    a_features: list[Feature], b_features: list[Feature], *, thresholds: Thresholds = _DEFAULT
) -> list[Match]:
    """Return the single best `a` (OSM/spine) candidate per `b` (agency) feature.

    Geometry-primary argmax: for each agency feature we score EVERY spine candidate
    (a cheap distance gate skips the geometrically-impossible ones — this is a
    geometry prefilter, not the old name<60 prefilter that hid correct candidates),
    rank the survivors by geometry (name as the final tiebreak), take the argmax, and
    emit it iff it isn't a no-match. At most one match per agency feature: the old
    'emit every passing pair' could stamp several OSM ways onto one agency record.
    """
    t = thresholds
    # A pair with min-distance beyond the review reach can't be near (Hausdorff ≥ that
    # distance, buffers can't touch) — skip before the expensive buffer/Hausdorff work.
    max_review_dist_deg = t.hausdorff_review_m / _DEG_TO_M
    out: list[Match] = []
    for b in b_features:
        best: tuple[tuple[float, float, float, int], Match] | None = None
        for a in a_features:
            if a.geom.distance(b.geom) > max_review_dist_deg:
                continue
            score, conflict = _name_match(a.name, b.name)
            agreement = geometry_agreement(a.geom, b.geom, buffer_deg=t.buffer_deg)
            verdict = classify(score, agreement, t, discriminating_conflict=conflict)
            if verdict == "no-match":
                continue
            # Geometry-primary ranking; name is only the final tiebreak.
            rank = (agreement.overlap, agreement.containment, -agreement.hausdorff_m, score)
            if best is None or rank > best[0]:
                best = (rank, Match(a, b, score, agreement, verdict))
        if best is not None:
            out.append(best[1])
    return out
