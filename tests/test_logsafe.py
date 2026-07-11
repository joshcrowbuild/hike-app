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
