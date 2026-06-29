from __future__ import annotations

import sqlite3

from src.db.schema import init_db
from src.retrieval.indexer import build_retrieval_index, load_indexable_pages
from src.retrieval.ocr_backfill import backfill_low_text_pages
from src.retrieval.retriever import retrieve_evidence


def _seed_doc(db_path: str) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute(
            "INSERT INTO documents (doc_id, filename, file_path, page_count, status) VALUES (?, ?, ?, ?, ?)",
            ("doc-ocr", "ocr.pdf", "C:/tmp/ocr.pdf", 2, "ingested"),
        )
        conn.execute(
            "INSERT INTO pages (doc_id, page_num, page_text, image_blob) VALUES (?, ?, ?, ?)",
            ("doc-ocr", 0, "", b"page-zero-image"),
        )
        conn.execute(
            "INSERT INTO pages (doc_id, page_num, page_text, image_blob) VALUES (?, ?, ?, ?)",
            ("doc-ocr", 1, "Original supplier declaration text", b"page-one-image"),
        )
        conn.commit()
    finally:
        conn.close()


def test_ocr_backfill_persists_distinct_text_and_indexes_it(tmp_path) -> None:
    db_path = str(tmp_path / "ocr.sqlite")
    _seed_doc(db_path)

    def fake_extractor(pdf_path: str, page_nums: frozenset[int]) -> dict[int, str]:
        assert pdf_path == "C:/tmp/ocr.pdf"
        assert page_nums == frozenset({0})
        return {0: "Cytiva Certificate of Quality AKTA ready Gradient Flow Section 20230126"}

    result = backfill_low_text_pages(db_path, extractor=fake_extractor)
    assert result.candidate_count == 1
    assert result.written_count == 1

    conn = sqlite3.connect(db_path)
    try:
        original_text = conn.execute(
            "SELECT page_text FROM pages WHERE doc_id = ? AND page_num = ?",
            ("doc-ocr", 0),
        ).fetchone()[0]
        ocr_row = conn.execute(
            """
            SELECT source, generated_text, text_sha256, page_image_sha256
            FROM page_ocr_texts
            WHERE doc_id = ? AND page_num = ?
            """,
            ("doc-ocr", 0),
        ).fetchone()
    finally:
        conn.close()

    assert original_text == ""
    assert ocr_row[0] == "docling_forced_ocr"
    assert "Cytiva Certificate" in ocr_row[1]
    assert len(ocr_row[2]) == 64
    assert len(ocr_row[3]) == 64

    pages = load_indexable_pages(db_path)
    by_key = {(page.doc_id, page.page_num): page for page in pages}
    assert by_key[("doc-ocr", 0)].text_source == "ocr"
    assert by_key[("doc-ocr", 0)].has_ocr_text is True
    assert "Cytiva Certificate" in by_key[("doc-ocr", 0)].normalized_text

    build_retrieval_index(db_path)
    retrieval = retrieve_evidence(db_path, "Cytiva AKTA 20230126", top_k=5)
    assert retrieval.is_strong
    top = retrieval.hits[0]
    assert (top.doc_id, top.page_num) == ("doc-ocr", 0)
    assert top.text_source == "ocr"
    assert top.has_ocr_text is True
    assert "Cytiva Certificate" in top.evidence_text
