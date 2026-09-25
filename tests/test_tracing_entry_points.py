"""Entry-point trace_session tests (06-07, OBS-01).

Every offline CLI entry point (extraction, retrieval index, ingestion, eval) must
open a phase-tagged ``trace_session`` around its command body without changing
exit codes or operator output. All tests are offline: trace_session is replaced
with a recording context manager, or the real one runs with Langfuse disabled.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from typer.testing import CliRunner

from src import tracing
from src.config import get_settings
from src.db.queries import insert_document, insert_page, mark_document_ingested
from src.db.schema import init_db
from src.extraction import cli as extraction_cli
from src.pipeline import ingest as ingest_module
from src.retrieval import cli as retrieval_cli
from tests.test_extraction_cli import FakeProvider, _prepare_doc

runner = CliRunner()


class SessionRecorder:
    """Recording stand-in for ``src.tracing.trace_session``."""

    def __init__(self) -> None:
        self.sessions: list[tuple[str, tuple[str, ...]]] = []
        self.body_exceptions: list[type[BaseException]] = []

    def __call__(self, *, phase: str, session_id: str | None = None, tags=(), metadata=None):  # noqa: ANN001
        return self._session(phase=phase, tags=tuple(tags))

    @contextmanager
    def _session(self, *, phase: str, tags: tuple[str, ...]):
        self.sessions.append((phase, tags))
        try:
            yield
        except BaseException as exc:
            self.body_exceptions.append(type(exc))
            raise


@pytest.fixture
def recorder() -> SessionRecorder:
    return SessionRecorder()


def _patch_session(monkeypatch: pytest.MonkeyPatch, module: Any, recorder: SessionRecorder) -> None:
    # raising=False: before wiring, the module has no trace_session attribute and the
    # test must fail on its assertion, not on the monkeypatch.
    monkeypatch.setattr(module, "trace_session", recorder, raising=False)


def _seed_retrieval_doc(db_path: str) -> None:
    init_db(db_path)
    insert_document(db_path, "doc-1", "sdf.pdf", "/tmp/sdf.pdf", 1, docling_json=None)
    mark_document_ingested(db_path, "doc-1")
    insert_page(db_path, "doc-1", 0, "Certificate page zero", image_blob=None)


# --------------------------------------------------------------------------- extraction


def test_extract_opens_session(monkeypatch: pytest.MonkeyPatch, recorder: SessionRecorder, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-001")
    monkeypatch.setattr(extraction_cli, "build_provider", lambda provider_name: FakeProvider(calls=[]))
    _patch_session(monkeypatch, extraction_cli, recorder)

    result = runner.invoke(extraction_cli.app, ["extract", "--doc-id", "doc-001", "--db-path", tmp_db_path])

    assert result.exit_code == 0, result.output
    assert "OK doc_id=doc-001" in result.output
    assert len(recorder.sessions) == 1
    phase, tags = recorder.sessions[0]
    assert phase == get_settings().pipeline_phase
    assert "cli" in tags and "extract" in tags


def test_extract_all_opens_session(monkeypatch: pytest.MonkeyPatch, recorder: SessionRecorder, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-001")
    _prepare_doc(tmp_db_path, "doc-002")
    monkeypatch.setattr(extraction_cli, "build_provider", lambda provider_name: FakeProvider(calls=[]))
    _patch_session(monkeypatch, extraction_cli, recorder)

    result = runner.invoke(extraction_cli.app, ["extract-all", "--db-path", tmp_db_path])

    assert result.exit_code == 0, result.output
    assert "SUMMARY attempted=2 succeeded=2 failed=0" in result.output
    assert len(recorder.sessions) == 1
    phase, tags = recorder.sessions[0]
    assert phase == get_settings().pipeline_phase
    assert "cli" in tags and "extract-all" in tags


def test_extract_body_runs_under_active_phase(monkeypatch: pytest.MonkeyPatch, tmp_db_path: str) -> None:
    """With the real trace_session (Langfuse off), the body sees the active phase tag."""
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-001")
    seen_phases: list[str | None] = []

    def _build(provider_name: str) -> FakeProvider:
        seen_phases.append(tracing.current_phase())
        return FakeProvider(calls=[])

    monkeypatch.setattr(extraction_cli, "build_provider", _build)

    result = runner.invoke(extraction_cli.app, ["extract", "--doc-id", "doc-001", "--db-path", tmp_db_path])

    assert result.exit_code == 0, result.output
    assert seen_phases == [get_settings().pipeline_phase]
    assert tracing.current_phase() is None


def test_session_body_exceptions_propagate(monkeypatch: pytest.MonkeyPatch, recorder: SessionRecorder, tmp_db_path: str) -> None:
    """typer.Exit raised inside the session keeps the pre-change exit code and message."""
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-001")

    def _unsupported(provider_name: str) -> FakeProvider:
        raise extraction_cli.SafeCliError("Unsupported extraction provider 'nope'.", exit_code=2)

    monkeypatch.setattr(extraction_cli, "build_provider", _unsupported)
    _patch_session(monkeypatch, extraction_cli, recorder)

    result = runner.invoke(
        extraction_cli.app, ["extract", "--doc-id", "doc-001", "--db-path", tmp_db_path, "--provider", "nope"]
    )

    assert result.exit_code == 2
    assert "Extraction failed (reason=SafeCliError, doc_id=doc-001" in result.output
    assert len(recorder.sessions) == 1
    assert recorder.body_exceptions, "the Exit must travel through the session, not be swallowed"


# --------------------------------------------------------------------------- retrieval


def test_retrieval_build_and_status_open_session(
    monkeypatch: pytest.MonkeyPatch, recorder: SessionRecorder, tmp_db_path: str
) -> None:
    _seed_retrieval_doc(tmp_db_path)
    _patch_session(monkeypatch, retrieval_cli, recorder)

    status_before = runner.invoke(retrieval_cli.app, ["status", "--db-path", tmp_db_path])
    build = runner.invoke(retrieval_cli.app, ["build", "--db-path", tmp_db_path])

    assert status_before.exit_code == 1
    assert "status=missing" in status_before.output
    assert build.exit_code == 0, build.output
    assert "status=built" in build.output
    expected_phase = get_settings().pipeline_phase
    assert [phase for phase, _ in recorder.sessions] == [expected_phase, expected_phase]
    status_tags, build_tags = (tags for _, tags in recorder.sessions)
    assert "cli" in status_tags and "retrieval-status" in status_tags
    assert "cli" in build_tags and "retrieval-build" in build_tags


def test_retrieval_missing_db_exit_code_unchanged(
    monkeypatch: pytest.MonkeyPatch, recorder: SessionRecorder, tmp_path
) -> None:
    _patch_session(monkeypatch, retrieval_cli, recorder)

    result = runner.invoke(retrieval_cli.app, ["build", "--db-path", str(tmp_path / "missing.db")])

    assert result.exit_code == 2
    assert "reason=db_missing" in result.output
    assert len(recorder.sessions) == 1


# --------------------------------------------------------------------------- ingestion


def test_ingest_opens_session_and_no_hardcoded_phase(
    monkeypatch: pytest.MonkeyPatch, recorder: SessionRecorder, tmp_path
) -> None:
    empty_folder = tmp_path / "empty"
    empty_folder.mkdir()
    _patch_session(monkeypatch, ingest_module, recorder)

    result = runner.invoke(ingest_module.app, [str(empty_folder), "--db-path", str(tmp_path / "c.db")])

    assert result.exit_code == 1
    assert "No PDFs found" in result.output
    assert len(recorder.sessions) == 1
    phase, tags = recorder.sessions[0]
    assert phase == get_settings().pipeline_phase
    assert "cli" in tags and "ingest" in tags

    trace_calls: list[dict[str, Any]] = []

    def _record(**kwargs: Any) -> bool:
        trace_calls.append(kwargs)
        return False

    monkeypatch.setattr(ingest_module, "safe_update_current_trace", _record)
    ingest_module._trace_ingestion({"boundary": "ingestion", "status": "started"})

    assert trace_calls[0]["tags"] == ["ingestion"]


def test_storage_trace_tags_are_phase_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    """The storage boundary also takes its phase from the active session (no 'phase1')."""
    from src.pipeline import db_writer  # noqa: PLC0415

    trace_calls: list[dict[str, Any]] = []

    def _record(**kwargs: Any) -> bool:
        trace_calls.append(kwargs)
        return False

    monkeypatch.setattr(db_writer, "safe_update_current_trace", _record)
    db_writer._trace_storage({"boundary": "storage", "status": "started"})

    assert trace_calls[0]["tags"] == ["storage"]


def test_ingestion_trace_carries_session_phase_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inside a phase2 session, ingestion/storage traces carry exactly one phase tag."""
    from src.pipeline import db_writer  # noqa: PLC0415

    class _Ctx:
        def __init__(self) -> None:
            self.updates: list[dict[str, Any]] = []

        def update_current_trace(self, **kwargs: Any) -> None:
            self.updates.append(kwargs)

    ctx = _Ctx()
    monkeypatch.setattr(tracing, "_get_langfuse_context", lambda: ctx)
    with tracing.trace_session(phase="phase2", tags=("cli", "ingest")):
        ingest_module._trace_ingestion({"boundary": "ingestion", "status": "started"})
        db_writer._trace_storage({"boundary": "storage", "status": "started"})

    assert [update["tags"] for update in ctx.updates] == [["phase2", "ingestion"], ["phase2", "storage"]]
