"""M001/S05 final-assembly proof for realistic offline SDF processing."""
from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest
from typer.testing import CliRunner

from src.dashboard.chat import render_chat_tab
from src.dashboard.compliance import format_compliance_rows
from src.db.queries import DocumentMetadata, DocumentPage, insert_document, insert_page, load_document_pages, mark_document_ingested
from src.db.schema import init_db
from src.extraction.models import SDFFieldName
from src.extraction.pipeline import extract_document
from src.extraction.providers import ProviderExtractionResult, ProviderFieldPayload, ProviderSourceEvidence
from src.extraction.repository import get_extraction_record, list_compliance_records
from src.rag import AnswerConfigurationError, AnswerProviderRequest, AnswerProviderResult, AnswerReasonCode, AnswerResult, AnswerStatus, answer_question
from src.retrieval.cli import app as retrieval_cli_app
from src.pipeline.ingest import ingest_document

PDF_LINES = (
    "Supplier Declaration Form",
    "Vendor Name: Acme Pharma Ltd.",
    "Manufacturing Date: 2024-01-05",
    "Effective Date: 2024-02-01",
    "Revision Date: 2024-03-15",
    "Expiry Date: 2027-01-31",
    "Quality Unit Approval: Pfizer supplier documentation controls apply.",
)

REQUIRED_SPANS = (
    "Supplier Declaration Form",
    "Vendor Name: Acme Pharma Ltd.",
    "Manufacturing Date: 2024-01-05",
    "Effective Date: 2024-02-01",
    "Revision Date: 2024-03-15",
    "Expiry Date: 2027-01-31",
)


@dataclass
class GroundedFakeProvider:
    """Credential-free provider that cites spans from the ingested page text."""

    expected_doc_id: str
    seen_run_id: str | None = None

    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> ProviderExtractionResult:
        assert document.doc_id == self.expected_doc_id
        assert [page.page_num for page in pages] == [0]
        assert pages[0].page_text is not None
        self.seen_run_id = run_id
        return ProviderExtractionResult(
            fields=(
                provider_field(
                    SDFFieldName.DOC_TYPE,
                    "Supplier Declaration Form",
                    normalized_value="SDF",
                    span="Supplier Declaration Form",
                ),
                provider_field(
                    SDFFieldName.VENDOR_NAME,
                    "Acme Pharma Ltd.",
                    span="Acme Pharma Ltd.",
                ),
                provider_field(
                    SDFFieldName.MANUFACTURING_DATE,
                    "2024-01-05",
                    normalized_date="2024-01-05",
                    span="2024-01-05",
                ),
                provider_field(
                    SDFFieldName.EFFECTIVE_DATE,
                    "2024-02-01",
                    normalized_date="2024-02-01",
                    span="2024-02-01",
                ),
                provider_field(
                    SDFFieldName.REVISION_DATE,
                    "2024-03-15",
                    normalized_date="2024-03-15",
                    span="2024-03-15",
                ),
                provider_field(
                    SDFFieldName.EXPIRY_DATE,
                    "2027-01-31",
                    normalized_date="2027-01-31",
                    span="2027-01-31",
                ),
            ),
            trace_id="trace-s05-proof-001",
            provider_name="grounded-fake-provider",
        )


def provider_field(
    field_name: SDFFieldName,
    raw_value: str,
    *,
    normalized_value: str | None = None,
    normalized_date: str | None = None,
    span: str | None = None,
) -> ProviderFieldPayload:
    return ProviderFieldPayload(
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        normalized_date=normalized_date,
        confidence=0.9,
        evidence=ProviderSourceEvidence(
            page_num=0,
            verbatim_span=span or raw_value,
            bbox={"x": 72, "y": 120, "width": 320, "height": 18},
        ),
    )


