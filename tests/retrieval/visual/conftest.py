"""Offline fixtures for the visual retrieval tier tests.

Mirrors ``tests/conftest.py`` ``tmp_db_path`` (tmp_path SQLite) and adds a
direct-INSERT seed helper that stores a real ``pages.image_blob`` so blob-decode
behavior can be exercised without a GPU or any heavy ML dependency.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.db.schema import _connect, init_db


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Return a path to a fresh temporary SQLite database file."""
    return str(tmp_path / "test_compliance.db")


def _insert_page_with_blob(
    db_path: str,
    doc_id: str,
    page_num: int,
    image_blob: bytes,
    *,
    filename: str = "sample.pdf",
) -> None:
    """Seed a documents + pages row carrying a real ``image_blob`` byte string.

    Parameterized SQL only; ``init_db`` is invoked first so the schema (incl. the
    new ``visual_index_runs`` table) exists.
    """
    init_db(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO documents (doc_id, filename, file_path, page_count) "
            "VALUES (?, ?, ?, ?)",
            (doc_id, filename, f"local_data/private/{filename}", page_num + 1),
        )
        conn.execute(
            "INSERT OR REPLACE INTO pages (doc_id, page_num, page_text, image_blob) "
            "VALUES (?, ?, ?, ?)",
            (doc_id, page_num, "", sqlite_blob(image_blob)),
        )
        conn.commit()
    finally:
        conn.close()


def sqlite_blob(data: bytes) -> "memoryview":
    """Wrap raw bytes for an sqlite BLOB binding."""
    return memoryview(data)
