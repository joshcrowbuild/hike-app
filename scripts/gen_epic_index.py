#!/usr/bin/env python3
"""Sync the epic-index Status column from each epic file's header.

`docs/epics/README.md` is the human-curated index — its description, phase, and
depends columns are authored there. This script keeps its **Status** column in
sync with the canonical source (each `epic-NNN-*.md` file's `**Status:**`
header), killing the #1 doc-drift source: epic status duplicated in four places.

  python scripts/gen_epic_index.py           # rewrite the table's Status cells
  python scripts/gen_epic_index.py --check    # exit 1 if any Status cell is stale
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EPICS_DIR = ROOT / "docs" / "epics"
INDEX = EPICS_DIR / "README.md"

# Canonical status tokens, longest-first so "DONE ✅" wins over a bare "DONE".
STATUS_TOKENS = ["DONE ✅", "BLOCKED 🚫", "IN_PROGRESS", "DEFINED", "REVIEW", "BACKLOG"]

ROW_RE = re.compile(r"^\| \[(\d{3})\]\(([^)]+)\) \|")
STATUS_HDR_RE = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$", re.MULTILINE)


def epic_status(epic_file: Path) -> str | None:
    match = STATUS_HDR_RE.search(epic_file.read_text(encoding="utf-8"))
    if match is None:
        return None
    rest = match.group(1)
    for token in STATUS_TOKENS:
        if rest.startswith(token):
            return token
    return None


def rebuild(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        row = ROW_RE.match(line)
        if row is None:
            out.append(line)
            continue
        epic_file = EPICS_DIR / row.group(2)
        status = epic_status(epic_file) if epic_file.exists() else None
        if status is None:
            out.append(line)
            continue
        # cells: ['', ' [NNN](..) ', ' desc ', ' STATUS ', ' phase ', ' depends ', '\n']
        cells = line.split("|")
        cells[3] = f" {status} "
        out.append("|".join(cells))
    return "".join(out)


def main() -> int:
    current = INDEX.read_text(encoding="utf-8")
    rebuilt = rebuild(current)
    if "--check" in sys.argv[1:]:
        if rebuilt != current:
            sys.stderr.write(
                "epic index out of sync: docs/epics/README.md Status cells do not match "
                "the epic files' **Status:** headers. Run `python scripts/gen_epic_index.py`.\n"
            )
            return 1
        return 0
    INDEX.write_text(rebuilt, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
