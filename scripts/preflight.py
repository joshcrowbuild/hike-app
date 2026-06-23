#!/usr/bin/env python3
"""Pre-flight environment check — run before starting the sprint.

Validates that all required services and credentials are in place before
the autonomous pipeline run. Exits 0 if OK, 1 if any critical check fails.

Usage: python scripts/preflight.py [--strict]
  --strict: also require optional API keys (AirNow, FIRMS, RIDB)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Load .env if present (before any os.environ checks)
_env_path = Path(".env")
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            # Strip surrounding quotes that editors/shells sometimes add
            v = v.strip().strip('"').strip("'")

RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET}  {msg}")


def check_env(
    key: str, description: str, *, required: bool = True, not_value: str | None = None
) -> bool:
    val = os.environ.get(key, "").strip()
    if not val or (not_value and val == not_value):
        if required:
            fail(f"{key} not set — {description}")
            return False
        else:
            warn(f"{key} not set (optional) — {description}")
            return True  # optional missing is not a failure
    ok(f"{key} = {'*' * min(len(val), 8)}  (set, {len(val)} chars)")
    return True


def check_neo4j() -> bool:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD", "")
    if not pw:
        fail("NEO4J_PASSWORD not set")
        return False
    try:
        import neo4j

        driver = neo4j.GraphDatabase.driver(uri, auth=(user, pw))
        driver.verify_connectivity()
        driver.close()
        ok(f"Neo4j connected at {uri}")
        return True
    except ImportError:
        fail("neo4j driver not installed — run: pip install neo4j")
        return False
    except Exception as exc:
        fail(f"Neo4j unreachable at {uri}: {exc}")
        fail("  → Start Docker Desktop, then: make db-up")
        return False


def check_anthropic() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or key == "REPLACE_ME":
        fail("ANTHROPIC_API_KEY not set or still REPLACE_ME")
        return False
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": "ping"}],
        )
        ok(f"Anthropic API OK (model: {r.model})")
        return True
    except ImportError:
        fail("anthropic SDK not installed — run: pip install anthropic")
        return False
    except Exception as exc:
        fail(f"Anthropic API failed: {exc}")
        return False


def check_nws() -> bool:
    ua = os.environ.get("NWS_USER_AGENT", "")
    if not ua:
        warn("NWS_USER_AGENT not set — weather probe will be inactive")
        return True
    try:
        import httpx

        r = httpx.get(
            "https://api.weather.gov/points/38.5519,-78.2861",
            headers={"User-Agent": ua, "Accept": "application/geo+json"},
            timeout=15,
        )
        if r.status_code == 200:
            ok("NWS API reachable")
            return True
        else:
            warn(f"NWS returned {r.status_code} — weather may not work")
            return True
    except Exception as exc:
        warn(f"NWS check failed: {exc}")
        return True  # optional


def check_docker() -> bool:
    try:
        import subprocess

        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        if result.returncode == 0:
            ok("Docker daemon running")
            return True
        else:
            fail("Docker daemon not running — start Docker Desktop")
            return False
    except FileNotFoundError:
        fail("docker not found in PATH")
        return False
    except Exception as exc:
        fail(f"Docker check failed: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Adventure Planner pre-flight check")
    parser.add_argument("--strict", action="store_true", help="Require optional API keys too")
    args = parser.parse_args()

    print("\nAdventure Planner — pre-flight check\n")
    failures: list[str] = []

    print("── Environment vars ─────────────────────────────────────────")
    for key, desc, req in [
        ("NEO4J_PASSWORD", "local Neo4j password", True),
        ("NEO4J_URI", "Neo4j bolt URI", False),
        ("ANTHROPIC_API_KEY", "Anthropic cloud yardstick", True),
        ("NWS_USER_AGENT", "weather adapter (contact string)", False),
        ("AIRNOW_API_KEY", "air quality adapter", args.strict),
        ("FIRMS_MAP_KEY", "fire adapter", args.strict),
        ("RIDB_API_KEY", "permit adapter", args.strict),
        ("ADVENTURE_REGION", "ingestion pilot region", False),
    ]:
        if not check_env(key, desc, required=req, not_value="REPLACE_ME"):
            failures.append(key)

    print("\n── Services ─────────────────────────────────────────────────")
    if not check_docker():
        failures.append("docker")
    if not check_neo4j():
        failures.append("neo4j")

    print("\n── API connectivity ─────────────────────────────────────────")
    if not check_anthropic():
        failures.append("anthropic")
    check_nws()  # advisory only

    print("\n── Python packages ──────────────────────────────────────────")
    for pkg in ["shapely", "httpx", "neo4j", "fastapi", "thefuzz"]:
        try:
            __import__(pkg.replace("-", "_"))
            ok(pkg)
        except ImportError:
            fail(f"{pkg} not installed")
            failures.append(pkg)

    print("\n── USFS data file ───────────────────────────────────────────")
    usfs_path = Path("data/usfs/trails.geojson")
    if usfs_path.exists():
        size_mb = usfs_path.stat().st_size / 1_048_576
        ok(f"data/usfs/trails.geojson present ({size_mb:.1f} MB)")
    else:
        warn("data/usfs/trails.geojson not found — USFS source will be skipped")
        warn("  Download: see ingestion/fetch/usfs.py for instructions")

    print()
    if failures:
        print(f"{RED}Pre-flight FAILED{RESET} — fix these before running the sprint:")
        for f in failures:
            print(f"  • {f}")
        sys.exit(1)
    else:
        print(
            f"{GREEN}Pre-flight PASSED{RESET} — ready to run!"
            " Resume with --dangerously-skip-permissions"
        )


if __name__ == "__main__":
    main()
