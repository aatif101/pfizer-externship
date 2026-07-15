"""CLI tests for offline-safe SDF extraction commands."""
from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

import pytest
from typer.testing import CliRunner

from src.db.queries import DocumentMetadata, DocumentPage, insert_document, insert_page, mark_document_ingested
from src.db.schema import init_db
from src.extraction import cli
from src.extraction.models import SDFFieldName
from src.extraction.providers import (
    ExtractionConfigurationError,
    ExtractionProviderError,
    ProviderExtractionResult,
    ProviderFieldPayload,
    ProviderSourceEvidence,
    VisualFallbackRequest,
)
from src.extraction.repository import (
    begin_or_resume_extraction_run,
    list_compliance_records,
    list_compliance_records_for_run,
    list_extraction_run_summaries,
    list_resume_candidates,
)

runner = CliRunner()

PAGE_TEXT = """
Supplier Declaration Form
Vendor Name: Acme Pharma Ltd.
Manufacturing Date: 2024-01-05
Effective Date: 2024-02-01
Revision Date: 2024-03-15
Expiry Date: 2027-01-31
"""


@dataclass
class FakeProvider:
    fail_doc_id: str | None = None
    fail_doc_ids: set[str] | None = None
    interrupt_doc_id: str | None = None
    failure_message: str = "Fake provider failed without leaking text."
    calls: list[str] | None = None
    run_ids: list[str] | None = None
    fields: tuple[ProviderFieldPayload, ...] | None = None

    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> ProviderExtractionResult:
        if self.calls is not None:
            self.calls.append(document.doc_id)
        if self.run_ids is not None:
            self.run_ids.append(run_id)
        if self.interrupt_doc_id == document.doc_id:
            raise KeyboardInterrupt()
        if self.fail_doc_id == document.doc_id or document.doc_id in (self.fail_doc_ids or set()):
            raise ExtractionProviderError(self.failure_message)
        return ProviderExtractionResult(
            fields=self.fields or _all_fields(),
            trace_id="trace-cli-fake",
            provider_name="fake",
        )


@dataclass
class FakeVisualProvider:
    calls: list[tuple[str, tuple[SDFFieldName, ...]]] | None = None
    run_ids: list[str] | None = None
    fields: tuple[ProviderFieldPayload, ...] | None = None

    def extract_visual_fields(
        self,
        *,
        document: DocumentMetadata,
        request: VisualFallbackRequest,
        run_id: str,
    ) -> ProviderExtractionResult:
        if self.calls is not None:
            self.calls.append((document.doc_id, request.eligible_field_names))
        if self.run_ids is not None:
            self.run_ids.append(run_id)
        return ProviderExtractionResult(
            fields=self.fields or (),
            trace_id="trace-cli-visual-fake",
            provider_name="fake-visual",
        )


def _field(
    field_name: SDFFieldName,
    raw_value: str,
    *,
    normalized_value: str | None = None,
    normalized_date: str | None = None,
) -> ProviderFieldPayload:
    return ProviderFieldPayload(
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        normalized_date=normalized_date,
        confidence=0.95,
        evidence=ProviderSourceEvidence(page_num=0, verbatim_span=raw_value, bbox={"x": 1, "y": 2, "w": 3, "h": 4}),
    )


def _all_fields() -> tuple[ProviderFieldPayload, ...]:
    return (
        _field(SDFFieldName.DOC_TYPE, "Supplier Declaration Form", normalized_value="SDF"),
        _field(SDFFieldName.VENDOR_NAME, "Acme Pharma Ltd."),
        _field(SDFFieldName.MANUFACTURING_DATE, "2024-01-05", normalized_date="2024-01-05"),
        _field(SDFFieldName.EFFECTIVE_DATE, "2024-02-01", normalized_date="2024-02-01"),
        _field(SDFFieldName.REVISION_DATE, "2024-03-15", normalized_date="2024-03-15"),
        _field(SDFFieldName.EXPIRY_DATE, "2027-01-31", normalized_date="2027-01-31"),
    )


