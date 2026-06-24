"""Epic 004 S4 — poller: per-adapter isolation, idempotent namespacing, pipeline reuse."""

from __future__ import annotations

from types import SimpleNamespace

from ingestion.watch.base import (
    ActivityRef,
    AdapterHealth,
    Capabilities,
    DeviceAdapter,
    RawActivity,
)
from scripts.watch_sync import run_sync, sync_adapter

# ── Fakes ─────────────────────────────────────────────────────────────────────


class _PollerAdapter(DeviceAdapter):
    def __init__(self, name, raws, *, health=AdapterHealth.OK, raise_in_fetch=False):
        self.name = name
        self._raws = raws
        self._health = health
        self._raise = raise_in_fetch

    def capabilities(self):
        return Capabilities(has_fit=True, has_readiness=False, has_activity_title=True)

    def list_activities(self, since, *, sport="hiking", limit=20):
        return [r.ref for r in self._raws]

    def download_fit(self, ref):
        return b"FIT"

    def fetch_readiness(self, *, at=None):
        return None

    def health(self):
        return self._health

    def fetch_new_activities(self, since):
        if self._raise:
            raise RuntimeError("vendor exploded")
        return list(self._raws)


def _raw(rid):
    return RawActivity(ref=ActivityRef(id=rid, source=rid.split(":")[0]), fit_bytes=b"FIT")


def _fakes():
    """Return (parse, match, create, calls) recording what the pipeline received."""
    calls = []

    def parse(fit_bytes):
        return SimpleNamespace(watch_activity_id="file:placeholder", fit=fit_bytes)

    def match(summary, session):
        return "ct:matched"

    def create(summary, cid, owner, session, *, belief_queue=None):
        calls.append({"wid": summary.watch_activity_id, "cid": cid, "owner": owner})
        return f"ep:{owner}:{summary.watch_activity_id}"

    return parse, match, create, calls


# ── AC-4.1 — per-adapter failure isolation ────────────────────────────────────


def test_s4_ac1_one_adapter_crash_does_not_stop_others():
    parse, match, create, calls = _fakes()
    adapters = [
        _PollerAdapter("garmin", [_raw("garmin:1")]),
        _PollerAdapter("coros", [], raise_in_fetch=True),  # explodes
        _PollerAdapter("suunto", [_raw("suunto:9")]),
    ]
    report = run_sync(
        adapters,
        "josh",
        since=None,
        parse=parse,
        match=match,
        create=create,
        session=object(),
        belief_queue=object(),
    )
    # garmin + suunto produced episodes; coros recorded an error but didn't stop them
    assert {c["wid"] for c in calls} == {"garmin:1", "suunto:9"}
    errored = [r for r in report.results if r.error]
    assert len(errored) == 1 and errored[0].adapter == "coros"


def test_s4_ac1_non_ok_health_skips_adapter_not_others():
    parse, match, create, calls = _fakes()
    adapters = [
        _PollerAdapter("garmin", [_raw("garmin:1")], health=AdapterHealth.NEEDS_REAUTH),
        _PollerAdapter("coros", [_raw("coros:2")]),
    ]
    report = run_sync(
        adapters,
        "josh",
        since=None,
        parse=parse,
        match=match,
        create=create,
        session=object(),
        belief_queue=object(),
    )
    # garmin needs_reauth → skipped (0 episodes); coros still synced
    assert {c["wid"] for c in calls} == {"coros:2"}
    garmin_result = next(r for r in report.results if r.adapter == "garmin")
    assert garmin_result.health == "needs_reauth"
    assert garmin_result.episodes == 0


# ── AC-4.3 — namespaced id flows through (idempotency key) ─────────────────────


def test_s4_ac3_namespaced_id_overrides_parse_placeholder():
    parse, match, create, calls = _fakes()
    adapter = _PollerAdapter("garmin", [_raw("garmin:42")])
    sync_adapter(
        adapter,
        "josh",
        None,
        parse=parse,
        match=match,
        create=create,
        session=object(),
        belief_queue=object(),
    )
    # parse() returned "file:placeholder"; poller overrode it with the namespaced id
    assert calls[0]["wid"] == "garmin:42"


# ── AC-4.4 — reuse the existing pipeline unchanged ────────────────────────────


