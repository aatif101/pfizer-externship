"""Versioned visual-index-run plan + persistence assertions (Task 3).

Deterministic plumbing ONLY (metric-integrity rule): ON CONFLICT idempotency
(one row on re-save), latest-run lookup, the no-raw-content guarantee (rows carry
counts/run_id/model_version/collection_name only), and ``plan_visual_run``
determinism over ALL pages incl. image-only ones (it does NOT apply the text
indexer's empty-text exclusion). No GPU, no fabricated metric.
"""
from __future__ import annotations

import pytest

from src.retrieval.visual.models import VisualIndexRun, deterministic_visual_run_id
from src.retrieval.visual.repository import (
    get_latest_visual_index_run_id,
    save_visual_index_run,
)
from src.retrieval.visual.run import build_visual_index_run, plan_visual_run

# 11-page corpus for doc 5543408c4dacc48b incl. image-only pages 0,1,2,7.
_PAGES_META = tuple(
    ("5543408c4dacc48b", page_num, "cytiva.pdf") for page_num in range(11)
) + (
    ("doc-b", 0, "vendorcert.pdf"),
    ("doc-b", 1, "vendorcert.pdf"),
)


@pytest.fixture
def tmp_db_path(tmp_path) -> str:
    return str(tmp_path / "test_compliance.db")


def _make_run(run_id: str = "visual-built-abc123", *, status: str = "built") -> VisualIndexRun:
    return VisualIndexRun(
        run_id=run_id,
        status=status,
        built_at=None,
        source_document_count=2,
        source_page_count=13,
        indexed_page_count=13,
        model_version="vidore/colqwen2.5-v0.2",
        collection_name="sdf_page_images_v1",
        content_hash="abc123def456",
    )


def test_save_then_resave_keeps_single_row(tmp_db_path: str) -> None:
    from src.db.schema import _connect, init_db

    init_db(tmp_db_path)
    run = _make_run()
    save_visual_index_run(tmp_db_path, run)
    # Re-save same run_id with updated counts -> ON CONFLICT UPDATE, still one row.
    save_visual_index_run(tmp_db_path, _make_run(status="stale"))

    conn = _connect(tmp_db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM visual_index_runs WHERE run_id = ?", (run.run_id,)
        ).fetchone()[0]
        status = conn.execute(
            "SELECT status FROM visual_index_runs WHERE run_id = ?", (run.run_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1
    assert status == "stale"  # updated, not duplicated


def test_persisted_row_carries_no_raw_content(tmp_db_path: str) -> None:
    from src.db.schema import _connect, init_db

    init_db(tmp_db_path)
    save_visual_index_run(tmp_db_path, _make_run())
    conn = _connect(tmp_db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(visual_index_runs)")}
    finally:
        conn.close()
    assert "image_blob" not in columns
    assert "page_text" not in columns
    # The columns we DO expect are present.
    assert {"run_id", "model_version", "collection_name", "source_page_count"} <= columns


def test_get_latest_visual_index_run_id(tmp_db_path: str) -> None:
    from src.db.schema import init_db

    init_db(tmp_db_path)
    assert get_latest_visual_index_run_id(tmp_db_path) is None
    save_visual_index_run(tmp_db_path, _make_run(run_id="visual-built-aaa"))
    save_visual_index_run(
        tmp_db_path,
        VisualIndexRun(
            run_id="visual-built-bbb",
            status="built",
            built_at="2099-01-01T00:00:00Z",
            source_document_count=1,
            source_page_count=1,
            indexed_page_count=1,
            model_version="vidore/colqwen2.5-v0.2",
            collection_name="sdf_page_images_v1",
        ),
    )
    assert get_latest_visual_index_run_id(tmp_db_path) == "visual-built-bbb"


def test_plan_visual_run_deterministic_and_counts_image_only_pages() -> None:
    run_a = plan_visual_run(_PAGES_META, model_version="vidore/colqwen2.5-v0.2", version=1)
    run_b = plan_visual_run(_PAGES_META, model_version="vidore/colqwen2.5-v0.2", version=1)

    # Deterministic run_id over identical corpus.
    assert run_a.run_id == run_b.run_id
    assert run_a.run_id == deterministic_visual_run_id(run_a.content_hash)
    assert run_a.run_id.startswith("visual-built-")

    # Counts cover ALL pages incl. image-only (no empty-text exclusion).
    assert run_a.source_document_count == 2
    assert run_a.source_page_count == 13
    assert run_a.indexed_page_count == 13
    assert run_a.collection_name == "sdf_page_images_v1"
    assert run_a.model_version == "vidore/colqwen2.5-v0.2"
    assert run_a.status == "built"


def test_plan_visual_run_changes_id_when_corpus_changes() -> None:
    base = plan_visual_run(_PAGES_META, model_version="m", version=1)
    extra = plan_visual_run(
        _PAGES_META + (("doc-c", 0, "new.pdf"),), model_version="m", version=1
    )
    assert base.run_id != extra.run_id
    assert extra.source_page_count == 14


def test_build_visual_index_run_plans_and_persists(tmp_db_path: str) -> None:
    from src.db.schema import init_db

    init_db(tmp_db_path)
    run = build_visual_index_run(
        tmp_db_path, _PAGES_META, model_version="vidore/colqwen2.5-v0.2", version=1
    )
    assert run.run_id.startswith("visual-built-")
    assert get_latest_visual_index_run_id(tmp_db_path) == run.run_id