def _all_fields_except_vendor() -> tuple[ProviderFieldPayload, ...]:
    return tuple(field for field in _all_fields() if field.field_name is not SDFFieldName.VENDOR_NAME)


def _prepare_doc(db_path: str, doc_id: str, *, status: str = "ingested", image_blob: bytes | None = None) -> None:
    insert_document(
        db_path,
        doc_id=doc_id,
        filename=f"{doc_id}.pdf",
        file_path=f"/tmp/{doc_id}.pdf",
        page_count=1,
        docling_json=None,
    )
    insert_page(db_path, doc_id=doc_id, page_num=0, page_text=PAGE_TEXT, image_blob=image_blob)
    if status == "ingested":
        mark_document_ingested(db_path, doc_id)


def test_extract_command_persists_compliance_row_with_safe_operator_output(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-001")
    provider = FakeProvider(calls=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: provider)

    result = runner.invoke(cli.app, ["extract", "--doc-id", "doc-001", "--db-path", tmp_db_path])

    assert result.exit_code == 0, result.output
    assert provider.calls == ["doc-001"]
    assert "OK doc_id=doc-001" in result.output
    assert "run_id=" in result.output
    assert "trace_id=trace-cli-fake" in result.output
    assert "Acme Pharma Ltd." not in result.output
    assert list_compliance_records(tmp_db_path)[0]["doc_id"] == "doc-001"


def test_extract_command_uses_explicit_run_id_for_provider_and_history(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-001")
    provider = FakeProvider(calls=[], run_ids=[])
    visual_constructed = False

    def fail_if_visual_provider_is_constructed(provider_name: str) -> FakeVisualProvider:
        nonlocal visual_constructed
        visual_constructed = True
        raise AssertionError("visual provider should not be constructed without --visual-fallback")

    monkeypatch.setattr(cli, "build_provider", lambda provider_name: provider)
    monkeypatch.setattr(cli, "build_visual_provider", fail_if_visual_provider_is_constructed)

    result = runner.invoke(
        cli.app,
        ["extract", "--doc-id", "doc-001", "--db-path", tmp_db_path, "--run-id", "baseline-run"],
    )

    assert result.exit_code == 0, result.output
    assert provider.calls == ["doc-001"]
    assert provider.run_ids == ["baseline-run"]
    assert visual_constructed is False
    assert "visual_fallback=false" in result.output
    assert "run_id=baseline-run" in result.output
    rows = list_compliance_records_for_run(tmp_db_path, "baseline-run")
    assert len(rows) == 1
    assert rows[0]["doc_id"] == "doc-001"
    assert rows[0]["run_id"] == "baseline-run"
    assert list_extraction_run_summaries(tmp_db_path)[0].resolved_model is None
    assert "Acme Pharma Ltd." not in result.output


def test_extract_command_visual_fallback_flag_passes_visual_provider_and_run_id(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-001", image_blob=b"fake-page-image")
    provider = FakeProvider(calls=[], run_ids=[], fields=_all_fields_except_vendor())
    visual_provider = FakeVisualProvider(
        calls=[],
        run_ids=[],
        fields=(_field(SDFFieldName.VENDOR_NAME, "Acme Pharma Ltd."),),
    )
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: provider)
    monkeypatch.setattr(cli, "build_visual_provider", lambda provider_name: visual_provider)

    result = runner.invoke(
        cli.app,
        [
            "extract",
            "--doc-id",
            "doc-001",
            "--db-path",
            tmp_db_path,
            "--run-id",
            "visual-run",
            "--visual-fallback",
        ],
    )

    assert result.exit_code == 0, result.output
    assert provider.calls == ["doc-001"]
    assert provider.run_ids == ["visual-run"]
    assert visual_provider.calls == [("doc-001", (SDFFieldName.VENDOR_NAME,))]
    assert visual_provider.run_ids == ["visual-run"]
    assert "visual_fallback=true" in result.output
    assert "run_id=visual-run" in result.output
    rows = list_compliance_records_for_run(tmp_db_path, "visual-run")
    assert len(rows) == 1
    assert rows[0]["doc_id"] == "doc-001"
    assert "Acme Pharma Ltd." not in result.output


def test_extract_all_filters_ingested_docs_deterministically_and_summarizes(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-b")
    _prepare_doc(tmp_db_path, "doc-a")
    _prepare_doc(tmp_db_path, "doc-pending", status="pending")
    provider = FakeProvider(calls=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: provider)

    result = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path])

    assert result.exit_code == 0, result.output
    assert provider.calls == ["doc-a", "doc-b"]
    assert "status=completed expected=2 attempted=2 succeeded=2 failed=0 skipped=0 corpus_version=unversioned" in result.output
    rows = list_compliance_records(tmp_db_path)
    assert {row["doc_id"] for row in rows} == {"doc-a", "doc-b"}
    assert "Supplier Declaration Form" not in result.output


def test_extract_all_uses_shared_explicit_run_id_for_provider_and_history(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-b")
    _prepare_doc(tmp_db_path, "doc-a")
    provider = FakeProvider(calls=[], run_ids=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: provider)

    result = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path, "--run-id", "candidate-run"])

    assert result.exit_code == 0, result.output
    assert provider.calls == ["doc-a", "doc-b"]
    assert provider.run_ids == ["candidate-run", "candidate-run"]
    assert "run_id=candidate-run" in result.output
    assert "status=completed expected=2 attempted=2 succeeded=2 failed=0 skipped=0 corpus_version=unversioned" in result.output
    rows = list_compliance_records_for_run(tmp_db_path, "candidate-run")
    assert {row["doc_id"] for row in rows} == {"doc-a", "doc-b"}
    assert {row["run_id"] for row in rows} == {"candidate-run"}
    assert "Supplier Declaration Form" not in result.output


