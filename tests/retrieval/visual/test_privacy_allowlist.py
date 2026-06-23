"""Privacy proof: retrieve_evidence trace metadata never leaks bytes/page text.

Mirrors tests/test_retrieval_eval_runner.py: monkeypatch-capture the
``safe_update_current_trace`` calls during a retrieve_evidence run, filter them
through the same allowlist the production code passes, then assert captured keys
⊆ _RETRIEVAL_TRACE_ALLOWED_KEYS and that no forbidden fragment (image bytes,
page text, snippet, secret, PNG magic) appears in any serialized value.
(T-05-11)
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from src.db.schema import init_db
from src.retrieval import retriever
from src.retrieval.indexer import build_retrieval_index
from src.retrieval.retriever import _RETRIEVAL_TRACE_ALLOWED_KEYS, retrieve_evidence
from src.tracing import filter_trace_metadata


def _seed_text_corpus(db_path: str) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute(
            "INSERT INTO documents (doc_id, filename, file_path, page_count, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("d1", "doc1.pdf", "/tmp/doc1.pdf", 1, "ingested"),
        )
        conn.execute(
            "INSERT INTO pages (doc_id, page_num, page_text) VALUES (?, ?, ?)",
            ("d1", 0, "alpha beta gamma secret-token sk-test page text body"),
        )
        conn.commit()
    finally:
        conn.close()
    build_retrieval_index(db_path)


def _capture_safe_trace_updates(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []

    def fake_safe_update_current_trace(**kwargs: Any) -> bool:
        updates.append(
            filter_trace_metadata(
                kwargs.get("metadata"),
                kwargs.get("allowed_metadata_keys") or frozenset(),
            )
        )
        return True

    monkeypatch.setattr(retriever, "safe_update_current_trace", fake_safe_update_current_trace)
    return updates


_FORBIDDEN_FRAGMENTS = (
    "image_blob",
    "page_text",
    "snippet",
    "secret",
    "sk-test",
    "alpha beta",
    "page text body",
    "\\x89png",  # PNG magic, repr-escaped
)


def _assert_metadata_safe(metadata: dict[str, Any]) -> None:
    assert set(metadata).issubset(_RETRIEVAL_TRACE_ALLOWED_KEYS)
    blob = repr(metadata).lower()
    for fragment in _FORBIDDEN_FRAGMENTS:
        assert fragment not in blob


def test_text_only_trace_metadata_is_allowlisted(tmp_path, monkeypatch):
    db_path = str(tmp_path / "trace.sqlite")
    _seed_text_corpus(db_path)
    updates = _capture_safe_trace_updates(monkeypatch)

    retrieve_evidence(db_path, "alpha", retrieval_mode="text-only")

    assert updates
    for metadata in updates:
        _assert_metadata_safe(metadata)


def test_visual_fused_trace_metadata_is_allowlisted(tmp_path, monkeypatch):
    db_path = str(tmp_path / "trace.sqlite")
    _seed_text_corpus(db_path)
    updates = _capture_safe_trace_updates(monkeypatch)

    def fake_visual_query(_db_path, _question, *, top_k):  # noqa: ANN001
        return [("d1", 0)]

    retrieve_evidence(
        db_path,
        "alpha",
        retrieval_mode="visual-fused",
        visual_query_fn=fake_visual_query,
    )

    assert updates
    for metadata in updates:
        _assert_metadata_safe(metadata)
        # The visual-tier numeric keys are allowlisted and identifier-only.
        if "visual_hit_count" in metadata:
            assert isinstance(metadata["visual_hit_count"], int)


def test_allowlist_excludes_image_and_text_keys():
    # Hard guarantee: no image-byte / page-text key was ever added.
    assert "image_blob" not in _RETRIEVAL_TRACE_ALLOWED_KEYS
    assert "page_text" not in _RETRIEVAL_TRACE_ALLOWED_KEYS
    assert "snippet" not in _RETRIEVAL_TRACE_ALLOWED_KEYS
    assert "evidence_text" not in _RETRIEVAL_TRACE_ALLOWED_KEYS
