"""OpenTopoDataSampler — a network `ElevationSampler` transport (Epic 033).

Ports the request/response contract of OpenTopoData (`ajnisbet/opentopodata`,
https://github.com/ajnisbet/opentopodata, MIT License) — a self-hostable,
Google-Elevation-API-compatible service. This module is a thin REST *client*
against that contract; no OpenTopoData source is vendored.

Sits alongside `RasterioDEMSampler` (`ingestion/sources/usgs_3dep.py`) as a
degrade-and-disclose fallback (rule #6) for hosts with no local DEM raster and
no `rasterio` (the recurring Render elevation-durability pain). Local-first
raster stays primary — see `UsgsThreeDEPSource.from_config`'s selection order.

Source-or-silence (Rule #1 / D3): any miss — out-of-coverage `null`, empty
`results`, a non-OK status, a non-200 response, a malformed body, or a raised
exception — returns `None`, never a guessed elevation.
"""

from __future__ import annotations

import httpx

_DEFAULT_DATASET = "ned10m"


class OpenTopoDataSampler:
    """Reads ground elevation from a hosted OpenTopoData endpoint. Lazy: builds
    its own `httpx.Client` on first use unless one is injected. Returns `None`
    on any miss — the source-or-silence signal the profile builder honors."""

    def __init__(
        self,
        *,
        base_url: str,
        dataset: str = _DEFAULT_DATASET,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client
        self._url = f"{base_url.rstrip('/')}/v1/{dataset}"
        self.source = f"opentopodata:{dataset}"

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def sample(self, lon: float, lat: float) -> float | None:
        client = self._ensure_client()
        try:
            response = client.get(self._url, params={"locations": f"{lat},{lon}"})
            if response.status_code != 200:
                return None
            body = response.json()
            if body.get("status") != "OK":
                return None
            results = body.get("results")
            if not results:
                return None
            elevation = results[0].get("elevation")
            return None if elevation is None else float(elevation)
        except Exception:
            # Any miss — malformed body, unexpected JSON shape, non-numeric
            # elevation, connect/timeout — is source-or-silence (rule #1),
            # never a guessed value.
            return None

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None
