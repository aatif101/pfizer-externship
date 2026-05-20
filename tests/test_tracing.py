"""Tests for src/tracing.py — Langfuse v3 wiring."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

import langfuse  # noqa: PLC0415
from importlib.metadata import version
import pytest
from src.tracing import verify_langfuse_connection  # noqa: PLC0415


def test_langfuse_v3_pinned() -> None:
    """Langfuse must be pinned to v3 (langfuse version starts with '3.')."""
    langfuse_version = version('langfuse')
    assert langfuse_version.startswith("3."), (
        f"langfuse version {langfuse_version!r} is not v3. "
        "Upgrade to v4 is prohibited — pin langfuse>=3.0,<4.0."
    )


def test_langfuse_import_paths() -> None:
    """v3 import paths must be resolvable."""
    from langfuse import observe, get_client  # noqa: PLC0415,F401

    assert callable(observe), "langfuse.observe must be callable"
    assert get_client is not None, "get_client must be importable"


def test_tracing_module_imports() -> None:
    """src/tracing.py must be importable without error."""
    import src.tracing  # noqa: PLC0415,F401


def test_verify_langfuse_connection_callable() -> None:
    """verify_langfuse_connection() must be exported and callable."""
    assert callable(verify_langfuse_connection)
    # Result may be True or False depending on env — we only check it doesn't raise
    result = verify_langfuse_connection()
    assert isinstance(result, bool)


_FORBIDDEN_TRACE_KEYS = {
    "question",
    "snippet",
    "page_text",
    "api_key",
    "secret",
    "image_blob",
    "docling_json",
    "content_hash",
}


@dataclass
class _FakeLangfuseContext:
    updates: list[dict[str, Any]] = field(default_factory=list)
    raise_on_update: bool = False

    def update_current_trace(self, **kwargs: Any) -> None:
        if self.raise_on_update:
            raise RuntimeError("trace backend unavailable")
        self.updates.append(kwargs)


@dataclass
class _TraceTestProvider:
    provider_name: str = "trace-test-provider"
    trace_id: str | None = "trace-safe-001"

    def answer(self, request: Any) -> Any:
        from src.rag.providers import AnswerProviderResult

        return AnswerProviderResult(
            answer_text="Acme has supplier compliance approval evidence on the cited page.",
            trace_id=self.trace_id,
            provider_name=self.provider_name,
        )


def _seed_trace_doc(db_path: str, *, text: str | None = None) -> None:
    from src.db.queries import insert_document, insert_page, mark_document_ingested
    from src.db.schema import init_db

    init_db(db_path)
    insert_document(db_path, "doc-trace", "trace-sdf.pdf", "/tmp/trace-sdf.pdf", 1, docling_json=None)
    mark_document_ingested(db_path, "doc-trace")
    insert_page(
        db_path,
        "doc-trace",
        0,
        text or "Acme supplier compliance approval evidence is present for Pfizer review.",
        image_blob=b"image bytes must never enter trace metadata",
    )


def _metadata_updates(fake_context: _FakeLangfuseContext) -> list[dict[str, Any]]:
    return [update.get("metadata", {}) for update in fake_context.updates]


def _assert_trace_metadata_is_bounded(metadata: dict[str, Any]) -> None:
    assert metadata, "expected trace metadata update"
    assert _FORBIDDEN_TRACE_KEYS.isdisjoint(metadata)
    metadata_repr = repr(metadata).lower()
    for forbidden in _FORBIDDEN_TRACE_KEYS:
        assert forbidden not in metadata_repr
    assert "acme supplier compliance approval" not in metadata_repr
    assert "image bytes" not in metadata_repr


def test_retrieval_and_answer_trace_metadata_use_only_whitelisted_bounded_fields(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.rag import service
    from src.retrieval import indexer, retriever

    _seed_trace_doc(tmp_db_path)
    fake_context = _FakeLangfuseContext()
    for module in (indexer, retriever, service):
        monkeypatch.setattr(module, "_LANGFUSE_AVAILABLE", True)
        monkeypatch.setattr(module, "langfuse_context", fake_context)

    built = indexer.build_retrieval_index(tmp_db_path)
    evidence = retriever.retrieve_evidence(tmp_db_path, "Acme supplier compliance approval", top_k=1)
    answer = service.answer_question(tmp_db_path, "Acme supplier compliance approval", provider=_TraceTestProvider(), top_k=1)

    assert built.run.indexed_page_count == 1
    assert evidence.is_strong is True
    assert answer.is_answered is True
    metadata_updates = _metadata_updates(fake_context)
    assert len(metadata_updates) >= 3
    for metadata in metadata_updates:
        _assert_trace_metadata_is_bounded(metadata)
    assert any(metadata.get("index_status") == "built" for metadata in metadata_updates)
    assert any(metadata.get("evidence_reason") == "strong_evidence" for metadata in metadata_updates)
    assert any(metadata.get("answer_status") == "answered" for metadata in metadata_updates)
    assert any(metadata.get("trace_id") == "trace-safe-001" for metadata in metadata_updates)


def test_trace_context_update_failures_do_not_change_offline_behavior(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.rag import service
    from src.retrieval import indexer, retriever

    _seed_trace_doc(tmp_db_path)
    failing_context = _FakeLangfuseContext(raise_on_update=True)
    for module in (indexer, retriever, service):
        monkeypatch.setattr(module, "_LANGFUSE_AVAILABLE", True)
        monkeypatch.setattr(module, "langfuse_context", failing_context)

    built = indexer.build_retrieval_index(tmp_db_path)
    evidence = retriever.retrieve_evidence(tmp_db_path, "Acme supplier compliance approval", top_k=1)
    answer = service.answer_question(tmp_db_path, "Acme supplier compliance approval", provider=_TraceTestProvider(), top_k=1)

    assert built.run.indexed_page_count == 1
    assert evidence.is_strong is True
    assert answer.is_answered is True
    assert failing_context.updates == []


def test_langfuse_absence_is_noop_for_index_retrieval_and_answer(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.rag import service
    from src.retrieval import indexer, retriever

    _seed_trace_doc(tmp_db_path)
    for module in (indexer, retriever, service):
        monkeypatch.setattr(module, "_LANGFUSE_AVAILABLE", False)
        monkeypatch.setattr(module, "langfuse_context", None)

    built = indexer.build_retrieval_index(tmp_db_path)
    evidence = retriever.retrieve_evidence(tmp_db_path, "Acme supplier compliance approval", top_k=1)
    answer = service.answer_question(tmp_db_path, "Acme supplier compliance approval", provider=_TraceTestProvider(), top_k=1)

    assert built.run.indexed_page_count == 1
    assert evidence.is_strong is True
    assert answer.is_answered is True


def test_provider_exception_trace_metadata_is_safe_and_bounded(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.rag import service
    from src.retrieval.indexer import build_retrieval_index

    class ExplodingProvider(_TraceTestProvider):
        def answer(self, request: Any) -> Any:
            raise RuntimeError("SECRET_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR")

    _seed_trace_doc(tmp_db_path)
    build_retrieval_index(tmp_db_path)
    fake_context = _FakeLangfuseContext()
    monkeypatch.setattr(service, "_LANGFUSE_AVAILABLE", True)
    monkeypatch.setattr(service, "langfuse_context", fake_context)

    result = service.answer_question(tmp_db_path, "Acme supplier compliance approval", provider=ExplodingProvider(), top_k=1)

    assert result.status.value == "provider_error"
    metadata_updates = _metadata_updates(fake_context)
    assert metadata_updates
    for metadata in metadata_updates:
        _assert_trace_metadata_is_bounded(metadata)
    assert any(metadata.get("answer_status") == "provider_error" for metadata in metadata_updates)
    assert "SECRET_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR" not in repr(metadata_updates)
