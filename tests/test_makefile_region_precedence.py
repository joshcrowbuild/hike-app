"""Guard test for the Makefile's ADVENTURE_REGION resolution order.

Regression for a confirmed-empirically bug: `ADVENTURE_REGION=<region> make
fetch-dem` / `make ingest` silently ran shenandoah-gwj instead of the requested
region, because the recipes sourced `.env` (which pins ADVENTURE_REGION) *after*
the shell inherited the caller's override, clobbering it. A silent wrong-region
ingest against prod is dangerous — it can prune the wrong region's corpus.

This test runs the *real* Makefile (via `make`, hermetically — PYTHON is stubbed
to a no-op echo script so nothing touches the network or a DB) and asserts the
resolved region for both invocation forms (`VAR=x make target` and
`make target VAR=x`), plus that a plain invocation still defaults from `.env`
(or the hardcoded fallback when no `.env` is present, as in CI).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_MAKEFILE = _REPO / "Makefile"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")

# Every ADVENTURE_REGION-parameterized target, per the Makefile.
_REGION_TARGETS = ["fetch-dem", "ingest", "ingest-dry"]

_STUB_PYTHON = """#!/bin/sh
# Stub interpreter: echoes its args instead of running ingestion/DEM fetch code,
# so this test never touches the network or a real DB.
echo "STUB_PYTHON_CALLED: $@"
"""


def _run_make(
    tmp_path: Path,
    target: str,
    *,
    env_extra: dict[str, str] | None = None,
    make_args: list[str] | None = None,
    write_dotenv: bool,
) -> str:
    """Run `make <target>` against the real Makefile in an isolated tmp cwd.

    PYTHON is stubbed so recipes never invoke real ingestion/fetch_dem code.
    """
    stub = tmp_path / "python_stub.sh"
    stub.write_text(_STUB_PYTHON)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    if write_dotenv:
        (tmp_path / ".env").write_text("ADVENTURE_REGION=shenandoah-gwj\nOTHER_VAR=x\n")

    env = dict(os.environ)
    env.pop("ADVENTURE_REGION", None)
    if env_extra:
        env.update(env_extra)

    args = ["make", "-f", str(_MAKEFILE), target, f"PYTHON={stub}"]
    if make_args:
        args.extend(make_args)

    result = subprocess.run(
        args,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"make {target} failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


@pytest.mark.parametrize("target", _REGION_TARGETS)
def test_env_var_form_takes_precedence_over_dotenv(tmp_path: Path, target: str) -> None:
    """`ADVENTURE_REGION=x make <target>` must win over .env's pinned region."""
    out = _run_make(tmp_path, target, env_extra={"ADVENTURE_REGION": "richmond"}, write_dotenv=True)
    assert ">> ADVENTURE_REGION resolved to: richmond" in out
    assert "--region richmond" in out
    assert "shenandoah-gwj" not in out


@pytest.mark.parametrize("target", _REGION_TARGETS)
def test_make_cli_var_form_takes_precedence_over_dotenv(tmp_path: Path, target: str) -> None:
    """`make <target> ADVENTURE_REGION=x` must win over .env's pinned region."""
    out = _run_make(tmp_path, target, make_args=["ADVENTURE_REGION=outer-banks"], write_dotenv=True)
    assert ">> ADVENTURE_REGION resolved to: outer-banks" in out
    assert "--region outer-banks" in out
    assert "shenandoah-gwj" not in out


@pytest.mark.parametrize("target", _REGION_TARGETS)
def test_plain_invocation_falls_back_to_dotenv(tmp_path: Path, target: str) -> None:
    """With no override, .env's ADVENTURE_REGION is still honored (local-dev default)."""
    out = _run_make(tmp_path, target, write_dotenv=True)
    assert ">> ADVENTURE_REGION resolved to: shenandoah-gwj" in out


@pytest.mark.parametrize("target", _REGION_TARGETS)
def test_plain_invocation_with_no_dotenv_uses_hardcoded_default(
    tmp_path: Path, target: str
) -> None:
    """No .env at all (e.g. CI) must not error — falls back to shenandoah-gwj."""
    out = _run_make(tmp_path, target, write_dotenv=False)
    assert ">> ADVENTURE_REGION resolved to: shenandoah-gwj" in out


@pytest.mark.parametrize("target", _REGION_TARGETS)
def test_override_wins_even_with_no_dotenv(tmp_path: Path, target: str) -> None:
    """An explicit override must still work when there is no .env to fall back to."""
    out = _run_make(
        tmp_path, target, env_extra={"ADVENTURE_REGION": "sky-meadows"}, write_dotenv=False
    )
    assert ">> ADVENTURE_REGION resolved to: sky-meadows" in out
