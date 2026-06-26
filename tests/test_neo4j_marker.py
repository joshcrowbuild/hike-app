"""Epic 015 S1 — the `neo4j` marker isolates DB tests; the fast legs stay DB-free.

These assertions are DB-free (they never open a driver), so they run on every fast
leg. They prove the marker is registered (AC-1.1) and that `make test` deselects it
(AC-1.2), which together guarantee the owner-isolation integration tests never run on
the fast legs or locally without a database.
"""

from __future__ import annotations

from pathlib import Path

_MAKEFILE = Path(__file__).resolve().parent.parent / "Makefile"


def test_s1_ac1_neo4j_marker_registered(pytestconfig) -> None:
    """AC-1.1: the `neo4j` marker is registered under [tool.pytest.ini_options] markers,
    so pytest emits no PytestUnknownMarkWarning (which is an error under -W error)."""
    registered = pytestconfig.getini("markers")
    assert any(entry.split(":", 1)[0].strip() == "neo4j" for entry in registered), (
        "the `neo4j` marker must be registered in pyproject.toml [tool.pytest.ini_options]"
    )


def test_s1_ac2_make_test_deselects_neo4j() -> None:
    """AC-1.2: `make test` runs `pytest ... -m "not neo4j"`, so the DB tests are never
    collected on the fast legs (or locally without a database)."""
    makefile = _MAKEFILE.read_text()
    # the `test:` recipe must carry the deselection
    assert '-m "not neo4j"' in makefile, (
        'the Makefile `test` target must deselect the neo4j marker (-m "not neo4j")'
    )
