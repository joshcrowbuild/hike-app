"""Corpus-source seam — N source adapters behind one `CorpusSource` contract.

Sibling-in-spirit to `orchestration/providers/` and `ingestion/watch/`: a real
contract (`base.py`), a config-driven registry (`registry.py`), and one adapter
per source. Every adapter normalizes to the existing `Feature`
(`ingestion.conflate.match`) — the seam wraps proven output, never reshapes it.

Adding a corpus source is a closed checklist (source-seams-corpus-and-live.md §6):
  1. Implement `CorpusSource` (`fetch` or `enrich`) in `ingestion/sources/<name>.py`.
  2. Declare `kind` / `role` / `authority_tier` (spine selection + best-view fall out).
  3. Register it in `registry.py`; add `<name>` to ADVENTURE_CORPUS_SOURCES.
  4. Put any path/key in the secrets store, read via `from_config` (rule #10).
  5. Run it through the shared source-conformance suite.
→ Zero edits to conflation scoring, the load loop, enrichment, or `run_pipeline`.
"""