def test_extract_unknown_doc_returns_safe_nonzero_message(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: FakeProvider(calls=[]))

    result = runner.invoke(cli.app, ["extract", "--doc-id", "missing-doc", "--db-path", tmp_db_path])

    assert result.exit_code == 1
    assert "reason=document_not_found" in result.output
    assert "doc_id=missing-doc" in result.output
    assert "Supplier Declaration Form" not in result.output


def test_extract_all_no_ingested_docs_returns_nonzero(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-pending", status="pending")
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: FakeProvider(calls=[]))

    result = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path])

    assert result.exit_code == 1
    assert "No ingested documents found" in result.output
    assert list_compliance_records(tmp_db_path) == []


def test_missing_gemini_credentials_fail_safely(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-001")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    cli.get_settings.cache_clear()

    try:
        result = runner.invoke(cli.app, ["extract", "--doc-id", "doc-001", "--db-path", tmp_db_path])
    finally:
        cli.get_settings.cache_clear()

    assert result.exit_code == 2
    assert result.exception is not None
    assert result.exception.__cause__ is None
    assert "reason=extraction_configuration_error" in result.output
    assert "GEMINI_API_KEY" not in result.output
    assert "Supplier Declaration Form" not in result.output


def test_extract_all_reports_provider_failure_without_raw_document_text(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-a")
    _prepare_doc(tmp_db_path, "doc-b")
    provider = FakeProvider(fail_doc_id="doc-b", calls=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: provider)

    result = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path])

    assert result.exit_code == 1
    assert provider.calls == ["doc-a", "doc-b"]
    assert "reason=extraction_provider_error" in result.output
    assert "doc_id=doc-b" in result.output
    assert "status=partial expected=2 attempted=2 succeeded=1 failed=1 skipped=0 corpus_version=unversioned" in result.output
    assert "Acme Pharma Ltd." not in result.output
    assert {row["doc_id"] for row in list_compliance_records(tmp_db_path)} == {"doc-a"}


