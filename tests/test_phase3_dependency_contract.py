"""Executable contracts for the Phase 3 offline test harness.

These tests intentionally exercise pytest in child processes so the socket and
session-failure plugins are proven at their actual command-line boundary.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


pytestmark = pytest.mark.phase3_required

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
ROOT_CONFTEST = ROOT / "tests" / "conftest.py"


def _run_pytest(tmp_path: Path, source: str, *args: str, no_skips: bool = False) -> subprocess.CompletedProcess[str]:
    """Run one isolated pytest session using this repository's root hooks."""

    (tmp_path / "conftest.py").write_bytes(ROOT_CONFTEST.read_bytes())
    (tmp_path / "test_contract.py").write_text(source, encoding="utf-8")
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    if no_skips:
        env["PHASE3_NO_SKIPS"] = "1"
    else:
        env.pop("PHASE3_NO_SKIPS", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_phase3_dependencies_and_markers_are_registered() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dev = config["project"]["optional-dependencies"]["dev"]
    assert any(dep.split(";")[0].strip().lower().startswith("pytest-socket") for dep in dev)

    marker_rows = config["tool"]["pytest"]["ini_options"]["markers"]
    for marker in ("live", "model", "gpu", "phase3_required"):
        assert any(row.startswith(f"{marker}:") for row in marker_rows), marker


@pytest.mark.parametrize(
    ("source", "needle"),
    [
        (
            "import pytest\npytestmark = pytest.mark.phase3_required\n"
            "def test_required_skip(): pytest.skip('deliberate skip reason')\n",
            "test_contract.py::test_required_skip",
        ),
        (
            "import pytest\npytestmark = pytest.mark.phase3_required\n"
            "@pytest.mark.xfail(reason='deliberate xpass reason')\n"
            "def test_required_xpass(): assert True\n",
            "test_contract.py::test_required_xpass",
        ),
    ],
)
def test_no_skip_contract_fails_session_with_exact_node_id(
    tmp_path: Path,
    source: str,
    needle: str,
) -> None:
    result = _run_pytest(tmp_path, source, no_skips=True)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert needle in output
    assert "PHASE3_NO_SKIPS" in output


def test_no_skip_contract_allows_clean_required_session(tmp_path: Path) -> None:
    result = _run_pytest(
        tmp_path,
        "import pytest\npytestmark = pytest.mark.phase3_required\n"
        "def test_required_pass(): assert 2 + 2 == 4\n",
        no_skips=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_disable_socket_blocks_an_external_socket_attempt(tmp_path: Path) -> None:
    result = _run_pytest(
        tmp_path,
        "import socket\n"
        "def test_external_socket_is_denied():\n"
        "    socket.create_connection(('example.com', 443), timeout=0.01)\n",
        "--disable-socket",
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "SocketBlockedError" in output


def test_windows_wrappers_enforce_offline_required_selection() -> None:
    wrapper = (ROOT / "scripts" / "run_phase3_pytest.ps1").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify_phase3_wave0.ps1").read_text(encoding="utf-8")
    assert "PHASE3_NO_SKIPS" in wrapper
    assert "--disable-socket" in wrapper
    assert 'not live and not model and not gpu' in wrapper
    assert "run_phase3_pytest.ps1" in verifier

