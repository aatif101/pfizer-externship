"""M001/S05 final-assembly proof for realistic offline SDF processing."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.dashboard.compliance import format_compliance_rows
from src.db.queries import DocumentMetadata, DocumentPage, load_document_pages
from src.db.schema import init_db
from src.extraction.models import SDFFieldName
from src.extraction.pipeline import extract_document
from src.extraction.providers import ProviderExtractionResult, ProviderFieldPayload, ProviderSourceEvidence
from src.extraction.repository import get_extraction_record, list_compliance_records
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
