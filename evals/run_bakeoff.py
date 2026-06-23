"""Provider bake-off runner — truthfulness eval across model configurations.

Compares Haiku (mechanical) + Sonnet (judge) vs Sonnet-only across the
truthfulness criteria in evals/truthfulness.py. Reports pass rates and
approximate token cost. Requires a live Neo4j with pilot data and Anthropic API.

Usage: python -m evals.run_bakeoff [--n-runs N] [--region shenandoah-gwj]
       make eval
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from evals.truthfulness import EvalReport, Scenario, evaluate
from graph.client import GraphClient
from orchestration.config import Settings
from orchestration.engine import PlannedTrail, plan_from_origin
from orchestration.providers.anthropic_claude import AnthropicProvider

# Old Rag trailhead — a representative point in the pilot region
_PILOT_LAT = 38.5707
_PILOT_LON = -78.2861
_PILOT_VIEWER = "eval-runner"


@dataclass(frozen=True)
class BakeoffConfig:
    name: str
    mechanical_model: str
    judge_model: str
    tier: str  # display label


CONFIGS = [
    BakeoffConfig(
        "haiku-mechanical + sonnet-judge", "claude-haiku-4-5-20251001", "claude-sonnet-4-6", "mixed"
    ),
    BakeoffConfig("sonnet-only", "claude-sonnet-4-6", "claude-sonnet-4-6", "premium"),
    BakeoffConfig("haiku-only", "claude-haiku-4-5-20251001", "claude-haiku-4-5-20251001", "budget"),
]


def _make_scenario(settings: Settings, gc: GraphClient, config: BakeoffConfig) -> Scenario:
    """Build a Scenario that runs the full pipeline for a bakeoff config."""

    def run() -> list[PlannedTrail]:
        mechanical_provider = AnthropicProvider(settings.anthropic_api_key)
        judge_provider = AnthropicProvider(settings.anthropic_api_key)

        session = gc.scoped_session(_PILOT_VIEWER)
        probes = {}  # no live probes in eval (deterministic; add when you want live test)

        # Inject probe-free runtime for deterministic eval
        from orchestration.engine import Runtime

        runtime = Runtime(
            session=session,
            probes=probes,
            mechanical=(mechanical_provider, config.mechanical_model),
            judge=(judge_provider, config.judge_model),
        )
        from orchestration.engine import rank_plan

        planned = plan_from_origin(_PILOT_LAT, _PILOT_LON, session, probes)
        if runtime.judge:
            planned = rank_plan(planned, runtime.judge[0], runtime.judge[1])
        return planned

    return Scenario(name=config.name, run=run)


def _format_report(report: EvalReport, elapsed_s: float) -> str:
    lines = [f"\n  Config: {report.scenario}"]
    for c in report.criteria:
        bar = "█" * int(c.rate * 10) + "░" * (10 - int(c.rate * 10))
        lines.append(f"    {c.name:30s} {bar}  {c.passes}/{c.runs}  ({c.rate:.0%})")
    lines.append(f"    elapsed: {elapsed_s:.1f}s")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Adventure Planner provider bake-off")
    parser.add_argument("--n-runs", type=int, default=5, help="Eval runs per config (default: 5)")
    parser.add_argument("--region", default="shenandoah-gwj")
    parser.add_argument("--config", choices=[c.name for c in CONFIGS], help="Run one config only")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not set — cannot run bake-off")
        raise SystemExit(1)

    gc = GraphClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)

    try:
        print(f"\n{'=' * 60}")
        print(f"Adventure Planner — provider bake-off ({args.n_runs} runs each)")
        print(f"Pilot point: {_PILOT_LAT}, {_PILOT_LON}")
        print(f"{'=' * 60}")

        reports: list[tuple[BakeoffConfig, EvalReport, float]] = []
        configs = [c for c in CONFIGS if args.config is None or c.name == args.config]

        for config in configs:
            print(f"\nRunning: {config.name} …")
            scenario = _make_scenario(settings, gc, config)
            t0 = time.monotonic()
            report = evaluate(scenario, n=args.n_runs)
            elapsed = time.monotonic() - t0
            reports.append((config, report, elapsed))
            print(_format_report(report, elapsed))

        print(f"\n{'=' * 60}")
        print("Summary (pass rate across all criteria):")
        for config, report, elapsed in reports:
            avg = (
                sum(c.rate for c in report.criteria) / len(report.criteria)
                if report.criteria
                else 0
            )
            status = "✓ PASS" if report.passed() else "✗ FAIL"
            print(f"  {status}  {config.name:40s}  avg={avg:.0%}  {elapsed:.1f}s")
        print()

    finally:
        gc.close()


if __name__ == "__main__":
    main()
