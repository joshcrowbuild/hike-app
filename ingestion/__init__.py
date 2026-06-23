"""Corpus ingestion — the Stage-3 pipeline (idempotent, versioned DAG).

    acquire -> extract -> transform -> hygiene -> conflate -> dedup -> load -> index

Polygon-scoped per region; monthly idempotent refresh keyed on (source,
source_pk) with tombstoned deletes; human-in-the-loop conflation (OSM spine +
OSM Merge). Submodules (pipeline/, sources/, conflate/) are created in Stage 3.

See docs/research/stage-3-corpus-pipeline.md.
"""
