#!/usr/bin/env python3
"""Generate the cross-surface current-state snapshot: `state.json` + `STATUS.md`.

The prose roadmap keeps drifting because live numbers (corpus counts, open PRs,
deploy SHA) are hand-transcribed. This moves those facts into a *generated*
snapshot that any surface can read — the terminal via `scripts/ground.py`, the
desktop/iOS apps via the committed files (or the live `/status` endpoint). The
authored narrative + judgement stays in `docs/process/roadmap.md`.

Two responsibilities, kept apart so the CI gate can't go flaky:
  - `--refresh` hits LIVE sources (the API `/health`, `git`, `gh`) and rewrites
    `state.json`, then renders `STATUS.md` from it. Run on demand (also `make state`).
  - `--check` re-renders `STATUS.md` from the COMMITTED `state.json` and diffs —
    a deterministic, stdlib-only, network-free check that `STATUS.md` faithfully
    reflects `state.json`. Wired into `scripts/doc_lint.py` (the `docs-lint` CI gate).
    It does NOT compare against live reality — that's the hook's/endpoint's job.

  python scripts/gen_state.py --refresh   # pull live sources, rewrite both files
  python scripts/gen_state.py             # re-render STATUS.md from state.json
  python scripts/gen_state.py --check      # exit 1 if STATUS.md is out of sync
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state.json"
STATUS = ROOT / "STATUS.md"

REPO = "joshcrowbuild/hike-app"
API_URL = "https://adventure-planner-api.onrender.com"


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return out.stdout.strip()


def _ssl_ctx() -> ssl.SSLContext | None:
    """A CA-verifying context via certifi. macOS python.org builds ship no system CA
    bundle, so a bare urlopen fails CERTIFICATE_VERIFY_FAILED. Falls back to the default
    context — never to an unverified one (strict TLS preserved). certifi is imported
    lazily so the network-free `--check` path stays stdlib-only for the no-deps CI job."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _fetch_health() -> dict[str, Any] | None:
    """GET the API /health (the live corpus + region source). Best-effort."""
    try:
        req = urllib.request.Request(f"{API_URL}/health", headers={"Accept": "application/json"})
        # B310-audited: https:// API_URL constant, not user input.
        with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx()) as resp:  # nosec B310
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _open_prs() -> list[dict[str, Any]] | None:
    """List open PRs via gh. Best-effort — returns None if gh is absent/unauth."""
    try:
        out = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                REPO,
                "--state",
                "open",
                "--json",
                "number,title,headRefName",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if out.returncode != 0:
            return None
        rows = json.loads(out.stdout or "[]")
        return [
            {"number": r["number"], "title": r["title"], "branch": r["headRefName"]} for r in rows
        ]
    except Exception:
        return None


def refresh(prior: dict[str, Any]) -> dict[str, Any]:
    """Build a fresh state dict from live sources, preserving prior data on failure."""
    main_sha = _git("rev-parse", "origin/main") or prior.get("main_sha", "unknown")
    main_date = _git("show", "-s", "--format=%cI", "origin/main") or prior.get(
        "main_committed_at", "unknown"
    )

    health = _fetch_health()
    if health is not None:
        graph = health.get("graph") or {}
        corpus = {
            "canonical_trails": graph.get("canonical_trails"),
            "source_records": graph.get("source_records"),
            "trailheads": graph.get("trailheads"),
            "same_as_edges": graph.get("same_as_edges"),
            "schema_version": graph.get("schema_version"),
        }
        api = {"url": API_URL, "reachable": True, "region": health.get("region")}
    else:
        # API unreachable — keep last-known numbers rather than wipe them to null.
        corpus = prior.get("corpus", {})
        api = {**prior.get("api", {"url": API_URL}), "reachable": False}

    prs = _open_prs()
    open_prs = prs if prs is not None else prior.get("open_prs", [])

    return {
        "generated_by": "scripts/gen_state.py --refresh (do not hand-edit)",
        "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "main_sha": main_sha,
        "main_committed_at": main_date,
        "region": (api.get("region") or prior.get("region") or "shenandoah-gwj"),
        "corpus": corpus,
        "api": api,
        "open_prs": open_prs,
        "narrative": "docs/process/roadmap.md",
    }


def render(state: dict[str, Any]) -> str:
    """Render STATUS.md deterministically from the state dict (no network, no clock)."""
    sha = str(state.get("main_sha", "unknown"))
    short = sha[:9] if sha != "unknown" else sha
    corpus = state.get("corpus", {})
    api = state.get("api", {})
    prs = state.get("open_prs", [])

    trails = corpus.get("canonical_trails")
    trails_str = f"{trails} canonical trails" if trails is not None else "corpus count unavailable"
    reach = "live" if api.get("reachable") else "unreachable at last refresh"
    corpus_line = (
        f"{trails_str} · {corpus.get('trailheads', '?')} trailheads · "
        f"{corpus.get('source_records', '?')} source records · "
        f"schema `{corpus.get('schema_version', '?')}`"
    )
    as_of = (
        f"`main@{short}` ({state.get('main_committed_at', 'unknown')}) · "
        f"refreshed {state.get('refreshed_at', 'unknown')}"
    )

    if prs:
        pr_lines = "\n".join(f"- #{p['number']} {p['title']} (`{p['branch']}`)" for p in prs)
    else:
        pr_lines = "- none open"

    return f"""# Current State — Adventure Planner

*Generated by `scripts/gen_state.py --refresh` — **do not hand-edit**. Narrative,
judgement, and next-work live in [`docs/process/roadmap.md`](docs/process/roadmap.md).
For real-time state, GET `{API_URL}/status`. For how the claude fleet operates, see
[`docs/process/agent-operating-model.md`](docs/process/agent-operating-model.md).*

**As of:** {as_of}

## Live substrate
- **Corpus:** {corpus_line}
- **Region:** `{state.get("region", "?")}`
- **API:** {api.get("url", API_URL)} — {reach}

## Open PRs ({len(prs)})
{pr_lines}
"""


def main() -> int:
    args = sys.argv[1:]
    prior: dict[str, Any] = {}
    if STATE.exists():
        prior = json.loads(STATE.read_text(encoding="utf-8"))

    if "--refresh" in args:
        state = refresh(prior)
        STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        STATUS.write_text(render(state), encoding="utf-8")
        return 0

    # --check / default both render from the committed state.json.
    if not prior:
        sys.stderr.write("state.json missing — run `python scripts/gen_state.py --refresh`.\n")
        return 1
    rendered = render(prior)

    if "--check" in args:
        current = STATUS.read_text(encoding="utf-8") if STATUS.exists() else ""
        if rendered != current:
            sys.stderr.write(
                "STATUS.md out of sync with state.json. "
                "Run `python scripts/gen_state.py` (or `--refresh`).\n"
            )
            return 1
        return 0

    STATUS.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