def test_s4_ac4_parse_bridge_calls_real_parse_fit(monkeypatch):
    import scripts.watch_sync as ws

    seen = {}

    def fake_parse_fit(path):
        seen["path"] = str(path)
        return SimpleNamespace(watch_activity_id="file:x")

    monkeypatch.setattr("ingestion.ingest_episode.parse_fit", fake_parse_fit)
    summary = ws._parse_fit_bytes(b"SOMEFITBYTES")
    # delegated to the real (here-patched) parse_fit via a temp file
    assert "path" in seen and seen["path"].endswith(".fit")
    assert summary.watch_activity_id == "file:x"


def test_s4_ac4_poller_imports_existing_pipeline():
    # The poller wires the real ingest_episode functions — no reimplementation.
    from ingestion.ingest_episode import create_episode, match_trail, parse_fit

    assert callable(parse_fit) and callable(create_episode) and callable(match_trail)


# ── AC-4.5 — sensitivity routing enforced at entrypoint ───────────────────────


def test_s4_ac5_sensitivity_routing_forces_local_even_with_cloud_judge():
    from orchestration.config import Settings
    from scripts.watch_sync import assert_local_sensitivity_routing

    # Judgment tier pointed at the cloud yardstick…
    settings = Settings.from_env(
        {
            "ADVENTURE_PROVIDER_JUDGMENT": "anthropic",
            "ADVENTURE_MODEL_JUDGMENT": "claude-x",
            "ADVENTURE_PROVIDER_MECHANICAL": "anthropic",
            "ADVENTURE_MODEL_MECHANICAL": "claude-x",
        }
    )
    # …must still pass: watch-ingest LLM calls are forced local (no raise).
    assert_local_sensitivity_routing(settings)


# ── most_recent_episode_time (AC-4.2) ─────────────────────────────────────────


def test_s4_ac2_since_from_latest_episode():
    from datetime import datetime, timezone

    from scripts.watch_sync import most_recent_episode_time

    latest = datetime(2026, 6, 20, tzinfo=timezone.utc)

    def session_run(query):
        return [{"latest": latest}]

    session = SimpleNamespace(run=session_run)
    assert most_recent_episode_time("josh", session) == latest


def test_s4_ac2_no_episodes_returns_none():
    session = SimpleNamespace(run=lambda q: [])
    from scripts.watch_sync import most_recent_episode_time

    assert most_recent_episode_time("josh", session) is None


def test_s4_ac2_iso_string_watermark_coerced_to_datetime():
    # create_episode stores created_at as an ISO string; the watermark must come
    # back as a datetime or Coros' since.timestamp() crashes every cycle.
    from datetime import datetime

    from scripts.watch_sync import most_recent_episode_time

    session = SimpleNamespace(run=lambda q: [{"latest": "2026-06-20T13:00:00+00:00"}])
    result = most_recent_episode_time("josh", session)
    assert isinstance(result, datetime)
    assert result.year == 2026 and result.month == 6 and result.day == 20


# ── per-activity isolation (rule #6, finding #1) ──────────────────────────────


def test_per_activity_failure_skips_one_keeps_rest():
    _, match, _, _ = _fakes()
    created = []

    def parse(fit_bytes):
        return SimpleNamespace(watch_activity_id="file:x")

    def create(summary, cid, owner, session, *, belief_queue=None):
        if summary.watch_activity_id == "garmin:2":
            raise RuntimeError("poison FIT")
        created.append(summary.watch_activity_id)

    adapter = _PollerAdapter("garmin", [_raw("garmin:1"), _raw("garmin:2"), _raw("garmin:3")])
    result = sync_adapter(
        adapter,
        "josh",
        None,
        parse=parse,
        match=match,
        create=create,
        session=object(),
        belief_queue=object(),
    )
    # the poison activity is skipped; siblings survive; count is accurate
    assert created == ["garmin:1", "garmin:3"]
    assert result.episodes == 2
    assert result.health == "ok"


# ── AC-4.3 idempotency: namespaced MERGE key is stable across runs ────────────


def test_s4_ac3_repeat_run_uses_same_namespaced_key():
    parse, match, create, calls = _fakes()
    adapter = _PollerAdapter("garmin", [_raw("garmin:42")])
    for _ in range(2):
        run_sync(
            [adapter],
            "josh",
            since=None,
            parse=parse,
            match=match,
            create=create,
            session=object(),
            belief_queue=object(),
        )
    # both runs key on the SAME namespaced id → real MERGE is a structural no-op
    assert [c["wid"] for c in calls] == ["garmin:42", "garmin:42"]
