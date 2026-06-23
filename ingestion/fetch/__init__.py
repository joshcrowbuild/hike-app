"""Stage-3 fetch layer — pull raw trail features from open-data sources.

Each sub-module exposes `fetch(bbox, *, client) -> list[Feature]` using the
same `Feature` type from `ingestion.conflate.match`. All I/O is injectable
(httpx.Client param) so tests don't need network. On any error, return [] —
fetch-layer failures are reported by the pipeline, not raised here.
"""
