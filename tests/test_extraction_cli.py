"""CLI tests for offline-safe SDF extraction commands."""
from __future__ import annotations

from dataclasses import dataclass

from typer.testing import CliRunner

from src.db.queries import DocumentMetadata, DocumentPage, insert_document, insert_page, mark_document_ingested
from src.db.schema import init_db
from src.extraction import cli
from src.extraction.models import SDFFieldName
from src.extraction.providers import (
    ExtractionProviderError,
    ProviderExtractionResult,
    ProviderFieldPayload,
    ProviderSourceEvidence,
    VisualFallbackRequest,
)
from src.extraction.repository import list_compliance_records, list_compliance_records_for_run

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
        if self.fail_doc_id == document.doc_id:
            raise ExtractionProviderError("Fake provider failed without leaking text.")
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
    assert "SUMMARY attempted=2 succeeded=2 failed=0" in result.output
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
    assert "SUMMARY attempted=2 succeeded=2 failed=0" in result.output
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
    assert "SUMMARY attempted=2 succeeded=1 failed=1" in result.output
    assert "Acme Pharma Ltd." not in result.output
    assert {row["doc_id"] for row in list_compliance_records(tmp_db_path)} == {"doc-a"}
