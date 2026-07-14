#!/usr/bin/env python3
"""Static lint for Rule #4: owned-label Cypher reads must be scoped to owner_id.

Scans orchestration/, api/, and graph/ for Cypher string literals that reference
an OWNED label (Episode, Belief, PhysicalProfile, Outcome, PartyProfile) and
verifies each such read carries a viewer/owner scope clause ($viewer_id / owner_id
= $viewer_id / $granted_ids). Exits non-zero and names file:line on any unscoped
owned read.

Supports `# noqa: owned-read <reason>` inline escape hatch for legitimate
non-viewer contexts (e.g., owner-scoped belief recount).

JOIN-AWARE (M10): a `graph.queries` builder commonly assembles one Cypher
statement out of several sibling string-literal fragments —
``cypher = ("MATCH (e:Episode {episode_id: $eid})\\n", f"WHERE {owner_scope('e')}\\n",
...)`` or, via Python's own adjacent-literal concatenation,
``cypher = ("MATCH ...\\n" f"WHERE {owner_scope('e')}\\n" "RETURN ...")``. Checking
each fragment in isolation is fragment-blind: the owned `MATCH` fragment carries no
scope token, so a naive per-fragment scan either false-positives (forcing a blanket
`# noqa`) or, worse, could miss a genuinely unscoped read hiding behind an unrelated
scoped sibling. `find_cypher_groups` below resolves the whole assembled expression
(implicit/adjacent concatenation, explicit `+`, and f-string parts within one
assignment) to the single string the seam will actually execute, and checks THAT —
so a multi-fragment read scoped anywhere in the assembly passes without a `# noqa`,
while one with no scope anywhere in the assembly still fails.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Import the authoritative owned-label set from the schema.
try:
    from graph.queries import OWNED_LABELS
except ImportError:
    # Fallback if import fails (e.g., in a minimal test environment).
    OWNED_LABELS = frozenset({"Episode", "Belief", "PhysicalProfile", "Outcome", "PartyProfile"})


# Regex to match an OWNED label in Cypher (case-insensitive label names,
# word boundary to avoid false matches like "EpisodeData").
_OWNED_LABEL_PATTERN = r":\s*(?:" + "|".join(sorted(OWNED_LABELS)) + r")\b"
_OWNED_LABEL_RE = re.compile(_OWNED_LABEL_PATTERN, re.IGNORECASE)

# Regex to match a scope clause. Recognizes multiple forms:
# 1. WHERE clause with owner_id = $viewer_id or owner_id IN $granted_ids
# 2. owner_scope(...) function call
# 3. A map-pattern key `owner_id: $viewer_id`, viewer-only (e.g. the MERGE key
#    `{episode_id: $eid, owner_id: $viewer_id}`) — NOT anchored to `{owner_id: ...}`
#    being the pattern's ONLY key, since a real MERGE key is almost always multi-key
#    (natural id + owner_id); requiring an exclusive-key brace pair made this the
#    hollow half of the M9 lint that forced a blanket lint-escape comment on every
#    such write/read once join-awareness (M10) stopped masking it via fragment-
#    blindness.
# Uses DOTALL so . matches newlines in multiline strings.
_SCOPE_CLAUSE_RE = re.compile(
    r"(?:WHERE\s+.*?(?:owner_id\s*=\s*\$viewer_id|owner_id\s*IN\s*\$granted_ids))|"
    r"(?:owner_scope\s*\()|"
    r"(?:owner_id\s*:\s*\$viewer_id)",
    re.DOTALL | re.IGNORECASE,
)

# Regex to match the noqa escape hatch (with or without owned-read code).
# We accept both plain noqa and noqa with owned-read specification.
_NOQA_PATTERN = r"#\s*noqa(?:\s*:\s*owned-read)?\b"
_NOQA_RE = re.compile(_NOQA_PATTERN)


_CYPHER_START_RE = re.compile(r"(?:MATCH|CREATE|MERGE|WITH|OPTIONAL|RETURN|CALL|DELETE|SET)\b")


def _is_owner_scope_call(call: ast.Call) -> bool:
    return isinstance(call.func, ast.Name) and call.func.id == "owner_scope"


def _resolve_literal(node: ast.AST) -> str | None:
    """Best-effort literal text for one AST node, joining sibling fragments that
    Python concatenates into a single Cypher string at runtime.

    Returns None when the node contains a piece that cannot be resolved to text
    (an opaque variable/call other than `owner_scope(...)`) — the caller then
    knows the assembly is only PARTIALLY known and must not silently treat the
    unresolved part as scope-bearing, but also must not drop it and pretend the
    rest of the string is the whole query (see `_first_resolvable_prefix` below,
    which recovers a checkable prefix instead)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                if isinstance(value.value, ast.Call) and _is_owner_scope_call(value.value):
                    # Contributes the literal substring the runtime scope guards
                    # (`assert_scoped_read` / the static `_SCOPE_CLAUSE_RE`) key on,
                    # without needing to evaluate `owner_scope`'s actual return value.
                    parts.append("owner_scope(")
                else:
                    return None  # opaque interpolation — can't resolve losslessly
            else:
                return None
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_literal(node.left)
        right = _resolve_literal(node.right)
        if left is None or right is None:
            return None
        return left + right
    return None


