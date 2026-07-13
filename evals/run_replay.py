"""CI entry point for the source-or-silence regression gate (Epic 009, replay half).

Walks every golden-trip scenario under `evals/scenarios/`, runs the REAL engine
against its recorded corpus + condition cassettes (hermetic: no network, no
Neo4j, no API key), and exits non-zero if ANY invariant criterion's pass rate
drops below 1.0 — a PR that breaks source-or-silence reds the build (Phase B's
"defend the claim" gate). On failure the first failing run's violations are
printed as a reproduction (AC-6.4), not just a rate.

Usage: python -m evals.run_replay [--n-runs N] [--scenario NAME]
       make eval-replay
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.replay import evaluate_scenario, list_scenario_dirs, load_scenario


def _is_skipped(path: Path) -> tuple[bool, str]:
    """Check whether a scenario is gate-skipped (adversarial findings that document
    a hole — failing on purpose, kept out of CI). Returns (skipped, reason)."""
    expected_path = path / "expected.json"
    if not expected_path.exists():
        return False, ""
    doc = json.loads(expected_path.read_text(encoding="utf-8"))
    meta = doc.get("meta", {}) if isinstance(doc, dict) else {}
    if meta.get("skip"):
        return True, str(meta.get("skip_reason", "gate-skipped adversarial finding"))
    return False, ""


def main() -> None:
    parser = argparse.ArgumentParser(description="source-or-silence replay gate")
    parser.add_argument("--n-runs", type=int, default=3, help="runs per scenario (default: 3)")
    parser.add_argument("--scenario", help="run one scenario directory by name")
    parser.add_argument(
        "--include-skipped",
        action="store_true",
        help="run gate-skipped scenarios too (for local investigation)",
    )
    args = parser.parse_args()

    dirs = list_scenario_dirs()
    if args.scenario:
        dirs = [d for d in dirs if d.name == args.scenario]
        if not dirs:
            raise SystemExit(f"no scenario named {args.scenario!r} under evals/scenarios/")
    if not dirs:
        # An empty scenario set must never read as a green gate.
        raise SystemExit("no scenarios found under evals/scenarios/ — the gate has no teeth")

    print(f"source-or-silence replay gate — {len(dirs)} scenario(s), n={args.n_runs}")
    any_failed = False
    for path in dirs:
        skipped, reason = _is_skipped(path)
        if skipped and not args.include_skipped:
            print(f"\n  [SKIP] {path.name} — {reason}")
            continue
        result = evaluate_scenario(load_scenario(path), n=args.n_runs)
        verdict = "PASS" if result.passed else "FAIL"
        print(f"\n  [{verdict}] {result.report.scenario}")
        for criterion in result.report.criteria:
            marker = "ok " if criterion.rate >= 1.0 else "RED"
            print(f"    {marker} {criterion.name:28s} {criterion.passes}/{criterion.runs}")
        if not result.passed:
            any_failed = True
            for name, violations in result.failures.items():
                for violation in violations:
                    print(f"      {name}: {violation}")
    print()
    if any_failed:
        raise SystemExit(1)
    print("all invariants held (rate 1.0) across every scenario")


if __name__ == "__main__":
    main()
