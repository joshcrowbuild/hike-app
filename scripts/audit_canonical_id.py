"""Re-runnable, read-only audit for same-source canonical_id collisions (Epic 030).

Proves zero silent *distinct-name* same-source merges in the loaded corpus by
recomputing `_build_canonical_id` (the single source of truth, imported from
`ingestion.pipeline`) over every `SourceRecord` and flagging any canonical_id
fed by >=2 SourceRecords of the SAME source with distinct (source_id, raw_name)
identity. Cross-source sharing is legitimate conflation and is never flagged.

Scope limit: this audit can only catch *distinct-name* collisions. Two
ref-less same-source features that share one byte-identical name collapse to
a single SourceRecord (via `ingestion.pipeline._sr_uid`) before they ever
reach this script, so that case is invisible here — it is caught instead at
load time by the S5 `log.warning` in `ingestion.pipeline._load_matches`. A
report of "0 collisions" from this script means zero *distinct-name*
same-source fusions, NOT zero same-source fusions overall.

Back-fill is out of scope: already-loaded nodes keep their old canonical_id
until the next re-ingest (see docs/epics/epic-030-slug-collision.md).
"""

from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict

from graph.client import GraphClient
from ingestion.pipeline import _build_canonical_id
from orchestration.config import Settings


def _prefix_id_legacy(source: str, source_id: str | None, raw_name: str) -> str:
    """Deliberate re-implementation of the PRE-FIX `_build_canonical_id`, used
    ONLY to report how many collision clusters the fix resolves (AC-4.4). The
    corrected, imported `_build_canonical_id` remains the single source of
    truth for actual collision detection — this is a read-only historical
    comparator, not an identity source."""
    if source_id:
        clean_ref = source_id.replace("/", "_").replace(" ", "-").lower()
        return f"ct:{source.lower()}:{clean_ref}"
    slug = raw_name.lower().replace(" ", "-").replace("/", "-")
    if len(slug) > 40:
        suffix = hashlib.sha1(slug.encode(), usedforsecurity=False).hexdigest()[:6]
        slug = f"{slug[:33]}-{suffix}"
    return f"ct:{source.lower()}:{slug}"


def find_same_source_clusters(
    rows: list[dict[str, str]], id_fn
) -> dict[str, list[tuple[str, str, str]]]:
    """Groups `rows` (each with source/source_id/raw_name) by `id_fn`-recomputed
    canonical_id, then keeps only groups where >=2 records share a `source` but
    have distinct (source_id, raw_name) identity. Returns canonical_id ->
    list of (source, source_id, raw_name) for the colliding records. Pure /
    DB-free so it is unit-testable without a live Neo4j."""
    by_id: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for row in rows:
        source = row["source"]
        source_id = row.get("source_id") or None
        raw_name = row["raw_name"]
        cid = id_fn(source, source_id, raw_name)
        by_id[cid].append((source, source_id or "", raw_name))

    clusters: dict[str, list[tuple[str, str, str]]] = {}
    for cid, records in by_id.items():
        by_source: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for source, source_id, raw_name in records:
            by_source[source].add((source_id, raw_name))
        for source, identities in by_source.items():
            if len(identities) >= 2:
                clusters[cid] = [r for r in records if r[0] == source]
    return clusters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when >=1 same-source collision cluster is found",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    gc = GraphClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    try:
        with gc._ensure_driver().session() as session:
            rows = session.run(
                "MATCH (r:SourceRecord) "
                "RETURN r.source AS source, r.source_id AS source_id, r.raw_name AS raw_name"
            ).data()
    finally:
        gc.close()

    corrected_clusters = find_same_source_clusters(
        rows, lambda source, source_id, raw_name: _build_canonical_id(source, source_id, raw_name)
    )
    legacy_clusters = find_same_source_clusters(rows, _prefix_id_legacy)

    print("=== Same-source canonical_id collision audit (distinct-name only) ===")
    if not corrected_clusters:
        print("0 collisions (corrected _build_canonical_id)")
    for cid, records in corrected_clusters.items():
        source = records[0][0]
        print(f"  canonical_id={cid!r} source={source!r}")
        for _source, source_id, raw_name in records:
            print(f"    - source_id={source_id!r} raw_name={raw_name!r}")

    print(
        f"\nCorrected function: {len(corrected_clusters)} same-source collision cluster(s). "
        f"Pre-fix function: {len(legacy_clusters)} same-source collision cluster(s) "
        f"(over the same loaded SourceRecords)."
    )
    print(
        "Note: already-loaded CanonicalTrail/SourceRecord nodes keep their OLD canonical_id "
        "until the next re-ingest — this audit does not back-fill (out of scope, epic-030)."
    )
    print(
        "Scope limit: this only catches DISTINCT-NAME same-source collisions. Two same-source "
        "ref-less features sharing one byte-identical name collapse to a single SourceRecord "
        "before reaching this audit and are invisible here — they are caught instead by the "
        "S5 load-time log.warning in ingestion.pipeline._load_matches. '0 collisions' above "
        "means 0 distinct-name fusions, NOT 0 same-source fusions overall."
    )

    if args.strict and corrected_clusters:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