def _line_span_or_none(node: ast.AST) -> tuple[int, int] | None:
    """Recursive worker for `_line_span`. Returns None for a subtree with no
    location info anywhere in it (an operator/context singleton and all its
    childless descendants), so the caller can skip it instead of polluting the
    min/max with a fabricated default."""
    lo = getattr(node, "lineno", None)
    hi = getattr(node, "end_lineno", None) or lo
    for child in ast.iter_child_nodes(node):
        child_span = _line_span_or_none(child)
        if child_span is None:
            continue
        child_lo, child_hi = child_span
        lo = child_lo if lo is None else min(lo, child_lo)
        hi = child_hi if hi is None else max(hi, child_hi)
    return None if lo is None else (lo, hi)


def _line_span(node: ast.AST) -> tuple[int, int]:
    """The (min, max) line numbers spanned by `node` and its descendants.

    Location-less nodes (operator/context singletons like `ast.Add`/`ast.Load`,
    which carry no `lineno` at all) must be SKIPPED, not defaulted to line 1 — an
    early version defaulted via `getattr(node, "lineno", 1)`, which silently
    dragged every group's start line down to 1 the moment a `BinOp`/`JoinedStr`
    appeared in the tree (their `op`/`ctx` children have no position). That's a
    false noqa-detection widener: `check_cypher_group` would then treat ANY noqa
    comment anywhere in the first `end_line` lines of the whole file as escaping
    the group, which is far too permissive for a security-sensitive lint.

    `node` itself is always a real expression (Constant/JoinedStr/BinOp — see
    `find_cypher_groups`' callers), so it always carries its own `lineno` and this
    can never actually return None in practice; the Optional-handling recursion
    lives in `_line_span_or_none`."""
    span = _line_span_or_none(node)
    assert span is not None, f"expected {node!r} to carry position info"
    return span


def find_cypher_groups(tree: ast.AST) -> list[tuple[str, int, int]]:
    """Find every Cypher-shaped string EXPRESSION in the module, joining sibling
    literal fragments that concatenate into one Cypher string (implicit/adjacent
    concatenation, `+`, and f-string parts) into a single (text, start_line,
    end_line) triple. Only whole top-level expressions are considered (an
    `Assign`'s value, or a bare expression statement) — a fragment nested inside
    an already-visited expression is never re-examined on its own, which is
    exactly what closes the fragment-blindness gap: the owned `MATCH` and its
    `WHERE owner_scope(...)` sibling are seen and scope-checked TOGETHER.

    Falls back to per-leaf-literal scanning for any string that is not the
    direct value of an `Assign`/expression-statement (e.g. a literal buried
    inside a call's argument list that isn't itself string-concatenated) so
    no Cypher-shaped literal goes unchecked.
    """
    groups: list[tuple[str, int, int]] = []
    seen_ids: set[int] = set()

    def _maybe_group(value_node: ast.AST) -> None:
        if not isinstance(value_node, (ast.Constant, ast.JoinedStr, ast.BinOp)):
            return
        text = _resolve_literal(value_node)
        candidate = text if text is not None else _first_resolvable_prefix(value_node)
        if candidate is None or len(candidate) <= 20:
            return
        if not _CYPHER_START_RE.match(candidate.lstrip()):
            return
        lo, hi = _line_span(value_node)
        groups.append((candidate, lo, hi))
        for sub in ast.walk(value_node):
            seen_ids.add(id(sub))

    class RootVisitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            _maybe_group(node.value)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if node.value is not None:
                _maybe_group(node.value)
            self.generic_visit(node)

        def visit_Return(self, node: ast.Return) -> None:
            # `return cypher_expr, {...}` — the first tuple element inline.
            if isinstance(node.value, ast.Tuple) and node.value.elts:
                _maybe_group(node.value.elts[0])
            self.generic_visit(node)

    RootVisitor().visit(tree)

    # Fallback: any Cypher-shaped Constant leaf not already covered by a group
    # above (preserves single-fragment detection for call-argument literals,
    # e.g. `runner("MATCH ...", params)`, that never sat under an Assign/Return).
    class LeafVisitor(ast.NodeVisitor):
        def visit_Constant(self, node: ast.Constant) -> None:
            if id(node) in seen_ids:
                return
            if isinstance(node.value, str) and len(node.value) > 20:
                trimmed = node.value.lstrip()
                if _CYPHER_START_RE.match(trimmed):
                    groups.append((node.value, node.lineno, node.lineno))

    LeafVisitor().visit(tree)
    return groups


