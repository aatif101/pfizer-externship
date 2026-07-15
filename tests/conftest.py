"""Shared pytest fixtures and release-safety hooks."""
from __future__ import annotations

import io
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest


_NO_SKIPS_ENV = "PHASE3_NO_SKIPS"
_EXCLUDED_RELEASE_MARKERS = frozenset({"live", "model", "gpu"})
_required_node_ids: set[str] = set()
_required_outcomes: list[tuple[str, str, str]] = []


def _is_required_phase3_item(item: pytest.Item) -> bool:
    """Return whether a collected item belongs to the required offline gate."""

    marker_names = {marker.name for marker in item.iter_markers()}
    return not bool(marker_names & _EXCLUDED_RELEASE_MARKERS)


def _report_reason(report: pytest.TestReport) -> str:
    if report.skipped and isinstance(report.longrepr, tuple) and len(report.longrepr) >= 3:
        return str(report.longrepr[2])
    reason = getattr(report, "wasxfail", None)
    if reason:
        return str(reason)
    return str(report.longrepr or "reason not reported")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Reset process-local enforcement state for repeat in-process sessions."""

    del session
    _required_node_ids.clear()
    _required_outcomes.clear()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Remember collected offline-required nodes when strict mode is enabled."""

    del config
    if os.getenv(_NO_SKIPS_ENV) != "1":
        return
    _required_node_ids.update(item.nodeid for item in items if _is_required_phase3_item(item))


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Capture skips and non-strict xpasses for exact end-of-session reporting."""

    if os.getenv(_NO_SKIPS_ENV) != "1" or report.nodeid not in _required_node_ids:
        return
    if report.skipped:
        outcome = "SKIP"
    elif report.passed and getattr(report, "wasxfail", None):
        outcome = "XPASS"
    else:
        return
    record = (report.nodeid, outcome, _report_reason(report))
    if record not in _required_outcomes:
        _required_outcomes.append(record)


def pytest_terminal_summary(
    terminalreporter: Any,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Print every forbidden outcome with its exact node ID and reason."""

    del exitstatus, config
    if not _required_outcomes:
        return
    terminalreporter.write_sep("=", f"{_NO_SKIPS_ENV} violations")
    for node_id, outcome, reason in _required_outcomes:
        terminalreporter.write_line(f"{node_id} [{outcome}] {reason}")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Turn any required skip or xpass into a failing release session."""

    del exitstatus
    if os.getenv(_NO_SKIPS_ENV) == "1" and _required_outcomes:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Return a path to a fresh temporary SQLite database file."""
    return str(tmp_path / "test_compliance.db")


@pytest.fixture
def sample_pdf_path() -> str:
    """Return the absolute path to the 1-page sample PDF in tests/fixtures/."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample.pdf"
    assert fixture_path.exists(), f"Sample PDF not found at {fixture_path}. Run plan 01 to create it."
    return str(fixture_path)
