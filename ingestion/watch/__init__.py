"""Device-integration seam — Epic 004.

A config-driven device-provider seam (sibling of the model-provider seam in
`orchestration/providers/`). Smart-device support (Garmin, Coros, future vendors)
is modular: every adapter normalizes to **FIT bytes**, which the EXISTING
`ingestion/ingest_episode.py` pipeline (parse → Episode → belief queue → commons
fork) consumes identically. The mechanism a vendor uses — community SSO lib vs.
official OAuth vs. MCP — is the adapter's private business.

**Adding a manufacturer is a closed checklist** (device-integration-seam.md §6):
  1. Implement `DeviceAdapter` (5 methods) in `ingestion/watch/<vendor>.py`.
  2. Declare its `Capabilities` (degrade-and-disclose falls out automatically).
  3. Register it in `registry.ADAPTER_REGISTRY`; add `<vendor>` to ADVENTURE_WATCH_ADAPTERS.
  4. Put its secrets in the secrets manager (rule #10).
  5. Run it through the shared conformance suite (tests/test_watch_conformance.py).
  → Zero edits to FIT parsing, Episode, belief, commons, or the poller.

Design: docs/research/device-integration-seam.md
"""
