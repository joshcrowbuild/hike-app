"""Garmin adapter — community SSO lib (garth / python-garminconnect).

Unofficial and fragile (Stage 6 §1.1, S6-2): kept behind the DeviceAdapter contract
so a future official Garmin Health API can substitute without touching anything
downstream. Secrets come only from the environment (rule #10). Construction is lazy:
no login happens until the first call (AC-1.5).

The injected `client` must expose:
  - `connectapi(path, params=None) -> dict | list`   (authenticated JSON GET)
  - `download(path) -> bytes`                         (authenticated binary GET, a ZIP)
Tests inject a fake client; production lazily builds a `garth`-backed wrapper.

Endpoint shapes are documented best-effort (Stage 6 §1.1) and validated live in a
terminal session, mirroring how the live conditions adapters were built.
"""

from __future__ import annotations

import io
import logging
import zipfile
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

_ACTIVITIES_PATH = "/activitylist-service/activities/search/activities"
_DOWNLOAD_PATH = "/download-service/files/activity/{activity_id}"
_BODY_BATTERY_PATH = "/wellness-service/wellness/bodyBattery/reports/daily"


def _is_auth_error(exc: Exception) -> bool:
    """True if an exception looks like a 401 / expired session (decoupled from garth
    internals so tests can raise a plain exception with a status_code attribute)."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 401:
        return True
    text = str(exc).lower()
    return "401" in text or "unauthorized" in text


class GarminAdapter(DeviceAdapter):
    name = "garmin"

    def __init__(self, email: str | None, password: str | None, *, client: Any = None) -> None:
        self._email = email
        self._password = password
        self._client = client  # injected fake in tests; lazily built garth in prod

    def _ensure_client(self) -> Any:
        if self._client is None:
            # Check secrets BEFORE importing the heavy lib so a missing-credential
            # config fails loudly and identically whether or not garth is installed.
            if not self._email or not self._password:
                raise ValueError("GARMIN_EMAIL / GARMIN_PASSWORD not set (rule #10)")
            import garth  # lazy: only when a real call is made

            garth.login(self._email, self._password)
            self._client = garth
        return self._client

    def capabilities(self) -> Capabilities:
        return Capabilities(has_fit=True, has_readiness=True, has_activity_title=True)

    def list_activities(
        self,
        since: datetime | None,
        *,
        sport: str = "hiking",
        limit: int = 20,
    ) -> list[ActivityRef]:
        client = self._ensure_client()
        data = client.connectapi(
            _ACTIVITIES_PATH,
            params={"activityType": sport, "start": 0, "limit": limit},
        )
        rows = data if isinstance(data, list) else []
        refs: list[ActivityRef] = []
        for a in rows:
            if not isinstance(a, dict) or a.get("activityId") is None:
                continue
            refs.append(
                ActivityRef(
                    id=f"garmin:{a['activityId']}",
                    source="garmin",
                    title=a.get("activityName"),
                    start_time=_parse_garmin_time(a.get("startTimeGMT")),
                    sport=(a.get("activityType") or {}).get("typeKey")
                    if isinstance(a.get("activityType"), dict)
                    else None,
                )
            )
        # The Garmin activitylist endpoint has no clean server-side "since" param,
        # so bound the window client-side (AC-4.2). MERGE idempotency is the backstop
        # for boundary slop. Activities with an unknown start_time are kept (the MERGE
        # de-dupes them) rather than risk dropping a genuinely-new one.
        if since is not None:
            refs = [r for r in refs if r.start_time is None or r.start_time >= since]
        return refs

    def download_fit(self, ref: ActivityRef) -> bytes:
        client = self._ensure_client()
        activity_id = ref.id.split(":", 1)[1]
        zip_bytes = client.download(_DOWNLOAD_PATH.format(activity_id=activity_id))
        return _extract_fit_from_zip(zip_bytes)

    def fetch_readiness(self, *, at: datetime | None = None) -> ReadinessSignal | None:
        client = self._ensure_client()
        try:
            data = client.connectapi(_BODY_BATTERY_PATH)
        except Exception as exc:
            log.warning("garmin: body battery fetch failed: %s", exc)
            return None
        value = _latest_body_battery(data)
        if value is None:
            return None
        return ReadinessSignal(
            value=float(value),
            kind="body_battery",
            source="garmin",
            fetched_at=at or datetime.now(timezone.utc),
        )

    def health(self) -> AdapterHealth:
        # Probe with a cheap call so an EXPIRED session (401 mid-life), not just a
        # bad initial login, is detected and reported as needs_reauth (Stage 6 §1.1).
        try:
            client = self._ensure_client()
            client.connectapi(_ACTIVITIES_PATH, params={"start": 0, "limit": 1})
            return AdapterHealth.OK
        except Exception as exc:
            if _is_auth_error(exc):
                return AdapterHealth.NEEDS_REAUTH
            log.warning("garmin: health check failed: %s", exc)
            return AdapterHealth.DOWN


# ── helpers ──────────────────────────────────────────────────────────────────


def _parse_garmin_time(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_fit_from_zip(zip_bytes: bytes) -> bytes:
    """Garmin's download-service returns a ZIP; pull the first .fit member."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        fit_names = [n for n in zf.namelist() if n.lower().endswith(".fit")]
        if not fit_names:
            raise ValueError("no .fit file in Garmin activity download")
        return zf.read(fit_names[0])


def _latest_body_battery(data: Any) -> float | None:
    """Best-effort extraction of the latest Body Battery value from the daily report."""
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        for key in ("charged", "bodyBatteryValue", "value", "level"):
            v = data.get(key)
            if isinstance(v, (int, float)):
                return float(v)
    return None
