"""Coros adapter — direct open.coros.com HTTP (OAuth2) for BATCH ingestion.

Coros provides an official MCP server, but that is reserved for *interactive*
agent queries (S6-3 / device-integration-seam.md §5). Batch ingestion uses the
direct HTTP API so the poller has no MCP dependency. Secrets (client id/secret)
come only from the environment (rule #10). Construction is lazy (AC-1.5).

The injected `client` is an `httpx.Client` (real or MockTransport-backed). Endpoint
shapes are documented best-effort (Stage 6 §1.2) and validated live in a terminal
session, mirroring the live conditions adapters.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .base import (
    ActivityRef,
    AdapterHealth,
    Capabilities,
    DeviceAdapter,
    ReadinessSignal,
)

log = logging.getLogger(__name__)

_BASE = "https://open.coros.com"
_TOKEN_URL = f"{_BASE}/oauth2/accesstoken"
_ACTIVITIES_URL = f"{_BASE}/v2/coros/activities"
_DOWNLOAD_URL = f"{_BASE}/v2/coros/activity/download"
_READINESS_URL = f"{_BASE}/v2/coros/recovery"


class CorosAdapter(DeviceAdapter):
    name = "coros"

    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        *,
        client: Any = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = client  # injected httpx.Client (real or MockTransport)
        self._token: str | None = None

    def _ensure_http(self) -> Any:
        if self._http is None:
            import httpx  # lazy

            self._http = httpx.Client(timeout=15.0)
        return self._http

    def _access_token(self) -> str:
        if self._token:
            return self._token
        if not self._client_id or not self._client_secret:
            raise ValueError("COROS_CLIENT_ID / COROS_CLIENT_SECRET not set (rule #10)")
        http = self._ensure_http()
        resp = http.post(
            _TOKEN_URL,
            json={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise ValueError("coros: no access_token in token response")
        self._token = token
        return token

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token()}"}

    def capabilities(self) -> Capabilities:
        return Capabilities(has_fit=True, has_readiness=True, has_activity_title=True)

    def list_activities(
        self,
        since: datetime | None,
        *,
        sport: str = "hiking",
        limit: int = 20,
    ) -> list[ActivityRef]:
        http = self._ensure_http()
        params: dict[str, Any] = {"sportType": sport, "size": limit}
        if since is not None:
            params["startTime"] = int(since.timestamp())
        resp = http.get(_ACTIVITIES_URL, params=params, headers=self._auth_headers())
        resp.raise_for_status()
        body = resp.json()
        rows = body.get("data") if isinstance(body, dict) else body
        refs: list[ActivityRef] = []
        for a in rows or []:
            if not isinstance(a, dict) or a.get("labelId") is None:
                continue
            refs.append(
                ActivityRef(
                    id=f"coros:{a['labelId']}",
                    source="coros",
                    title=a.get("name"),
                    start_time=_parse_coros_time(a.get("startTime")),
                    sport=a.get("sportType"),
                )
            )
        return refs

    def download_fit(self, ref: ActivityRef) -> bytes:
        http = self._ensure_http()
        activity_id = ref.id.split(":", 1)[1]
        resp = http.get(
            _DOWNLOAD_URL,
            params={"labelId": activity_id, "fileType": "fit"},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.content

    def fetch_readiness(self, *, at: datetime | None = None) -> ReadinessSignal | None:
        http = self._ensure_http()
        try:
            resp = http.get(_READINESS_URL, headers=self._auth_headers())
            resp.raise_for_status()
        except Exception as exc:
            log.warning("coros: recovery fetch failed: %s", exc)
            return None
        body = resp.json()
        value = body.get("recovery") if isinstance(body, dict) else None
        if not isinstance(value, (int, float)):
            return None
        return ReadinessSignal(
            value=float(value),
            kind="recovery",
            source="coros",
            fetched_at=at or datetime.now(timezone.utc),
        )

    def health(self) -> AdapterHealth:
        try:
            self._access_token()
            return AdapterHealth.OK
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 401:
                return AdapterHealth.NEEDS_REAUTH
            if status == 429:
                return AdapterHealth.RATE_LIMITED
            log.warning("coros: health check failed: %s", exc)
            return AdapterHealth.DOWN


def _parse_coros_time(raw: Any) -> datetime | None:
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (ValueError, OSError):
            return None
    return None