def _first_resolvable_prefix(node: ast.AST) -> str | None:
    """When a `+`/f-string assembly has an unresolvable tail (e.g. a `+`-chain
    that ends in a module-level Name the lint can't inline), still recover the
    resolvable PREFIX so a Cypher-shaped opener is checked rather than silently
    dropped. Conservative in the safe direction: if the prefix alone already
    carries an owned label with no scope token, the (possibly scope-bearing) tail
    could in principle rescue it — but every such case in this codebase is a
    world-only builder (`graph/load.py`'s `guard + "MATCH (node:CanonicalTrail)..."`),
    so in practice this only ever fires on labels outside `OWNED_LABELS`, where the
    scope question is moot. `check_cypher_string` still short-circuits to None the
    instant no OWNED label is found in the string it's given."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_literal(node.left)
        if left is not None:
            return left
        return _first_resolvable_prefix(node.left)
    if isinstance(node, ast.JoinedStr) and node.values:
        first = node.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def check_cypher_group(
    cypher: str,
    start_line: int,
    end_line: int,
    filename: str,
    source_lines: list[str],
) -> str | None:
    """Check one ASSEMBLED Cypher expression (start_line..end_line inclusive) for an
    unscoped owned-label read. `cypher` is the already-joined text of every sibling
    fragment in the expression, so a scope token anywhere in the assembly — not just
    the fragment nearest the owned `MATCH` — satisfies the guard (the join-aware fix;
    see the module docstring). Returns an error message if unscoped, None if OK or if
    OWNED labels aren't used.
    """
    # Skip if no OWNED labels present.
    if not _OWNED_LABEL_RE.search(cypher):
        return None

    # A noqa anywhere in the assembled expression's line span (or the line just
    # before it starts) escapes the whole group — matching how a developer would
    # naturally place it: on the opening `cypher = (` line, or on whichever
    # fragment line reads most naturally.
    check_lines = []
    if start_line > 1 and start_line - 2 < len(source_lines):
        check_lines.append(source_lines[start_line - 2])
    for lineno in range(start_line, end_line + 1):
        if lineno <= len(source_lines):
            check_lines.append(source_lines[lineno - 1])

    if any(_NOQA_RE.search(check_line) for check_line in check_lines):
        return None  # Escaped by noqa

    # Check if a scope clause is present anywhere in the joined text.
    if not _SCOPE_CLAUSE_RE.search(cypher):
        found_labels = sorted(set(re.findall(r":\s*(\w+)\b", cypher)))
        found_labels = [label for label in found_labels if label in OWNED_LABELS]
        labels_str = ", ".join(found_labels) if found_labels else "owned label"
        return (
            f"{filename}:{start_line}: unscoped read on owned label ({labels_str}) — "
            "add WHERE clause with owner_id = $viewer_id or owner_id IN $granted_ids, "
            "or use # noqa: owned-read <reason> if this is a legitimate non-viewer context"
        )

    return None


def check_cypher_string(
    cypher: str, line: int, filename: str, source_lines: list[str]
) -> str | None:
    """Single-line convenience wrapper over `check_cypher_group` (kept for existing
    per-fragment callers/tests) — equivalent to a group spanning just `line`."""
    return check_cypher_group(cypher, line, line, filename, source_lines)


def scan_file(filepath: Path) -> list[str]:
    """Scan a Python file for unscoped owned-label Cypher reads.

    Returns a list of error messages for unscoped reads.
    """
    try:
        source = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        print(f"warning: could not read {filepath}: {e}", file=sys.stderr)
        return []

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        print(f"warning: could not parse {filepath}: {e}", file=sys.stderr)
        return []

    source_lines = source.split("\n")
    errors = []

    for cypher, start_line, end_line in find_cypher_groups(tree):
        error = check_cypher_group(cypher, start_line, end_line, str(filepath), source_lines)
        if error:
            errors.append(error)

    return errors


def main() -> int:
    """Scan all Python files in orchestration/, api/, and graph/ directories.

    Exits with 0 if no unscoped reads found, 1 otherwise.
    """
    repo_root = Path(__file__).parent.parent
    dirs_to_scan = [
        repo_root / "orchestration",
        repo_root / "api",
        repo_root / "graph",
    ]

    all_errors = []
    for scan_dir in dirs_to_scan:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            errors = scan_file(py_file)
            all_errors.extend(errors)

    if all_errors:
        for error in sorted(all_errors):
            print(error)
        return 1

    print("✓ All owned-label Cypher reads are properly scoped (or escaped with # noqa: owned-read)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
