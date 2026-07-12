"""Log-safe identifiers + the process logging config (Phase B log hygiene).

Rule #5: the private overlay — including who a log line is *about* — is substrate,
never telemetry. Every identifier that names a member (viewer_id, owner_id, and
episode_id, whose ``ep:{owner_id}:{activity}`` shape embeds the owner) must pass
through a scrubber before reaching a log call. This module is the one home for
those scrubbers, placed below both ``api/`` and ``ingestion/`` so every layer can
import it without a layering inversion (``api.observability`` re-exports
``scrub_viewer`` for its existing call sites).

``setup_logging()`` is the coherent process-wide config: before it existed the API
process had no logging config at all, so INFO-level lines (the /plan cost metrics,
warm-up completion) never reached Render's log stream — only WARNING+ made it out
via Python's last-resort handler.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re

logger = logging.getLogger(__name__)

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_VALID_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}

# Known secret-bearing URL shapes in live-probe requests (2026-07-12 review). httpx
# logs every request line at INFO with the FULL url, and two adapters carry their key
# in it: FIRMS embeds FIRMS_MAP_KEY as a path segment
# (/api/area/csv/{key}/{dataset}/...), AirNow passes API_KEY as a query param. Pattern
# based on purpose: the filter must not need the live key values to do its job, and
# it keeps masking if a key is rotated mid-process.
_SECRET_URL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # FIRMS map key: the path segment right after /api/area/csv/. "***" is the repo's
    # existing mask convention (orchestration/adapters/_http.py), which also makes
    # re-masking an already-masked line a no-op.
    (
        re.compile(r"(firms\.modaps\.eosdis\.nasa\.gov/api/area/csv/)[^/\s\"]+"),
        r"\1***",
    ),
    # AirNow (and any other) API_KEY-style query param, case-insensitive.
    (re.compile(r"(?i)\b(api_key=)[^&\s\"']+"), r"\1***"),
)


class SecretUrlRedactionFilter(logging.Filter):
    """Masks known key-in-URL patterns before a record reaches any handler.

    Attached to the ``httpx``/``httpcore`` loggers by ``setup_logging`` — a logging-
    layer fix, chosen over demoting httpx to WARNING so the request lines stay useful
    in production logs (which requests ran, status, latency) with only the credential
    material masked. The record's message is resolved eagerly (``getMessage``) then
    rewritten, because the secret arrives via ``args``, not the format string."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for pattern, replacement in _SECRET_URL_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def scrub_viewer(viewer_id: str) -> str:
    """A short, stable, non-reversible tag for a viewer (Rule #5). ``anonymous`` stays
    legible as ``anon``; any real identity becomes an 8-hex digest, enough to correlate
    a session's calls in the logs without carrying the identity itself.

    A bare SHA-256 of a low-entropy identifier (e.g. an email) is *confirmable* — anyone
    who guesses the value can verify it by re-hashing. Mixing in a deployment-private
    salt (``ADVENTURE_LOG_HASH_SALT``) defeats that while keeping the tag stable within
    a deploy. The salt is optional: absent it, the digest is still non-reversible and
    adequate for log correlation."""
    if viewer_id == "anonymous":
        return "anon"
    salt = os.environ.get("ADVENTURE_LOG_HASH_SALT", "")
    return "vh:" + hashlib.sha256((salt + viewer_id).encode("utf-8")).hexdigest()[:8]


def scrub_episode(episode_id: str) -> str:
    """The episode analogue of ``scrub_viewer``: episode ids are built as
    ``ep:{owner_id}:{watch_activity_id}`` (ingestion/ingest_episode.py), so a raw
    episode id in a log line IS the owner id in the clear. The whole id is digested —
    not just the owner segment — because the activity id is itself linkable device
    data. Same salt, same stability contract."""
    salt = os.environ.get("ADVENTURE_LOG_HASH_SALT", "")
    return "eh:" + hashlib.sha256((salt + episode_id).encode("utf-8")).hexdigest()[:8]


def setup_logging(level: str | None = None) -> None:
    """Process-wide logging config for the API (called from the app lifespan).

    Level comes from the argument, else ``ADVENTURE_LOG_LEVEL``, else INFO; an
    unrecognized value degrades to INFO with a warning rather than refusing to boot
    (the surface degrades gracefully; the misconfiguration is disclosed). Idempotent:
    ``basicConfig`` is a no-op when the root logger already has handlers (e.g. an
    ingestion CLI's import-time config, or a re-run lifespan), so repeated calls
    never stack duplicate handlers — only the level is (re)applied."""
    resolved = (level or os.environ.get("ADVENTURE_LOG_LEVEL") or "INFO").upper()
    if resolved not in _VALID_LEVELS:
        logger.warning("unknown ADVENTURE_LOG_LEVEL %r; using INFO", resolved)
        resolved = "INFO"
    logging.basicConfig(level=resolved, format=_LOG_FORMAT)
    logging.getLogger().setLevel(resolved)
    # httpx logs each request line at INFO with the full URL — for FIRMS/AirNow that
    # URL carries the API key (2026-07-12 review). Mask at the emitting logger so no
    # handler ever sees the key. A logger-level filter does NOT see records from child
    # loggers (httpcore emits via httpcore.http11 etc., where a filter on "httpcore"
    # would be a silent no-op — self-review finding), so the root handlers get the
    # filter too: every propagated record from any logger passes through them. Same
    # idempotence contract as basicConfig above: never stack a duplicate filter.
    httpx_logger = logging.getLogger("httpx")
    if not any(isinstance(f, SecretUrlRedactionFilter) for f in httpx_logger.filters):
        httpx_logger.addFilter(SecretUrlRedactionFilter())
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, SecretUrlRedactionFilter) for f in handler.filters):
            handler.addFilter(SecretUrlRedactionFilter())
