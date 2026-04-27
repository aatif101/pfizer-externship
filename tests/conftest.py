"""Shared pytest fixtures for Phase 1 tests."""
from __future__ import annotations

import io
import os
import sqlite3
from pathlib import Path

import pytest


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