def test_realistic_pdf_ingests_extracts_persists_risk_and_formats_dashboard_row(tmp_path: Path) -> None:
    db_path = str(tmp_path / "s05-proof.db")
    pdf_path = tmp_path / "realistic_supplier_declaration_form.pdf"
    write_minimal_text_pdf(pdf_path, PDF_LINES)

    init_db(db_path)
    ingest_result = ingest_document(str(pdf_path), db_path)

    assert ingest_result["page_count"] == 1
    assert ingest_result["image_count"] == 1

    loaded = load_document_pages(db_path, ingest_result["doc_id"])
    assert loaded is not None
    assert len(loaded.pages) == 1
    page_text = loaded.pages[0].page_text or ""
    assert page_text.strip()
    for span in REQUIRED_SPANS:
        assert span in page_text

    provider = GroundedFakeProvider(expected_doc_id=ingest_result["doc_id"])
    result = extract_document(
        db_path,
        ingest_result["doc_id"],
        provider,
        today=date(2026, 1, 6),
        run_id="run-s05-proof-001",
    )

    assert provider.seen_run_id == "run-s05-proof-001"
    assert result.diagnostics.trace_id == "trace-s05-proof-001"
    assert result.diagnostics.provider_name == "grounded-fake-provider"
    assert result.diagnostics.page_count == 1
    assert result.record.risk_level == "amber"
    assert result.record.age_days == 732
    assert extraction_count(db_path, ingest_result["doc_id"]) == 6

    stored = get_extraction_record(db_path, ingest_result["doc_id"])
    assert stored is not None
    assert set(stored.fields) == set(SDFFieldName)
    assert stored.run_id == "run-s05-proof-001"
    assert stored.trace_id == "trace-s05-proof-001"

    compliance_rows = list_compliance_records(db_path)
    assert len(compliance_rows) == 1
    compliance = compliance_rows[0]
    assert compliance["doc_id"] == ingest_result["doc_id"]
    assert compliance["vendor_name"] == "Acme Pharma Ltd."
    assert compliance["risk_level"] == "amber"
    assert compliance["age_days"] == 732
    assert compliance["source_page"] == 0
    assert compliance["source_verbatim_span"] == "2027-01-31"
    assert compliance["run_id"] == "run-s05-proof-001"
    assert compliance["trace_id"] == "trace-s05-proof-001"

    formatted = format_compliance_rows(compliance_rows)
    assert formatted[0]["vendor_name"] == "Acme Pharma Ltd."
    assert formatted[0]["source_page_label"] == "Page 1"
    assert formatted[0]["source_verbatim_span"] == "2027-01-31"
    assert formatted[0]["aggregate_confidence_display"] == "90%"


FORBIDDEN_PUBLIC_VALUES = (
    "GEMINI_API_KEY=fake-s05-secret",
    "RAW_PROVIDER_PAYLOAD_SHOULD_NOT_RENDER",
    "FULL_PAGE_TAIL_SHOULD_NOT_RENDER",
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
)


@dataclass
class S05FakeAnswerProvider:
    """Fake answer provider that records the bounded evidence request."""

    answer_text: str = "Acme Pharma has Pfizer supplier approval evidence in the cited SDF page."
    provider_name: str = "s05-fake-answer-provider"
    trace_id: str | None = "trace-s05-rag-001"
    exception: BaseException | None = None
    calls: list[AnswerProviderRequest] = field(default_factory=list)

    def answer(self, request: AnswerProviderRequest) -> AnswerProviderResult:
        self.calls.append(request)
        if self.exception is not None:
            raise self.exception
        return AnswerProviderResult(
            answer_text=self.answer_text,
            trace_id=self.trace_id,
            provider_name=self.provider_name,
        )


class S05FakeContext(AbstractContextManager["S05FakeContext"]):
    def __init__(self, fake_st: "S05FakeStreamlit", kind: str, label: str) -> None:
        self.fake_st = fake_st
        self.kind = kind
        self.label = label

    def __enter__(self) -> "S05FakeContext":
        self.fake_st.context_stack.append((self.kind, self.label))
        self.fake_st.context_entries.append((self.kind, self.label))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.fake_st.context_stack.pop()


class S05FakeStreamlit:
    def __init__(self, prompts: list[str | None] | None = None) -> None:
        self.session_state: dict[str, Any] = {}
        self.prompts = list(prompts or [])
        self.context_stack: list[tuple[str, str]] = []
        self.context_entries: list[tuple[str, str]] = []
        self.markdown_messages: list[str] = []
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.error_messages: list[str] = []
        self.caption_messages: list[str] = []
        self.chat_inputs: list[str] = []
        self.expanders: list[tuple[str, bool]] = []

    def chat_message(self, role: str) -> S05FakeContext:
        return S05FakeContext(self, "chat_message", role)

    def expander(self, label: str, *, expanded: bool = False) -> S05FakeContext:
        self.expanders.append((label, expanded))
        return S05FakeContext(self, "expander", label)

    def chat_input(self, placeholder: str) -> str | None:
        self.chat_inputs.append(placeholder)
        if not self.prompts:
            return None
        return self.prompts.pop(0)

    def markdown(self, message: str) -> None:
        self.markdown_messages.append(message)

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)

    def caption(self, message: str) -> None:
        self.caption_messages.append(message)

    def all_rendered_text(self) -> str:
        return "\n".join(
            [
                *self.markdown_messages,
                *self.info_messages,
                *self.warning_messages,
                *self.error_messages,
                *self.caption_messages,
            ]
        )


