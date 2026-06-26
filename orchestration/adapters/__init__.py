"""Live-data adapters (Stage 4 Verifier tools).

One module per Stage-1 source, added in Stage 4:
  nws · usgs_water (OGC API) · firms · airnow · ridb · valhalla (drive time).
Each: `(lat, lon | site_id) -> VerifiedFact | None`, with mocked-response
integration tests and degrade-and-disclose on outage / rate-limit.
"""
