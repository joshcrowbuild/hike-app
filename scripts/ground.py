#!/usr/bin/env python3
"""Grounding report — print the current state so a session starts grounded, not stale.

Answers the three questions that keep going stale: where is this worktree relative
to `origin/main`, what does the live corpus actually hold, and what work is open.
Designed to run from a Claude Code `SessionStart` hook (see
`docs/process/agent-operating-model.md`) so every terminal session opens grounded.

Everything is best-effort and time-bounded; it never blocks and always exits 0.

  python scripts/ground.py                # print the grounding block
  python scripts/ground.py --warn-stale    # also warn loudly if this worktree is stale
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = "joshcrowbuild/hike-app"
API_URL = "https://adventure-planner-api.onrender.com"

RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"


def _git(*args: str, timeout: int = 15) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _ssl_ctx() -> ssl.SSLContext | None:
    """CA-verifying context via certifi (macOS python.org builds ship no system CA
    bundle). Falls back to the default context — never to an unverified one."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _health() -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(f"{API_URL}/health", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=6, context=_ssl_ctx()) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _open_prs() -> list[dict[str, Any]] | None:
    try:
        out = subprocess.run(
            ["gh", "pr", "list", "--repo", REPO, "--state", "open", "--json", "number,title"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode != 0:
            return None
        return list(json.loads(out.stdout or "[]"))
    except Exception:
        return None


def main() -> int:
    warn_stale = "--warn-stale" in sys.argv[1:]

    _git("fetch", "origin", "--quiet", timeout=20)  # best-effort; tolerate offline
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"

    behind = ahead = 0
    counts = _git("rev-list", "--left-right", "--count", "origin/main...HEAD")
    if counts and len(counts.split()) == 2:
        behind, ahead = (int(x) for x in counts.split())
    dirty = len([ln for ln in _git("status", "--porcelain").splitlines() if ln.strip()])
    merged_branches = _git("branch", "--merged", "origin/main")
    is_merged = any(branch == b.strip().lstrip("* ").strip() for b in merged_branches.splitlines())

    print(f"{DIM}── grounding (scripts/ground.py) ──────────────────────────────{RESET}")
    print(
        f"  branch {GREEN}{branch}{RESET} · "
        f"{behind} behind / {ahead} ahead origin/main · {dirty} dirty file(s)"
    )

    health = _health()
    if health is not None:
        graph = health.get("graph") or {}
        trails = graph.get("canonical_trails", "?")
        region = health.get("region", "?")
        print(f"  corpus {GREEN}{trails}{RESET} trails · region {region} · API live")
    else:
        print(f"  corpus {YELLOW}unavailable{RESET} — API unreachable (cold start or offline)")

    prs = _open_prs()
    if prs is None:
        print(f"  open PRs {DIM}unavailable (gh absent/unauth){RESET}")
    elif prs:
        head = " · ".join(f"#{p['number']} {p['title'][:40]}" for p in prs[:4])
        more = f" · +{len(prs) - 4} more" if len(prs) > 4 else ""
        print(f"  open PRs ({len(prs)}): {head}{more}")
    else:
        print("  open PRs (0): none")

    if warn_stale and branch != "main" and (behind > 0 or is_merged):
        why = "already merged into main" if is_merged else f"{behind} commit(s) behind main"
        print(
            f"  {YELLOW}⚠ this worktree is {why}. For current/deployed state read "
            f"origin/main + the live API — NOT this working copy (rule G2).{RESET}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
