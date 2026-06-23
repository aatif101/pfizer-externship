"""retrieval_mode config + retrieve_evidence routing (text-only default).

Asserts the deterministic plumbing only:
- default Settings.retrieval_mode == "text-only";
- the default still returns the unchanged text-tier result on a seeded corpus;
- requesting "visual-fused" with no visual backend raises the clear RuntimeError
  (metric-integrity: no fabricated score stands in for the model).
"""

from __future__ import annotations

import sqlite3

import pytest

from src.config import Settings
from src.db.schema import init_db
from src.retrieval.indexer import build_retrieval_index
from src.retrieval.retriever import retrieve_evidence


def _seed_text_corpus(db_path: str) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute(
            "INSERT INTO documents (doc_id, filename, file_path, page_count, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("d1", "doc1.pdf", "/tmp/doc1.pdf", 2, "ingested"),
        )
        for idx, text in enumerate(["alpha beta gamma", "delta epsilon zeta"]):
            conn.execute(
                "INSERT INTO pages (doc_id, page_num, page_text) VALUES (?, ?, ?)",
                ("d1", idx, text),
            )
        conn.commit()
    finally:
        conn.close()
    build_retrieval_index(db_path)


def test_default_retrieval_mode_is_text_only():
    assert Settings().retrieval_mode == "text-only"


def test_default_mode_returns_text_tier_result(tmp_path):
    db_path = str(tmp_path / "modes.sqlite")
    _seed_text_corpus(db_path)

    result = retrieve_evidence(db_path, "alpha", retrieval_mode="text-only")

    assert result.is_strong
    assert result.hits
    top = result.hits[0]
    assert top.doc_id == "d1"
    assert top.page_num == 0
    # Text tier never tags a hit visual/fused.
    assert top.score_components.source in ("fts", "lexical")


def test_visual_fused_without_backend_raises_clear_error(tmp_path):
    db_path = str(tmp_path / "modes.sqlite")
    _seed_text_corpus(db_path)

    with pytest.raises(RuntimeError, match="visual-fused mode requires"):
        retrieve_evidence(db_path, "alpha", retrieval_mode="visual-fused")


def test_visual_fused_with_injected_ranking_fuses_into_hits(tmp_path):
    """A real (notebook-supplied) visual ranking fuses into RetrievalHits.

    This injects a ranked list of page keys (NOT a fabricated similarity score);
    fusion is RRF over RANKS, so this exercises only deterministic plumbing.
    """
    db_path = str(tmp_path / "modes.sqlite")
    _seed_text_corpus(db_path)

    # Visual tier surfaces an image-only page the text tier cannot reach (p1).
    def fake_visual_query(_db_path, _question, *, top_k):  # noqa: ANN001
        return [("d1", 1), ("d1", 0)]

    result = retrieve_evidence(
        db_path,
        "alpha",
        retrieval_mode="visual-fused",
        visual_query_fn=fake_visual_query,
    )

    assert result.is_strong
    keys = {(hit.doc_id, hit.page_num) for hit in result.hits}
    assert ("d1", 1) in keys  # image-only/visual-only page now retrievable
    sources = {hit.score_components.source for hit in result.hits}
    assert sources <= {"visual", "fused"}
    # The visual-only page carries empty grounding (no fabricated text).
    visual_only = next(hit for hit in result.hits if (hit.doc_id, hit.page_num) == ("d1", 1))
    assert visual_only.score_components.source == "visual"
    assert visual_only.evidence_text == ""