def test_extract_all_auto_run_id_is_generated_once_and_shared_across_documents(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-b")
    _prepare_doc(tmp_db_path, "doc-a")
    provider = FakeProvider(calls=[], run_ids=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: provider)

    result = runner.invoke(
        cli.app,
        ["extract-all", "--db-path", tmp_db_path, "--corpus-version", "synthetic-v1"],
    )

    assert result.exit_code == 0, result.output
    assert provider.calls == ["doc-a", "doc-b"]
    assert provider.run_ids is not None
    assert len(set(provider.run_ids)) == 1
    effective_run_id = provider.run_ids[0]
    assert re.fullmatch(r"sdf-[0-9a-f]{32}", effective_run_id)
    assert (
        f"SUMMARY run_id={effective_run_id} status=completed expected=2 attempted=2 "
        "succeeded=2 failed=0 skipped=0 corpus_version=synthetic-v1"
    ) in result.output


def test_completed_resume_skips_every_provider_call_and_reports_durable_counts(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-a")
    _prepare_doc(tmp_db_path, "doc-b")
    first_provider = FakeProvider(calls=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: first_provider)
    first = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path, "--run-id", "resume-run"])
    assert first.exit_code == 0, first.output

    provider_constructed = False

    def forbidden_provider_construction(provider_name: str):
        nonlocal provider_constructed
        provider_constructed = True
        raise AssertionError("completed resume must not construct a provider")

    monkeypatch.setattr(cli, "build_provider", forbidden_provider_construction)
    resumed = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path, "--run-id", "resume-run"])

    assert resumed.exit_code == 0, resumed.output
    assert provider_constructed is False
    assert "status=completed expected=2 attempted=2 succeeded=2 failed=0 skipped=2" in resumed.output


def test_failed_child_resume_retries_only_failed_document_without_duplicate_history(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-a")
    _prepare_doc(tmp_db_path, "doc-b")
    first_provider = FakeProvider(fail_doc_id="doc-b", calls=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: first_provider)
    first = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path, "--run-id", "retry-run"])
    assert first.exit_code == 1, first.output

    retry_provider = FakeProvider(calls=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: retry_provider)
    retried = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path, "--run-id", "retry-run"])

    assert retried.exit_code == 0, retried.output
    assert retry_provider.calls == ["doc-b"]
    assert "status=completed expected=2 attempted=2 succeeded=2 failed=0 skipped=1" in retried.output
    conn = sqlite3.connect(tmp_db_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM extraction_history WHERE run_id = ?",
            ("retry-run",),
        ).fetchone()[0] == 12
        assert conn.execute(
            "SELECT COUNT(*) FROM compliance_record_history WHERE run_id = ?",
            ("retry-run",),
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT attempt_count FROM extraction_run_documents WHERE run_id = ? AND doc_id = ?",
            ("retry-run", "doc-b"),
        ).fetchone()[0] == 2
    finally:
        conn.close()


def test_extract_all_all_failed_persists_failed_terminal_state(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-a")
    _prepare_doc(tmp_db_path, "doc-b")
    provider = FakeProvider(fail_doc_ids={"doc-a", "doc-b"}, calls=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: provider)

    result = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path, "--run-id", "failed-run"])

    assert result.exit_code == 1, result.output
    assert provider.calls == ["doc-a", "doc-b"]
    assert "status=failed expected=2 attempted=2 succeeded=0 failed=2 skipped=0" in result.output
    summary = next(item for item in list_extraction_run_summaries(tmp_db_path) if item.run_id == "failed-run")
    assert summary.status.value == "failed"
    assert summary.completed_at is not None


def test_provider_construction_failure_marks_all_candidates_failed_without_leaking_exception(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-a")
    _prepare_doc(tmp_db_path, "doc-b")
    raw_sentinels = (
        "api-key-SUPERSECRET",
        "C:\\private\\supplier.pdf",
        "Supplier Declaration Form Vendor Name: Secret Vendor",
    )

    def fail_construction(provider_name: str):
        raise ExtractionConfigurationError(" | ".join(raw_sentinels))

    monkeypatch.setattr(cli, "build_provider", fail_construction)
    result = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path, "--run-id", "config-run"])

    assert result.exit_code == 2, result.output
    assert "reason=extraction_configuration_error" in result.output
    assert "status=failed expected=2 attempted=2 succeeded=0 failed=2 skipped=0" in result.output
    assert not any(sentinel in result.output for sentinel in raw_sentinels)
    conn = sqlite3.connect(tmp_db_path)
    try:
        reasons = {
            row[0]
            for row in conn.execute(
                "SELECT error_reason FROM extraction_run_documents WHERE run_id = ?",
                ("config-run",),
            )
        }
    finally:
        conn.close()
    assert reasons == {"extraction_configuration_error"}


