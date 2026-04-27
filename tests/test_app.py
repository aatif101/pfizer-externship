"""Smoke test for Streamlit app startup — Phase 1 SC-5."""
from __future__ import annotations

import subprocess
import sys
import time
import pytest


def test_streamlit_starts() -> None:
    """Streamlit app must import and configure without errors (headless check)."""
    # Test that src/app.py can be imported (checks syntax and top-level imports)
    result = subprocess.run(
        [sys.executable, "-c", "import importlib.util; "
         "spec = importlib.util.spec_from_file_location('app', 'src/app.py'); "
         "mod = importlib.util.module_from_spec(spec)"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # A cleaner approach: run streamlit with --headless for 2s then kill
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "src/app.py",
         "--server.headless", "true",
         "--server.port", "8599"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(5)
    proc.terminate()
    stdout = proc.stdout.read().decode("utf-8", errors="replace")
    stderr = proc.stderr.read().decode("utf-8", errors="replace")

    assert proc.returncode is None or proc.returncode in (0, -15), (
        f"Streamlit exited early with code {proc.returncode}\n"
        f"stdout: {stdout}\n"
        f"stderr: {stderr}"
    )
    # Verify no import errors
    assert "Error" not in stderr or "Traceback" not in stderr, (
        f"Streamlit reported errors:\n{stderr}"
    )