"""Doc-lint guard keeping the commons-fork docs HONEST (Epic 010 S1, AC-1.5).

gap-audit C1 was the lesson "wrong memory is worse than none" (CLAUDE.md): the
decision log marked the commons forked write ✅ *before it was built*. While the
fork stayed unbuilt this guard was INVERTED — it failed the build if the glyphs
read ✅, pinning them to 🔶 "designed, not built — Epic 010 pending". That pin was
correct only as long as the code did not exist.

Epic 010 has since SHIPPED: the de-identified `:CommonsObservation` forked write
is DONE (docs/epics/README.md; `graph.queries.create_commons_observation`, forked
inside `create_episode()`'s transaction). So the old pin would now force the docs
to keep LYING about a shipped feature. The guard is therefore RE-INVERTED here: it
greps the EXACT commons-fork lines and fails if any regresses from the truthful ✅
(built) back to a false 🔶 / "Epic 010 pending". It still targets the committed
`decision-log.md` §30/§31 bullets and `stage-6-watch-integration.md` S6-10 — the
same lines that once carried the false ✅, now policed to stay honest.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _lines(rel: str) -> list[str]:
    return (_ROOT / rel).read_text(encoding="utf-8").splitlines()


def test_s1_no_false_commons_checkmark_decision_log() -> None:
    """AC-1.5 (re-inverted post-Epic-010): the §30 'Commons write for episodes' and
    §31 'Commons fork' bullets in committed decision-log.md must read ✅ (built) and
    never regress to a false 🔶 / 'Epic 010 pending' now that the fork has shipped."""
    bullets = [
        ln
        for ln in _lines("docs/decision-log.md")
        if ln.lstrip().startswith("- **Commons write for episodes:**")
        or ln.lstrip().startswith("- **Commons fork:**")
    ]
    assert len(bullets) == 2, f"expected both commons-fork bullets, found {len(bullets)}"
    for ln in bullets:
        assert "✅" in ln, f"commons-fork bullet must read ✅ (Epic 010 shipped): {ln!r}"
        assert "🔶" not in ln, f"false 'pending' 🔶 regressed in decision-log: {ln!r}"
        assert "Epic 010 pending" not in ln, f"stale 'Epic 010 pending' regressed: {ln!r}"


def test_s6_ac1_commons_opt_in_default_off_in_schema() -> None:
    """AC-6.1: :Person carries commons_opt_in seeded false (default-OFF substrate);
    AC-2.6: the :CommonsObservation uniqueness constraint exists. Schema-lint so the
    default-OFF flag + the constraint are guarded invariants, not untested seeds."""
    schema = (_ROOT / "graph/schema.cypher").read_text(encoding="utf-8")
    assert "commons_opt_in = false" in schema  # AC-6.1 default-OFF
    assert "FOR (co:CommonsObservation) REQUIRE co.observation_id IS UNIQUE" in schema  # AC-2.6


def test_s1_no_false_commons_checkmark_stage6() -> None:
    """AC-1.5 (re-inverted post-Epic-010): the S6-10 decision-table row in
    stage-6-watch-integration.md must read ✅ (built), never a false 🔶 /
    'Epic 010 pending' now that the fork has shipped."""
    rows = [
        ln
        for ln in _lines("docs/research/stage-6-watch-integration.md")
        if ln.startswith("| S6-10 ")
    ]
    assert len(rows) == 1, f"expected exactly one S6-10 row, found {len(rows)}"
    row = rows[0]
    assert "✅" in row, f"S6-10 must read ✅ (Epic 010 shipped): {row!r}"
    assert "🔶" not in row, f"false 'pending' 🔶 regressed in stage-6 S6-10: {row!r}"
    assert "Epic 010 pending" not in row, f"stale 'Epic 010 pending' regressed in S6-10: {row!r}"