def test_keyboard_interrupt_leaves_running_child_and_same_identity_resumes(monkeypatch, tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-a")
    _prepare_doc(tmp_db_path, "doc-b")
    interrupting = FakeProvider(interrupt_doc_id="doc-a", calls=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: interrupting)

    interrupted = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path, "--run-id", "interrupt-run"])

    assert interrupted.exit_code == 130
    assert isinstance(interrupted.exception, SystemExit)
    assert "SUMMARY" not in interrupted.output
    summary = next(item for item in list_extraction_run_summaries(tmp_db_path) if item.run_id == "interrupt-run")
    assert summary.status.value == "running"
    assert summary.completed_at is None
    candidates = list_resume_candidates(tmp_db_path, "interrupt-run")
    assert [(item.doc_id, item.status.value, item.attempt_count) for item in candidates] == [
        ("doc-a", "running", 1),
        ("doc-b", "pending", 0),
    ]

    resumed_provider = FakeProvider(calls=[])
    monkeypatch.setattr(cli, "build_provider", lambda provider_name: resumed_provider)
    resumed = runner.invoke(cli.app, ["extract-all", "--db-path", tmp_db_path, "--run-id", "interrupt-run"])
    assert resumed.exit_code == 0, resumed.output
    assert resumed_provider.calls == ["doc-a", "doc-b"]
    assert "status=completed expected=2 attempted=2 succeeded=2 failed=0 skipped=0" in resumed.output


@pytest.mark.parametrize("mismatch", ["manifest", "provider", "model", "corpus"])
def test_run_identity_mismatch_exits_two_before_provider_construction(
    monkeypatch,
    tmp_db_path: str,
    mismatch: str,
) -> None:
    init_db(tmp_db_path)
    _prepare_doc(tmp_db_path, "doc-a")
    _prepare_doc(tmp_db_path, "doc-b")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    cli.get_settings.cache_clear()
    begin_or_resume_extraction_run(
        tmp_db_path,
        run_id="identity-run",
        doc_ids=("doc-a", "doc-b"),
        provider="gemini",
        requested_model="gemini-2.5-flash",
        corpus_version="v1",
    )
    provider_calls = 0

    def forbidden_provider_construction(provider_name: str):
        nonlocal provider_calls
        provider_calls += 1
        return FakeProvider()

    monkeypatch.setattr(cli, "build_provider", forbidden_provider_construction)
    if mismatch == "manifest":
        args = ["extract", "--doc-id", "doc-a", "--db-path", tmp_db_path, "--run-id", "identity-run", "--corpus-version", "v1"]
    elif mismatch == "provider":
        args = ["extract-all", "--db-path", tmp_db_path, "--run-id", "identity-run", "--provider", "other", "--corpus-version", "v1"]
    elif mismatch == "model":
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
        cli.get_settings.cache_clear()
        args = ["extract-all", "--db-path", tmp_db_path, "--run-id", "identity-run", "--corpus-version", "v1"]
    else:
        args = ["extract-all", "--db-path", tmp_db_path, "--run-id", "identity-run", "--corpus-version", "v2"]

    try:
        result = runner.invoke(cli.app, args)
    finally:
        cli.get_settings.cache_clear()

    assert result.exit_code == 2, result.output
    assert provider_calls == 0
    assert "reason=extraction_run_identity_mismatch" in result.output
    assert [(item.doc_id, item.status.value) for item in list_resume_candidates(tmp_db_path, "identity-run")] == [
        ("doc-a", "pending"),
        ("doc-b", "pending"),
    ]