def test_m002_retrieval_rag_chat_operational_proof_is_grounded_observable_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "m002-s05-operational-proof.db")
    init_db(db_path)
    _seed_m002_supplier_pages(db_path)

    cli_runner = CliRunner()
    build = cli_runner.invoke(retrieval_cli_app, ["build", "--db-path", db_path])

    assert build.exit_code == 0
    assert "status=built" in build.output
    assert "run_id=retrieval-built-" in build.output
    assert "indexed_docs=2" in build.output
    assert "indexed_pages=2" in build.output
    assert "source_pages=2" in build.output
    assert "content_hash=" in build.output
    assert "reason=none" in build.output
    _assert_forbidden_absent(build.output)
    assert "Acme Pharma" not in build.output
    assert "Pfizer quality unit approval" not in build.output

    provider = S05FakeAnswerProvider()
    happy = answer_question(db_path, "Does Acme have Pfizer supplier approval?", provider=provider, top_k=1)

    assert happy.status is AnswerStatus.ANSWERED
    assert happy.answer_text == provider.answer_text
    assert len(provider.calls) == 1
    assert provider.calls[0].question == "Does Acme have Pfizer supplier approval?"
    assert provider.calls[0].run_id == happy.diagnostics.run_id
    assert len(provider.calls[0].evidence) == 1
    assert not hasattr(provider.calls[0].evidence[0], "page_text")
    provider_snippet = provider.calls[0].evidence[0].snippet
    assert "Acme Pharma" in provider_snippet
    assert "Pfizer quality unit approval" in provider_snippet
    assert len(provider_snippet) <= 222
    _assert_forbidden_absent(provider_snippet)

    assert len(happy.citations) == 1
    citation = happy.citations[0]
    assert citation.filename == "acme-supplier-sdf.pdf"
    assert citation.display_page_num == 1
    assert "Acme Pharma" in citation.snippet
    assert len(citation.snippet) <= 222
    assert happy.diagnostics.reason_code is AnswerReasonCode.ANSWERED
    assert happy.diagnostics.provider_name == "s05-fake-answer-provider"
    assert happy.diagnostics.trace_id == "trace-s05-rag-001"
    assert happy.diagnostics.run_id and happy.diagnostics.run_id.startswith("retrieval-built-")
    assert happy.diagnostics.top_score > 0
    assert happy.diagnostics.citation_count == 1
    assert happy.diagnostics.evidence_reason == "strong_evidence"
    _assert_forbidden_absent(repr(happy))

    weak_provider = S05FakeAnswerProvider()
    weak = answer_question(db_path, "Who won the astronomy prize on Mars?", provider=weak_provider, top_k=1)

    assert weak.status is AnswerStatus.ABSTAINED
    assert weak.citations == ()
    assert weak_provider.calls == []
    assert weak.diagnostics.reason_code is AnswerReasonCode.NO_MATCH
    assert weak.diagnostics.citation_count == 0
    assert weak.diagnostics.provider_name == "s05-fake-answer-provider"
    _assert_forbidden_absent(repr(weak))

    fake_st = S05FakeStreamlit(prompts=["Does Acme have Pfizer supplier approval?"])
    chat_provider = S05FakeAnswerProvider()

    def chat_answer_fn(db_path_arg: str, question: str, *, provider: Any) -> AnswerResult:
        assert db_path_arg == db_path
        assert provider is chat_provider
        return answer_question(db_path_arg, question, provider=provider, top_k=1)

    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab(db_path, provider_factory=lambda: chat_provider, answer_fn=chat_answer_fn)

    rendered = fake_st.all_rendered_text()
    assert len(chat_provider.calls) == 1
    assert len(fake_st.session_state["pfizer_chat_messages"]) == 2
    assert "Does Acme have Pfizer supplier approval?" in rendered
    assert "Acme Pharma has Pfizer supplier approval evidence" in rendered
    assert "acme-supplier-sdf.pdf" in rendered
    assert "Page 1" in rendered
    assert "Acme Pharma" in rendered
    assert "score " in rendered
    assert "**Answer status:** answered" in rendered
    assert "**Reason code:** answered" in rendered
    assert "**Run ID:** retrieval-built-" in rendered
    assert "**Provider:** s05-fake-answer-provider" in rendered
    assert "**Trace ID:** trace-s05-rag-001" in rendered
    assert "**Top score:**" in rendered
    assert "**Citation count:** 1" in rendered
    assert "**Evidence reason:** strong_evidence" in rendered
    _assert_forbidden_absent(rendered)

    failing_provider = S05FakeAnswerProvider(
        exception=RuntimeError("RAW_PROVIDER_PAYLOAD_SHOULD_NOT_RENDER GEMINI_API_KEY=fake-s05-secret")
    )
    failed = answer_question(db_path, "Does Acme have Pfizer supplier approval?", provider=failing_provider, top_k=1)

    assert len(failing_provider.calls) == 1
    assert failed.status is AnswerStatus.PROVIDER_ERROR
    assert failed.citations == ()
    assert failed.diagnostics.reason_code is AnswerReasonCode.PROVIDER_EXCEPTION
    assert failed.diagnostics.error_class == "RuntimeError"
    assert failed.diagnostics.provider_name == "s05-fake-answer-provider"
    assert failed.diagnostics.citation_count == 0
    _assert_forbidden_absent(repr(failed))

    error_st = S05FakeStreamlit(prompts=["Does Acme have Pfizer supplier approval?"])
    monkeypatch.setattr("src.dashboard.chat.st", error_st)

    render_chat_tab(
        db_path,
        provider_factory=lambda: failing_provider,
        answer_fn=lambda db_path_arg, question, *, provider: answer_question(db_path_arg, question, provider=provider, top_k=1),
    )

    error_rendered = error_st.all_rendered_text()
    assert "I found relevant evidence, but answer generation failed safely" in error_rendered
    assert "Answer generation failed safely" in error_rendered
    assert "**Answer status:** provider_error" in error_rendered
    assert "**Reason code:** provider_exception" in error_rendered
    assert "**Provider:** s05-fake-answer-provider" in error_rendered
    assert "**Safe error class:** RuntimeError" in error_rendered
    assert "**Citation count:** 0" in error_rendered
    _assert_forbidden_absent(error_rendered)

    config_error_st = S05FakeStreamlit(prompts=["Does Acme have Pfizer supplier approval?"])
    monkeypatch.setattr("src.dashboard.chat.st", config_error_st)

    def unsafe_provider_factory() -> S05FakeAnswerProvider:
        raise AnswerConfigurationError("GEMINI_API_KEY=fake-s05-secret RAW_PROVIDER_PAYLOAD_SHOULD_NOT_RENDER")

    render_chat_tab(
        db_path,
        provider_factory=unsafe_provider_factory,
        answer_fn=lambda db_path_arg, question, *, provider: answer_question(db_path_arg, question, provider=provider, top_k=1),
    )

    config_rendered = config_error_st.all_rendered_text()
    assert "Chat answer provider is not ready" in config_rendered
    assert "**Answer status:** provider_error" in config_rendered
    assert "**Reason code:** provider_configuration_error" in config_rendered
    assert "**Provider:** gemini" in config_rendered
    assert "**Safe error class:** AnswerConfigurationError" in config_rendered
    _assert_forbidden_absent(config_rendered)


