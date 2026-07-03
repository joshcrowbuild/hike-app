#!/usr/bin/env python3
"""CI doc-lint: fail the build on wrong memory, broken doc links, or a stale epic index.

Three checks over the LIVE doc surface (`docs/research/archive/` is off-surface):
  1. epic index in sync   — runs `gen_epic_index.py --check`
  2. known stale markers   — a denylist of strings that are now wrong memory
  3. broken internal links — every relative `*.md` link resolves to a real file

  python scripts/doc_lint.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "docs/research/archive/"

# (regex, why-banned). Each pattern asserted something now false; keep the reason.
DENYLIST = [
    (r"Epic 010 pending", "Epic 010 (commons fork) shipped — DONE"),
    (r"Designed, not built", "the commons fork + corpus/live seams shipped"),
    (r"no app logic yet", "the personal-intelligence app UX shipped (PR #22)"),
    (r"Phase-1 build started", "Phase-1 build is COMPLETE"),
    (r"Most modules are stubs", "modules are implemented through Phase 1"),
    (r"design complete for Phase 0", "Phase-0 AND Phase-1 builds are complete"),
    (r"vigilant-bohr-yzdcyh", "that trunk is retired; the baseline is `main`"),
]

# Excluded from the DENYLIST scan only (NOT the link check):
#   epics/epic-*.md       DONE-epic AC bodies legitimately quote the pre-remediation state
#   roadmap.md/workplan.md  PM-owned SSOT; they reference the retired trunk correctly
DENY_EXCLUDE = re.compile(
    r"(docs/epics/epic-[^/]*\.md"
    r"|docs/process/roadmap\.md"
    r"|docs/workplan\.md)$"
)

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def live_md(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "*.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [rel for rel in listed if not rel.startswith(ARCHIVE)]


def check_links(root: Path, rels: list[str]) -> list[str]:
    bad: list[str] = []
    for rel in rels:
        path = root / rel
        for num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in LINK_RE.finditer(line):
                target = match.group(1).strip()
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                rel_path = target.split("#", 1)[0].split("?", 1)[0]
                if not rel_path.endswith(".md"):
                    continue
                if not (path.parent / rel_path).resolve().exists():
                    bad.append(f"{rel}:{num} -> {target}")
    return bad


def check_denylist(root: Path, rels: list[str]) -> list[str]:
    hits: list[str] = []
    for rel in rels:
        if DENY_EXCLUDE.search(rel):
            continue
        for num, line in enumerate((root / rel).read_text(encoding="utf-8").splitlines(), 1):
            for pat, why in DENYLIST:
                if re.search(pat, line):
                    hits.append(f"{rel}:{num} [{pat}] — {why}")
    return hits


def main() -> int:
    rels = live_md(ROOT)
    failed = False

    index_check = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_epic_index.py"), "--check"]
    )
    if index_check.returncode != 0:
        failed = True

    state_check = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_state.py"), "--check"]
    )
    if state_check.returncode != 0:
        failed = True

    deny = check_denylist(ROOT, rels)
    if deny:
        failed = True
        sys.stderr.write("Stale wrong-memory markers (denylist):\n")
        for hit in deny:
            sys.stderr.write(f"  {hit}\n")

    links = check_links(ROOT, rels)
    if links:
        failed = True
        sys.stderr.write("Broken internal *.md links:\n")
        for bad in links:
            sys.stderr.write(f"  {bad}\n")

    if not failed:
        sys.stdout.write(f"doc-lint: OK ({len(rels)} live docs)\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
