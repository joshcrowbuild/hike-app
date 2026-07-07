"""Tests for scripts/apply_schema.py — the Aura/remote schema applier.

Only the pure statement splitter is unit-tested (no DB). The splitter is the part
that can silently corrupt a schema apply (a `;` inside a string or comment must not
split a statement), so it gets the coverage.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_MOD_PATH = _REPO / "scripts" / "apply_schema.py"
_spec = importlib.util.spec_from_file_location("apply_schema", _MOD_PATH)
assert _spec and _spec.loader
apply_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apply_schema)
split_statements = apply_schema.split_statements


def test_splits_on_top_level_semicolons() -> None:
    assert split_statements("CREATE (a); CREATE (b);") == ["CREATE (a)", "CREATE (b)"]


def test_trailing_statement_without_semicolon_is_kept() -> None:
    assert split_statements("RETURN 1") == ["RETURN 1"]


def test_empty_and_whitespace_only_yield_nothing() -> None:
    assert split_statements("   ;\n\n  ; ") == []


def test_line_comments_are_dropped() -> None:
    out = split_statements("// header\nCREATE (a);\n// note\nCREATE (b);")
    assert out == ["CREATE (a)", "CREATE (b)"]


def test_semicolon_inside_double_quoted_string_does_not_split() -> None:
    assert split_statements('MERGE (s:Source {name: "a;b"});') == ['MERGE (s:Source {name: "a;b"})']


def test_semicolon_inside_single_quoted_string_does_not_split() -> None:
    assert split_statements("MERGE (s {v: 'x;y'});") == ["MERGE (s {v: 'x;y'})"]


def test_escaped_quote_inside_string_does_not_end_it() -> None:
    # the escaped quote keeps us "in string", so the ';' stays part of one statement
    out = split_statements(r'CREATE (n {s: "a\";b"}); RETURN 1;')
    assert out == [r'CREATE (n {s: "a\";b"})', "RETURN 1"]


def test_semicolon_inside_block_comment_does_not_split() -> None:
    out = split_statements("/* a; b */ CREATE (a);")
    assert len(out) == 1 and "CREATE (a)" in out[0]


def test_real_schema_parses_to_nonempty_executable_statements() -> None:
    stmts = split_statements((_REPO / "graph" / "schema.cypher").read_text())
    assert len(stmts) >= 30
    for s in stmts:
        assert s.strip(), "no empty statements"
        assert not s.lstrip().startswith("//"), "no pure-comment statements"
    joined = " ".join(stmts).upper()
    assert "CREATE CONSTRAINT" in joined and "MERGE" in joined


def test_schema_stamps_integer_schema_format_on_meta() -> None:
    """Epic 024 AC-1.1/1.4: schema.cypher sets an integer schema_format literal on
    :Meta in both the ON CREATE and ON MATCH branches (never a string like "1")."""
    text = (_REPO / "graph" / "schema.cypher").read_text()
    stmts = split_statements(text)
    meta_stmt = next(s for s in stmts if 'Meta {id: "schema"}' in s)
    assert "m.schema_format = 1" in meta_stmt
    assert 'm.schema_format = "1"' not in meta_stmt
    assert meta_stmt.count("m.schema_format = 1") == 2  # ON CREATE and ON MATCH
