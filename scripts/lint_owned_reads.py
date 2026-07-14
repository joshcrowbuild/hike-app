#!/usr/bin/env python3
"""Static lint for Rule #4: owned-label Cypher reads must be scoped to owner_id.

Scans orchestration/, api/, and graph/ for Cypher string literals that reference
an OWNED label (Episode, Belief, PhysicalProfile, Outcome, PartyProfile) and
verifies each such read carries a viewer/owner scope clause ($viewer_id / owner_id
= $viewer_id / $granted_ids). Exits non-zero and names file:line on any unscoped
owned read.

Supports `# noqa: owned-read <reason>` inline escape hatch for legitimate
non-viewer contexts (e.g., owner-scoped belief recount).
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
# 3. MATCH pattern with {owner_id: $viewer_id} (strict form, viewer-only)
# Uses DOTALL so . matches newlines in multiline strings.
_SCOPE_CLAUSE_RE = re.compile(
    r"(?:WHERE\s+.*?(?:owner_id\s*=\s*\$viewer_id|owner_id\s*IN\s*\$granted_ids))|"
    r"(?:owner_scope\s*\()|"
    r"(?:\{owner_id\s*:\s*\$viewer_id\})",
    re.DOTALL | re.IGNORECASE,
)

# Regex to match the noqa escape hatch (with or without owned-read code).
# We accept both plain noqa and noqa with owned-read specification.
_NOQA_PATTERN = r"#\s*noqa(?:\s*:\s*owned-read)?\b"
_NOQA_RE = re.compile(_NOQA_PATTERN)


def find_cypher_strings(node) -> list[tuple[str, int]]:
    """Extract all string literals from an AST node, returning (value, lineno) pairs.

    Only extracts strings that appear to be Cypher (start with a Cypher keyword),
    since the scanner would be too noisy otherwise. This avoids matching
    docstrings, log messages, and other non-Cypher strings.
    """
    strings = []

    class StringVisitor(ast.NodeVisitor):
        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, str) and len(node.value) > 20:
                # Heuristic: Cypher queries typically START with a keyword
                # (after leading whitespace). Match queries that start with
                # uppercase Cypher keywords (MATCH, CREATE, etc.). This avoids
                # matching docstrings like "Delete CanonicalTrails..." which may
                # contain event label names but aren't Cypher code.
                trimmed = node.value.lstrip()
                # Require uppercase to avoid matching docstrings ("Delete" != "DELETE")
                if re.match(
                    r"(?:MATCH|CREATE|MERGE|WITH|OPTIONAL|RETURN|CALL|DELETE|SET)\b",
                    trimmed,
                ):
                    strings.append((node.value, node.lineno))

    StringVisitor().visit(node)
    return strings


def check_cypher_string(
    cypher: str, line: int, filename: str, source_lines: list[str]
) -> str | None:
    """Check a single Cypher string for unscoped owned-label reads.

    Returns an error message if unscoped, None if OK or if OWNED labels aren't used.
    """
    # Skip if no OWNED labels present.
    if not _OWNED_LABEL_RE.search(cypher):
        return None

    # Check if there's a noqa escape hatch in the same line or the line before.
    check_lines = []
    if line > 1 and line - 2 < len(source_lines):
        check_lines.append(source_lines[line - 2])  # Line before (line numbers are 1-indexed)
    if line <= len(source_lines):
        check_lines.append(source_lines[line - 1])

    if any(_NOQA_RE.search(check_line) for check_line in check_lines):
        return None  # Escaped by noqa

    # Check if a scope clause is present.
    if not _SCOPE_CLAUSE_RE.search(cypher):
        found_labels = sorted(set(re.findall(r":\s*(\w+)\b", cypher)))
        found_labels = [label for label in found_labels if label in OWNED_LABELS]
        labels_str = ", ".join(found_labels) if found_labels else "owned label"
        return (
            f"{filename}:{line}: unscoped read on owned label ({labels_str}) — "
            "add WHERE clause with owner_id = $viewer_id or owner_id IN $granted_ids, "
            "or use # noqa: owned-read <reason> if this is a legitimate non-viewer context"
        )

    return None


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

    for cypher, lineno in find_cypher_strings(tree):
        error = check_cypher_string(cypher, lineno, str(filepath), source_lines)
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
