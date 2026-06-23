"""Schema + DTO + marker behaviors for the visual retrieval tier (Task 1).

These tests assert ONLY deterministic plumbing: the ``visual_index_runs`` table
shape and idempotency, the ``VisualIndexRun`` DTO privacy boundary, and the
``deterministic_visual_run_id`` helper. No embedding/score is fabricated.

The blob-decode-from-stored-blob round trip lives here too: it confirms a real
``pages.image_blob`` byte string decodes deterministically to a PIL RGB image.
"""
from __future__ import annotations

import dataclasses
import io

from PIL import Image

from src.db.schema import _connect, init_db, _table_columns
from src.retrieval.visual.models import VisualIndexRun, deterministic_visual_run_id
from src.retrieval.visual.pooling import blob_to_image

from .conftest import _insert_page_with_blob


_EXPECTED_COLUMNS = {
    "run_id",
    "status",
    "built_at",
    "source_document_count",
    "source_page_count",
    "indexed_page_count",
    "content_hash",
    "previous_content_hash",
    "model_version",
    "collection_name",
    "is_stale",
    "stale_reason",
    "error_reason",
}


def test_init_db_creates_visual_index_runs_table(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    conn = _connect(tmp_db_path)
    try:
        columns = _table_columns(conn, "visual_index_runs")
    finally:
        conn.close()
    assert _EXPECTED_COLUMNS.issubset(columns)


def test_init_db_is_idempotent(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    conn = _connect(tmp_db_path)
    try:
        first = _table_columns(conn, "visual_index_runs")
    finally:
        conn.close()

    # Second init on the SAME db path must not raise and must keep the columns.
    init_db(tmp_db_path)
    conn = _connect(tmp_db_path)
    try:
        second = _table_columns(conn, "visual_index_runs")
    finally:
        conn.close()

    assert first == second
    assert _EXPECTED_COLUMNS.issubset(second)


def test_visual_index_run_is_frozen_and_content_free() -> None:
    run = VisualIndexRun(
        run_id="visual-built-abc",
        status="built",
        built_at=None,
        source_document_count=3,
        source_page_count=11,
        indexed_page_count=11,
        model_version="vidore/colqwen2.5-v0.2",
        collection_name="sdf_page_images_v1",
    )
    # Frozen: cannot mutate.
    try:
        run.run_id = "mutated"  # type: ignore[misc]
        raised = False
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised

    field_names = {f.name for f in dataclasses.fields(VisualIndexRun)}
    # Privacy boundary: NO raw-content fields.
    assert "image_blob" not in field_names
    assert "page_text" not in field_names
    # Counts / identifiers only.
    assert {"run_id", "model_version", "collection_name", "indexed_page_count"} <= field_names


def test_deterministic_visual_run_id_is_stable() -> None:
    content_hash = "0123456789abcdef0123456789abcdef"
    first = deterministic_visual_run_id(content_hash)
    second = deterministic_visual_run_id(content_hash)
    assert first == second
    assert first == "visual-built-0123456789abcdef"


def test_blob_to_image_decodes_stored_blob_deterministically(tmp_db_path: str) -> None:
    # Build a real PNG byte string and store it as pages.image_blob.
    buffer = io.BytesIO()
    Image.new("RGB", (12, 7), color=(10, 20, 30)).save(buffer, format="PNG")
    blob = buffer.getvalue()

    _insert_page_with_blob(tmp_db_path, "doc-blob", 2, blob)

    conn = _connect(tmp_db_path)
    try:
        row = conn.execute(
            "SELECT image_blob FROM pages WHERE doc_id = ? AND page_num = ?",
            ("doc-blob", 2),
        ).fetchone()
    finally:
        conn.close()
    stored = bytes(row[0])

    image_a = blob_to_image(stored)
    image_b = blob_to_image(stored)
    assert image_a.mode == "RGB"
    assert image_a.size == (12, 7)
    assert image_a.size == image_b.size
