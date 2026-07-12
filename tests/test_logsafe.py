"""Log hygiene (Phase B, rule #5): identifiers that name a member — viewer_id,
owner_id, and episode_id (whose ``ep:{owner_id}:{activity}`` shape embeds the
owner) — never reach a log line in the clear, and the process logging config is
coherent (idempotent, env-driven level, never a duplicate handler)."""

from __future__ import annotations

import logging

from orchestration.logsafe import scrub_episode, scrub_viewer, setup_logging


class TestScrubViewer:
    def test_anonymous_stays_legible(self) -> None:
        assert scrub_viewer("anonymous") == "anon"

    def test_real_identity_never_appears(self) -> None:
        tag = scrub_viewer("josh@example.com")
        assert "josh" not in tag
        assert tag.startswith("vh:")
        assert len(tag) == len("vh:") + 8

    def test_stable_within_a_deploy(self, monkeypatch) -> None:
        monkeypatch.setenv("ADVENTURE_LOG_HASH_SALT", "s1")
        assert scrub_viewer("mem:josh") == scrub_viewer("mem:josh")

    def test_salt_changes_the_digest(self, monkeypatch) -> None:
        monkeypatch.setenv("ADVENTURE_LOG_HASH_SALT", "s1")
        first = scrub_viewer("mem:josh")
        monkeypatch.setenv("ADVENTURE_LOG_HASH_SALT", "s2")
        assert scrub_viewer("mem:josh") != first


class TestScrubEpisode:
    def test_owner_segment_never_appears(self) -> None:
        # episode ids are ep:{owner_id}:{activity} — the owner id must not survive.
        tag = scrub_episode("ep:josh-real-identity:garmin:act-1")
        assert "josh-real-identity" not in tag
        assert "garmin" not in tag  # the activity id is linkable device data too
        assert tag.startswith("eh:")

    def test_stable_for_correlation(self) -> None:
        assert scrub_episode("ep:a:1") == scrub_episode("ep:a:1")
        assert scrub_episode("ep:a:1") != scrub_episode("ep:a:2")


