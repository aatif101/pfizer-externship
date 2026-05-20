"""Tests for the deterministic provider-free retrieval indexer."""
from __future__ import annotations

import sqlite3

from src.db.queries import insert_document, insert_page, mark_document_ingested
from src.db.schema import init_db
from src.retrieval.indexer import build_retrieval_index, get_retrieval_index_status, load_indexable_pages
from src.retrieval.models import PageIndexInput, RetrievalIndexRun, RetrievalIndexStatus
from src.retrieval.repository import list_page_index_records, load_latest_index_run, save_index_run_with_pages


def _seed_doc(
    db_path: str,
    *,
    doc_id: str = "doc-1",
    filename: str = "sdf.pdf",
    status: str = "ingested",
    pages: tuple[str | None, ...] = ("Certificate page zero", "Supplier page one"),
) -> None:
    insert_document(db_path, doc_id, filename, f"/tmp/{filename}", len(pages), docling_json=None)
    if status == "ingested":
        mark_document_ingested(db_path, doc_id)
    elif status != "pending":
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE documents SET status = ? WHERE doc_id = ?", (status, doc_id))
        conn.commit()
        conn.close()
    for page_num, text in enumerate(pages):
        insert_page(db_path, doc_id, page_num, text, image_blob=b"fake image bytes")


def test_missing_status_before_build_reports_safe_counts(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path)

    status = get_retrieval_index_status(tmp_db_path)

    assert status.status is RetrievalIndexStatus.MISSING
    assert status.run_id is None
    assert status.source_document_count == 1
    assert status.source_page_count == 2
    assert status.indexed_page_count == 0
    assert len(status.content_hash or "") == 64


def test_build_persists_built_metadata_and_safe_page_snippets(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, pages=("  Certificate\npage   zero  ", "Supplier page one"))

    result = build_retrieval_index(tmp_db_path)
    latest = load_latest_index_run(tmp_db_path)
    records = list_page_index_records(tmp_db_path, run_id=result.run.run_id)

    assert latest is not None
    assert latest.status is RetrievalIndexStatus.BUILT
    assert latest.source_document_count == 1
    assert latest.source_page_count == 2
    assert latest.indexed_page_count == 2
    assert len(latest.content_hash or "") == 64
    assert latest.run_id.startswith("retrieval-built-")
    assert records == list(result.pages)
    assert [record.page_num for record in records] == [0, 1]
    assert records[0].display_page_num == 1
    assert records[0].snippet == "Certificate page zero"
    assert all(not hasattr(record, "page_text") for record in records)


def test_empty_corpus_build_records_empty_state(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, pages=("   ", None))

    result = build_retrieval_index(tmp_db_path)
    latest = load_latest_index_run(tmp_db_path)
    status = get_retrieval_index_status(tmp_db_path)

    assert result.run.status is RetrievalIndexStatus.EMPTY
    assert result.pages == ()
    assert latest is not None
    assert latest.status is RetrievalIndexStatus.EMPTY
    assert latest.source_document_count == 0
    assert latest.source_page_count == 0
    assert latest.indexed_page_count == 0
    assert status.status is RetrievalIndexStatus.EMPTY


def test_blank_pages_and_non_ingested_documents_are_excluded(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-1", pages=("alpha", "  ", None, "omega"))
    _seed_doc(tmp_db_path, doc_id="doc-2", status="pending", pages=("pending text",))

    pages = load_indexable_pages(tmp_db_path)
    result = build_retrieval_index(tmp_db_path)

    assert [(page.doc_id, page.page_num, page.normalized_text) for page in pages] == [
        ("doc-1", 0, "alpha"),
        ("doc-1", 3, "omega"),
    ]
    assert result.run.source_document_count == 1
    assert result.run.source_page_count == 2
    assert result.run.indexed_page_count == 2


def test_status_becomes_stale_after_page_text_changes(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path)
    built = build_retrieval_index(tmp_db_path)
    insert_page(tmp_db_path, "doc-1", 1, "Supplier page one changed", image_blob=b"new image bytes")

    status = get_retrieval_index_status(tmp_db_path)

    assert status.status is RetrievalIndexStatus.STALE
    assert status.run_id == built.run.run_id
    assert status.is_stale is True
    assert status.previous_content_hash == built.run.content_hash
    assert status.content_hash != built.run.content_hash


def test_rebuild_after_stale_updates_to_built(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path)
    build_retrieval_index(tmp_db_path)
    insert_page(tmp_db_path, "doc-1", 0, "Changed certificate", image_blob=None)

    rebuilt = build_retrieval_index(tmp_db_path)
    status = get_retrieval_index_status(tmp_db_path)

    assert rebuilt.run.status is RetrievalIndexStatus.BUILT
    assert status.status is RetrievalIndexStatus.BUILT
    assert status.run_id == rebuilt.run.run_id
    assert status.is_stale is False


def test_run_id_and_page_order_are_deterministic_for_same_corpus(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-b", filename="b.pdf", pages=("b1",))
    _seed_doc(tmp_db_path, doc_id="doc-a", filename="a.pdf", pages=("a1", "a2"))

    first = build_retrieval_index(tmp_db_path)
    second = build_retrieval_index(tmp_db_path)
    records = list_page_index_records(tmp_db_path)

    assert first.run.run_id == second.run.run_id
    assert [(record.doc_id, record.page_num) for record in records] == [("doc-a", 0), ("doc-a", 1), ("doc-b", 0)]


def test_safe_diagnostics_do_not_include_raw_page_text_or_image_blobs(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    secret_text = "SECRET raw supplier text that must not appear in diagnostics " * 6
    _seed_doc(tmp_db_path, pages=(secret_text,))

    result = build_retrieval_index(tmp_db_path)
    status = get_retrieval_index_status(tmp_db_path)
    record = result.pages[0]

    assert secret_text not in repr(status)
    assert secret_text not in repr(result.run)
    assert secret_text not in repr(record)
    assert "fake image bytes" not in repr(status)
    assert len(record.snippet) == 160
    assert secret_text.startswith(record.snippet)


def test_failed_page_write_rolls_back_partial_current_index_state(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path)
    original = build_retrieval_index(tmp_db_path)
    failing_run = RetrievalIndexRun(
        run_id="retrieval-built-bad",
        status=RetrievalIndexStatus.BUILT,
        built_at=None,
        source_document_count=2,
        source_page_count=2,
        indexed_page_count=2,
        content_hash="bad",
    )

    try:
        save_index_run_with_pages(
            tmp_db_path,
            failing_run,
            [
                PageIndexInput("doc-1", 0, "sdf.pdf", "first write would succeed"),
                PageIndexInput("missing-doc", 0, "missing.pdf", "foreign key failure"),
            ],
        )
    except sqlite3.IntegrityError:
        pass
    else:  # pragma: no cover - defensive guard if SQLite behavior changes
        raise AssertionError("Expected build to fail on a missing source page foreign key")

    latest = load_latest_index_run(tmp_db_path)
    assert latest is not None
    assert latest.run_id == original.run.run_id
    assert list_page_index_records(tmp_db_path) == list(original.pages)