def _seed_m002_supplier_pages(db_path: str) -> None:
    acme_text = " ".join(
        (
            "Supplier Declaration Form.",
            "Vendor Name: Acme Pharma Ltd.",
            "Pfizer quality unit approval confirms supplier compliance controls for the sterile excipient SDF.",
            "Expiry Date: 2027-01-31.",
            "Lot coverage: ACME-2026-001.",
            "Routine filler text keeps the public answer snippet bounded away from the planted tail.",
            "more filler " * 40,
            FORBIDDEN_PUBLIC_VALUES[0],
            FORBIDDEN_PUBLIC_VALUES[1],
            FORBIDDEN_PUBLIC_VALUES[2],
            FORBIDDEN_PUBLIC_VALUES[3],
        )
    )
    beta_text = " ".join(
        (
            "Certificate of Analysis.",
            "Vendor Name: Beta Labs.",
            "Material identity confirmed for retained supplier sample.",
            "No unrelated award or science-topic content is present in this supplier file.",
        )
    )
    insert_document(db_path, "doc-acme-s05", "acme-supplier-sdf.pdf", "/fixture/acme-supplier-sdf.pdf", 1, docling_json=None)
    insert_page(db_path, "doc-acme-s05", 0, acme_text, image_blob=b"image bytes must remain private")
    mark_document_ingested(db_path, "doc-acme-s05")
    insert_document(db_path, "doc-beta-s05", "beta-coa.pdf", "/fixture/beta-coa.pdf", 1, docling_json=None)
    insert_page(db_path, "doc-beta-s05", 0, beta_text, image_blob=b"other image bytes must remain private")
    mark_document_ingested(db_path, "doc-beta-s05")


def _assert_forbidden_absent(text: str) -> None:
    for forbidden in FORBIDDEN_PUBLIC_VALUES:
        assert forbidden not in text
    assert "fake-s05-secret" not in text
    assert "image bytes" not in text


def extraction_count(db_path: str, doc_id: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM extractions WHERE doc_id = ?", (doc_id,)).fetchone()
        return int(row[0])
    finally:
        conn.close()


def write_minimal_text_pdf(path: Path, lines: tuple[str, ...]) -> None:
    """Write a tiny dependency-free PDF that Docling can extract as text."""

    text_ops = ["BT", "/F1 12 Tf", "72 740 Td", "16 TL"]
    for index, line in enumerate(lines):
        operator = "Tj" if index == 0 else "'"
        text_ops.append(f"({escape_pdf_text(line)}) {operator}")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for obj_num, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{obj_num} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(output))


def escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
