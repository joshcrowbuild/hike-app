"""Doc-lint regression guard for the commons-fork false ✅ (Epic 010 S1, AC-1.5).

gap-audit C1: the committed decision log marked the commons forked write ✅ while
it was never built — wrong memory is worse than none (CLAUDE.md). This test greps
the EXACT commons-fork lines that carried the false ✅ and fails if any regresses
to ✅. It deliberately targets the committed `decision-log.md` §30/§31 bullets and
`stage-6-watch-integration.md` S6-10 — NOT `decision-log-additions-proposed.md
§32` (the Stage-3 ingestion section, which carries no commons-fork claim and would
make the guard pass vacuously — the same C1 failure mode this epic kills).
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _lines(rel: str) -> list[str]:
    return (_ROOT / rel).read_text(encoding="utf-8").splitlines()


def test_s1_no_false_commons_checkmark_decision_log() -> None:
    """AC-1.5: the §30 'Commons write for episodes' and §31 'Commons fork' bullets
    in committed decision-log.md must read 🔶 (designed, not built), never ✅."""
    bullets = [
        ln
        for ln in _lines("docs/decision-log.md")
        if ln.lstrip().startswith("- **Commons write for episodes:**")
        or ln.lstrip().startswith("- **Commons fork:**")
    ]
    assert len(bullets) == 2, f"expected both commons-fork bullets, found {len(bullets)}"
    for ln in bullets:
        assert "✅" not in ln, f"false commons-fork ✅ regressed in decision-log: {ln!r}"
        assert "🔶" in ln, f"commons-fork bullet must carry 🔶: {ln!r}"


def test_s6_ac1_commons_opt_in_default_off_in_schema() -> None:
    """AC-6.1: :Person carries commons_opt_in seeded false (default-OFF substrate);
    AC-2.6: the :CommonsObservation uniqueness constraint exists. Schema-lint so the
    default-OFF flag + the constraint are guarded invariants, not untested seeds."""
    schema = (_ROOT / "graph/schema.cypher").read_text(encoding="utf-8")
    assert "commons_opt_in = false" in schema  # AC-6.1 default-OFF
    assert "FOR (co:CommonsObservation) REQUIRE co.observation_id IS UNIQUE" in schema  # AC-2.6


def test_s1_no_false_commons_checkmark_stage6() -> None:
    """AC-1.5: the S6-10 decision-table row in stage-6-watch-integration.md must
    read 🔶 'designed, not built — Epic 010 pending', not ✅."""
    rows = [
        ln
        for ln in _lines("docs/research/stage-6-watch-integration.md")
        if ln.startswith("| S6-10 ")
    ]
    assert len(rows) == 1, f"expected exactly one S6-10 row, found {len(rows)}"
    row = rows[0]
    assert "✅" not in row, f"false commons-fork ✅ regressed in stage-6 S6-10: {row!r}"
    assert "🔶" in row, f"S6-10 must carry 🔶: {row!r}"