class TestSetupLogging:
    def test_sets_level_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ADVENTURE_LOG_LEVEL", "debug")
        setup_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_explicit_level_wins(self, monkeypatch) -> None:
        monkeypatch.setenv("ADVENTURE_LOG_LEVEL", "ERROR")
        setup_logging("WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_unknown_level_degrades_to_info(self, monkeypatch) -> None:
        monkeypatch.setenv("ADVENTURE_LOG_LEVEL", "LOUD")
        setup_logging()
        assert logging.getLogger().level == logging.INFO

    def test_idempotent_no_duplicate_handlers(self) -> None:
        setup_logging("INFO")
        count_after_first = len(logging.getLogger().handlers)
        setup_logging("INFO")
        assert len(logging.getLogger().handlers) == count_after_first


class _CapturingHandler(logging.Handler):
    """Collects the final rendered messages exactly as a real handler would see them."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class TestSecretUrlRedaction:
    """2026-07-12 review: httpx logs each request line at INFO with the full URL —
    FIRMS carries FIRMS_MAP_KEY as a path segment and AirNow carries API_KEY as a
    query param, so those lines printed live keys into production logs. The filter
    installed by setup_logging must mask the key before ANY handler sees the record."""

    def _emit_through_httpx_logger(self, msg: str, *args: object) -> list[str]:
        setup_logging("INFO")
        httpx_logger = logging.getLogger("httpx")
        handler = _CapturingHandler()
        httpx_logger.addHandler(handler)
        try:
            # The httpx idiom exactly: a %s format string with the URL in args.
            httpx_logger.info(msg, *args)
        finally:
            httpx_logger.removeHandler(handler)
        return handler.messages

    def test_firms_map_key_in_url_path_never_reaches_a_handler(self) -> None:
        url = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/SECRET-MAP-KEY/VIIRS_SNPP_NRT/-78.9,38.0,-77.9,39.0/1"
        messages = self._emit_through_httpx_logger(
            'HTTP Request: %s %s "%s"', "GET", url, "HTTP/1.1 200 OK"
        )
        assert messages, "expected the record to reach the handler"
        assert not any("SECRET-MAP-KEY" in m for m in messages)
        # The rest of the request line survives — that is the point of a redaction
        # filter over demoting httpx to WARNING.
        assert any("firms.modaps.eosdis.nasa.gov" in m and "GET" in m for m in messages)

    def test_airnow_api_key_query_param_never_reaches_a_handler(self) -> None:
        url = (
            "https://www.airnowapi.org/aq/observation/latLong/current/"
            "?format=application%2Fjson&latitude=38.5&longitude=-78.4"
            "&distance=50&API_KEY=secret-airnow-key"
        )
        messages = self._emit_through_httpx_logger(
            'HTTP Request: %s %s "%s"', "GET", url, "HTTP/1.1 200 OK"
        )
        assert messages, "expected the record to reach the handler"
        assert not any("secret-airnow-key" in m for m in messages)
        assert any("airnowapi.org" in m and "latitude=38.5" in m for m in messages)

    def test_keyless_request_lines_pass_through_untouched(self) -> None:
        line = 'HTTP Request: GET https://api.weather.gov/points/38.5,-78.4 "HTTP/1.1 200 OK"'
        messages = self._emit_through_httpx_logger(line)
        assert messages == [line]

    def test_filter_is_not_stacked_on_repeated_setup(self) -> None:
        from orchestration.logsafe import SecretUrlRedactionFilter

        setup_logging("INFO")
        setup_logging("INFO")
        filters = logging.getLogger("httpx").filters
        assert sum(isinstance(f, SecretUrlRedactionFilter) for f in filters) == 1
        for handler in logging.getLogger().handlers:
            assert sum(isinstance(f, SecretUrlRedactionFilter) for f in handler.filters) == 1

    def test_root_handlers_carry_the_filter_for_child_logger_records(self) -> None:
        # A logger-level filter never sees a CHILD logger's records (httpcore emits via
        # httpcore.http11 etc. — self-review finding), so coverage for those comes from
        # the root handlers, which every propagated record passes through.
        from orchestration.logsafe import SecretUrlRedactionFilter

        setup_logging("INFO")
        assert logging.getLogger().handlers, "setup_logging must configure a root handler"
        for handler in logging.getLogger().handlers:
            assert any(isinstance(f, SecretUrlRedactionFilter) for f in handler.filters)

        # And a filtered handler masks an httpcore.http11-style record end-to-end.
        capturing = _CapturingHandler()
        capturing.addFilter(SecretUrlRedactionFilter())
        child_logger = logging.getLogger("httpcore.http11")
        child_logger.addHandler(capturing)
        try:
            child_logger.info(
                "send_request_headers.started request=<Request [b'GET'] %s>",
                "https://www.airnowapi.org/aq/observation/?API_KEY=secret-airnow-key",
            )
        finally:
            child_logger.removeHandler(capturing)
        assert capturing.messages
        assert not any("secret-airnow-key" in m for m in capturing.messages)


class TestNoRawIdentifiersInLogs:
    """The leak sites fixed in this lane stay fixed: log output from the
    belief-update and outcome paths never carries a raw owner/episode id."""

    def test_belief_queue_drain_failure_scrubs_episode_id(self, caplog) -> None:
        from orchestration.belief_update import BeliefUpdateQueue, UpdateTask

        queue = BeliefUpdateQueue()
        queue.enqueue(
            UpdateTask(
                episode_id="ep:josh-real-identity:act-9",
                owner_id="josh-real-identity",
                distance_m=1000.0,
                ascent_m=10.0,
                pace_on_grade=10.0,
            )
        )

        def _boom_factory(owner_id: str):
            raise RuntimeError("db down")

        with caplog.at_level(logging.ERROR, logger="orchestration.belief_update"):
            queue.drain(_boom_factory)
        messages = [r.getMessage() for r in caplog.records]
        assert messages, "expected the drain failure to be logged"
        assert not any("josh-real-identity" in m for m in messages)

    def test_process_episode_not_found_scrubs_both_ids(self, caplog) -> None:
        from orchestration.belief_update import process_episode

        class _EmptySession:
            def run(self, query: object) -> list:
                return []

        with caplog.at_level(logging.WARNING, logger="orchestration.belief_update"):
            process_episode("ep:josh-real-identity:act-9", "josh-real-identity", _EmptySession())
        messages = [r.getMessage() for r in caplog.records]
        assert messages, "expected the not-found warning to be logged"
        assert not any("josh-real-identity" in m for m in messages)

    def test_episode_not_found_log_scrubs_episode_id(self, caplog) -> None:
        # Extends test_outcome.py's AH4 viewer check: the episode id embeds the
        # owner id, so it must be scrubbed from the same rejection line.
        from orchestration.outcome import OutcomeRequest, write_outcome

        class _EmptyScoped:
            def run(self, query: object) -> list:
                return []

        req = OutcomeRequest(overall=2, skipped=False)
        with caplog.at_level(logging.WARNING, logger="orchestration.outcome"):
            write_outcome("ep:josh-real-identity:act-9", "josh-real-identity", req, _EmptyScoped())
        messages = [r.getMessage() for r in caplog.records]
        assert messages, "expected the rejection warning to be logged"
        assert not any("josh-real-identity" in m for m in messages)

    def test_fit_summary_log_never_carries_heart_rate(self, caplog, monkeypatch) -> None:
        # Heart rate is a biometric (rule #5/#7): the parse-summary line may say HR
        # was present, never its value. dry_run exercises the log without a DB.
        from pathlib import Path

        import ingestion.ingest_episode as mod

        summary = mod.FITSummary(
            watch_activity_id="act-1",
            total_distance_m=15000.0,
            total_ascent_m=735.0,
            total_descent_m=735.0,
            moving_time_s=10800.0,
            total_time_s=12000.0,
            avg_heart_rate=147,
            start_lat=38.5,
            start_lon=-78.4,
            end_lat=38.5,
            end_lon=-78.4,
            sport="hiking",
        )
        monkeypatch.setattr(mod, "parse_fit", lambda _path: summary)
        with caplog.at_level(logging.INFO, logger="ingestion.ingest_episode"):
            mod.ingest_episode(Path("/nonexistent.fit"), "josh-real-identity", dry_run=True)
        messages = [r.getMessage() for r in caplog.records]
        assert messages
        assert not any("147" in m for m in messages)
        assert not any("josh-real-identity" in m for m in messages)
