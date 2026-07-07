"""API request/response schemas (Pydantic models)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Shape of a viewer identity (AH4): the anonymous default, or an alphanumeric/underscore/
# hyphen/colon token (":" separates the household-member prefix, e.g. "mem:josh"),
# length-bounded so a malformed value 422s before it ever reaches Cypher (access control
# at the query/data layer, rule #4) or a log line (rule #5).
VIEWER_ID_PATTERN = r"^[A-Za-z0-9_:-]{1,64}$"

# Shape of a canonical_id path param (AL2): the query is already parameterized (no
# injection risk), so this is length/hygiene only — reject control characters and cap
# length well above any real id (e.g. "ct:osm:old-rag-loop").
CANONICAL_ID_PATTERN = r"^[^\x00-\x1F\x7F]{1,200}$"


class PlanRequest(BaseModel):
    query: str = Field(
        ..., description="Free-text request, e.g. 'something mellow with good views'"
    )
    lat: float = Field(..., ge=-90, le=90, description="Origin latitude (WGS84)")
    lon: float = Field(..., ge=-180, le=180, description="Origin longitude (WGS84)")
    # 10 is the product norm; 20 is ample headroom. Each candidate fans out to several
    # live probes (AH3), so the public max is capped well below the old le=50.
    k: int = Field(default=10, ge=1, le=20, description="Max results")
    viewer_id: str = Field(
        default="anonymous",
        pattern=VIEWER_ID_PATTERN,
        description="Viewer identity for graph scoping",
    )


class FeedLineResponse(BaseModel):
    text: str
    source: str
    confidence_level: str  # "stated" | "hedged" | "flagged"  (presentation vocabulary)
    # Distinct live-source names backing this fact (Epic 026a). Populated only for a
    # line built from a live probe (every line the engine emits qualifies — the feed
    # carries no non-live lines); never backfilled from a card-level enrichment/mock
    # source list, which would fabricate per-fact provenance (Rule #2/#11). Always a
    # single-entry list today (CDP-01: live facts are single-source by construction),
    # carried honestly rather than padded — the corpus-level count lives elsewhere.
    sources: list[str] = []


class CardWarningResponse(BaseModel):
    """One prominent, source-stamped hazard warning a card wears (decision of
    2026-07-01): a VERIFIED hazard shows on the trail's card, never hides it.
    Mirrors `FeedLineResponse`'s source-carrying shape; `observed_at` is the ISO-8601
    timestamp the hazard fact was fetched. Mirrors `frontend/src/data/api.ts`."""

    text: str
    source: str
    observed_at: str  # ISO-8601 fetch timestamp of the hazard fact
    kind: str  # the condition kind, e.g. "weather" | "air" | "fire"


class ConditionUnavailableResponse(BaseModel):
    """One condition that couldn't be verified — the trail stays a normal card
    carrying this disclosure rather than being set aside (decision of 2026-07-02;
    rule #6: live conditions are enrichment, never a dependency — an outage must
    never blank the feed). Mirrors `frontend/src/data/api.ts`."""

    text: str
    source: str
    kind: str  # the condition kind, e.g. "weather"


# ── Maps & terrain wire DTOs — the Lane A↔B contract ──────────────────────────
#
# These are a literal mirror of `frontend/src/data/api.ts` (the published source of
# truth): `WireGeometry` / `WirePoint` / `WireElevationSample` / `WireElevationProfile`,
# plus the maps fields on `FeedCardResponse`. Field names ARE the wire contract — keep
# them snake_case and verbatim. `null`/absent everywhere means *not available*, never a
# fabricated value (Rule #1). `tests/test_maps_contract.py` asserts this match.

ConfidenceLevel = Literal["stated", "hedged", "flagged"]


class GeoJsonGeometry(BaseModel):
    """`WireGeometry`: the assembled route as a GeoJSON geometry (WGS84), coordinate
    order `(lon, lat)` per the spec. `LineString` when the trail's segments join into
    one continuous line; `MultiLineString` when they don't join cleanly (Epic 016
    AC-1.1)."""

    type: Literal["LineString", "MultiLineString"]
    # LineString -> [[lon, lat], ...]; MultiLineString -> [[[lon, lat], ...], ...].
    coordinates: list[Any]


class GeoPoint(BaseModel):
    """`WirePoint`: a WGS84 point `{lat, lon}` — used for the trailhead start marker
    and the summit/high-point.

    `derived` is the source-or-silence disclosure for the start marker (Rule #1): when
    a trail has no surveyed `:Trailhead`, the start falls back to a point synthesised
    from the trail's own geometry, and `derived=True` says so — an approximate access
    point, never presented as a surveyed trailhead (D7). `False` for a real trailhead
    and for the summit (a summit is never a fallback). Presentation-only; it never
    enters ranking (Rule #2)."""

    lat: float
    lon: float
    derived: bool = False


class ElevationSample(BaseModel):
    """`WireElevationSample`: one ordered point on the climb profile. `distance_m` is
    the cumulative along-route distance from the start; samples run start → end."""

    distance_m: float
    elevation_m: float


class ElevationProfile(BaseModel):
    """`WireElevationProfile`: the precomputed climb profile sampled along the route
    from USGS 3DEP (Epic 017). The whole field is `null` when a trail has no DEM
    coverage or no geometry — never an interpolated or faked curve (Rule #1 / D3).
    `total_gain_m`/`total_loss_m`/`max_grade_pct` are derived fresh from `samples` at
    read time (`api.app._elevation_profile`), not trusted from a second stored
    scalar. `estimated_duration_min` is a computed grade-aware ESTIMATE, not a
    stated fact (Rule #1/#7) — name says so; the client must disclose it as such."""

    samples: list[ElevationSample]  # ordered start → end
    total_gain_m: float
    total_loss_m: float
    max_grade_pct: float
    source: str  # provenance, e.g. "usgs-3dep"
    resolution_m: float  # sampling spacing along the route
    estimated_duration_min: float  # grade-aware ESTIMATE — never a stated fact


class FeedCardResponse(BaseModel):
    canonical_id: str
    name: str
    distance_mi: float | None
    lines: list[FeedLineResponse]
    warnings: list[CardWarningResponse]
    # Conditions that couldn't be verified, disclosed here rather than causing the
    # trail to be set aside (decision of 2026-07-02; rule #6).
    unavailable: list[ConditionUnavailableResponse] = []
    # Maps & terrain (Epic 016 S1 / Epic 017 S4). All optional/nullable: a card with no
    # mapped route omits/nulls them and the client degrades honestly (Rule #1).
    geometry: GeoJsonGeometry | None = None
    trailhead: GeoPoint | None = None
    # Geometry's confidence tier (Rule #2); non-`stated` draws the dashed "approximate"
    # route (D5). Derived from assembly quality, never hardcoded.
    geometry_confidence: ConfidenceLevel | None = None
    summit: GeoPoint | None = None  # high point if known, else null (source-or-silence)
    elevation_profile: ElevationProfile | None = None


class SetAsideReasonResponse(BaseModel):
    """One source-stamped cause a trail was set aside by a hard live guardrail (Epic
    018 S5). `text` is the ready-to-show disclosure ("cause (source)"); `source`/`kind`
    keep the pieces structured. Mirrors `frontend/src/data/api.ts`."""

    text: str
    source: str
    kind: str  # the condition kind, e.g. "weather" | "air"


class SetAsideResponse(BaseModel):
    """A trail a hard live guardrail ruled out — an unverifiable required condition or
    a hard threshold — disclosed with its cause + source (Epic 018 S5 AC-5.2), never
    dropped without a trace. A verified hazard is NOT set aside; it stays a card with a
    `warnings` entry (decision of 2026-07-01). A safety gate, not a ranking signal
    (Rule #2). Mirrors `frontend/src/data/api.ts`."""

    canonical_id: str
    name: str
    reasons: list[SetAsideReasonResponse]


class FeedResponse(BaseModel):
    query: str
    cards: list[FeedCardResponse]
    card_count: int
    notices: list[str] = []  # feed-level disclosures (e.g. drive times unavailable)
    # Trails a hard live guardrail set aside, disclosed with cause + source (Epic 018 S5).
    set_aside: list[SetAsideResponse] = []


class GraphStats(BaseModel):
    canonical_trails: int
    # Elevation-presence gauge (Epic 017 durability): how many CanonicalTrails carry a
    # 3DEP-derived profile, and that as a % of all trails (null when there are no
    # trails). Makes a corpus-wide elevation lag/wipe visible instead of silent.
    trails_with_elevation: int = 0
    elevation_coverage_pct: float | None = None
    # Corroboration gauge (CDP-01 / Epic 026a): how many CanonicalTrails are joined by
    # SAME_AS to ≥2 distinct upstream SourceRecord.source values, and that as a % of all
    # trails (null when there are no trails). Makes the trust gradient visible on the
    # dashboard the same way elevation coverage is.
    trails_multi_source: int = 0
    corroboration_pct: float | None = None
    source_records: int
    trailheads: int
    same_as_edges: int
    schema_version: str | None
    # Integer data-shape stamp (Epic 024 / CoMaps A4-lite), distinct from the semver
    # schema_version string above. None on a legacy graph applied before this epic.
    schema_format: int | None = None


class OutcomeBody(BaseModel):
    overall: int | None = Field(
        default=None,
        description="1 (😞) | 2 (😐) | 3 (🙂); null when skipped",
    )
    delta_question: str | None = None
    # AL3: this free-text answer is stored verbatim as a `stated` Belief (never decays,
    # confidence 1.0 — orchestration/outcome.py), so an unbounded body is unbounded
    # substrate. 2000 chars is ample for a reflect-back answer.
    delta_answer: str | None = Field(
        default=None, max_length=2000, description="User's free-text reflect-back"
    )
    skipped: bool = False


class OutcomeResponse(BaseModel):
    outcome_id: str
    episode_id: str
    skipped: bool
    overall: int | None


class OriginResponse(BaseModel):
    """One named search origin the frontend picker can offer (Phase 2: config-driven
    origins — sourced from `regions/*.geojson` `properties.origins`, never hardcoded
    in frontend code)."""

    key: str
    label: str
    lat: float
    lon: float


class RegionResponse(BaseModel):
    """One ingest region's picker-facing config: its display label and named origins."""

    region_id: str
    label: str
    origins: list[OriginResponse]


class RegionsResponse(BaseModel):
    """`GET /regions`: every region's origin config, independent of which region this
    process last ingested (`ADVENTURE_REGION`) — the graph holds every ingested
    region's trails at once, so the picker must offer all of them."""

    regions: list[RegionResponse]


class IngestDiffBucket(BaseModel):
    """One per-facet bucket delta (Epic 027) — a single `"{dimension}={value}"` row
    from the within-run pre-load-vs-this-run `stats.json`."""

    dimension: str
    value: str
    pre: int
    post: int
    delta: int
    rel_pct: float
    breached_level: str | None = None


class IngestDiffResponse(BaseModel):
    """Compact per-facet ingest-diff summary (Epic 027) surfaced on `/health`: the
    top ≤5 buckets by `|delta|`, whether the hard-breach gate blocked this run's
    prune, and the coarsest (most severe) level any bucket breached. `None` on
    `/health` when no `stats.json` is present for this host's region (Rule #1)."""

    region: str
    generated_at: str
    prune_blocked: bool
    worst_breached_level: str | None = None
    top_deltas: list[IngestDiffBucket] = []


class HealthResponse(BaseModel):
    status: str
    version: str
    region: str
    probes_available: list[str]
    graph: GraphStats | None = None  # None if Neo4j unreachable
    ingest_diff: IngestDiffResponse | None = None  # None if no stats.json for this region


class StatusResponse(BaseModel):
    """`GET /status`: current deployed state for cross-surface grounding (the
    agent-operating-model real-time source). Anything unknowable from this host is
    honestly `null` — never guessed (Rule #1): deploy fields are `null` off Render,
    graph-derived fields are `null` when the graph is unreachable."""

    deploy_sha: str | None  # RENDER_GIT_COMMIT; null off Render
    deploy_branch: str | None  # RENDER_GIT_BRANCH; null off Render
    region: str  # corpus region (e.g. "shenandoah-gwj")
    live_region: str  # live-probe registry region (e.g. "US")
    schema_version: str | None  # (:Meta {id:'schema'}).schema_version
    meta_updated_at: str | None  # Meta.updated_at (last schema apply), ISO-8601
    # Most recent SourceRecord.fetched_at (ISO-8601), falling back to the coarse
    # ingest_version ("YYYY-MM") when no fetched_at is stored.
    last_ingest: str | None
    corpus: GraphStats | None  # same shape as /health's graph; None if unreachable


class TripDetailResponse(BaseModel):
    """The trip/detail response (`GET /trail/{canonical_id}`). The same maps fields the
    feed card carries, served per-trail — every geometry/elevation field honestly
    `null` when absent (Rule #1). Snake_case to match `frontend/src/data/api.ts`."""

    canonical_id: str
    name: str
    geometry: GeoJsonGeometry | None = None  # null = route not mapped (trailhead only)
    trailhead: GeoPoint | None = None
    geometry_confidence: ConfidenceLevel | None = None
    summit: GeoPoint | None = None
    elevation_profile: ElevationProfile | None = None  # null = no coverage
