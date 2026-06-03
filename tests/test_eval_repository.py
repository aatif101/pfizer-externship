from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from src.db.queries import insert_document
from src.db.schema import init_db
from src.eval.repository import (
    RAGEvalObservationRow,
    create_eval_run,
    insert_rag_eval_observation,
    list_eval_metrics,
    list_eval_runs,
    list_gold_extraction_labels,
    list_gold_retrieval_queries,
    list_gold_retrieval_targets,
    list_predicted_extractions,
    list_predicted_extractions_for_run,
    list_rag_eval_observations,
    mark_eval_run_complete,
    mark_eval_run_error,
    upsert_eval_metric,
)
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
from src.extraction.repository import upsert_extraction_record


def _eval_field(
    field_name: SDFFieldName,
    raw_value: str,
    *,
    normalized_value: str | None = None,
    normalized_date: date | None = None,
    review_state: ReviewState = ReviewState.PENDING,
) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value if normalized_value is not None else raw_value,
        normalized_date=normalized_date,
        confidence=0.9,
        evidence=SourceEvidence(page_num=0, bbox={"x": 1, "y": 2}, verbatim_span=raw_value),
        review_state=review_state,
    )


def _eval_record(doc_id: str, *, vendor_name: str, run_id: str) -> SDFExtractionRecord:
    fields = {
        SDFFieldName.DOC_TYPE: _eval_field(SDFFieldName.DOC_TYPE, "Supplier Declaration Form", normalized_value="SDF"),
        SDFFieldName.VENDOR_NAME: _eval_field(SDFFieldName.VENDOR_NAME, vendor_name),
        SDFFieldName.MANUFACTURING_DATE: _eval_field(
            SDFFieldName.MANUFACTURING_DATE,
            "2024-01-05",
            normalized_date=date(2024, 1, 5),
        ),
        SDFFieldName.EFFECTIVE_DATE: _eval_field(
            SDFFieldName.EFFECTIVE_DATE,
            "2024-02-01",
            normalized_date=date(2024, 2, 1),
        ),
        SDFFieldName.REVISION_DATE: _eval_field(
            SDFFieldName.REVISION_DATE,
            "2024-03-15",
            normalized_date=date(2024, 3, 15),
            review_state=ReviewState.REVIEWED,
        ),
        SDFFieldName.EXPIRY_DATE: _eval_field(
            SDFFieldName.EXPIRY_DATE,
            "2027-01-31",
            normalized_date=date(2027, 1, 31),
        ),
    }
    return SDFExtractionRecord(
        doc_id=doc_id,
        filename=f"{doc_id}.pdf",
        fields=fields,
        trace_id=f"trace-{run_id}",
        run_id=run_id,
        extracted_at=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
    )


def _insert_eval_document(db_path: str, doc_id: str) -> None:
    insert_document(
        db_path,
        doc_id=doc_id,
        filename=f"{doc_id}.pdf",
        file_path=f"/tmp/{doc_id}.pdf",
        page_count=1,
        docling_json=None,
    )


def test_eval_run_create_and_list_is_idempotent(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    create_eval_run(
        db_path,
        run_id="run-1",
        eval_type="extraction",
        pipeline_label="baseline",
        params={"a": 1, "b": 2},
    )
    # Streamlit rerun simulation
    create_eval_run(
        db_path,
        run_id="run-1",
        eval_type="extraction",
        pipeline_label="baseline",
        params={"b": 2, "a": 1},
    )

    runs = list_eval_runs(db_path)
    assert [r.run_id for r in runs] == ["run-1"]
    assert runs[0].status == "running"
    assert runs[0].pipeline_label == "baseline"
    assert json.loads(runs[0].params_json or "{}") == {"a": 1, "b": 2}

    mark_eval_run_complete(db_path, "run-1")
    runs2 = list_eval_runs(db_path)
    assert runs2[0].status == "complete"
    assert runs2[0].completed_at is not None


def test_eval_run_error_sets_status_and_reason(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    create_eval_run(db_path, "run-err", "retrieval", "pl", params={})
    mark_eval_run_error(db_path, "run-err", "boom")

    runs = list_eval_runs(db_path)
    assert runs[0].run_id == "run-err"
    assert runs[0].status == "error"
    assert runs[0].error_reason == "boom"
    assert runs[0].completed_at is not None


def test_eval_metric_upsert_dedupes(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)
    create_eval_run(db_path, "run-1", "rag", None, params={})

    upsert_eval_metric(db_path, "run-1", "faithfulness", 0.5)
    upsert_eval_metric(db_path, "run-1", "faithfulness", 0.7)

    metrics = list_eval_metrics(db_path, "run-1")
    assert len(metrics) == 1
    assert metrics[0].metric_name == "faithfulness"
    assert metrics[0].metric_value == 0.7

    upsert_eval_metric(db_path, "run-1", "ndcg@5", 0.8, scope_type="query", scope_id="q1")
    upsert_eval_metric(db_path, "run-1", "ndcg@5", 0.9, scope_type="query", scope_id="q1")

    metrics2 = list_eval_metrics(db_path, "run-1")
    assert len(metrics2) == 2
    by_key = {(m.metric_name, m.scope_type, m.scope_id): m for m in metrics2}
    assert by_key[("ndcg@5", "query", "q1")].metric_value == 0.9


def test_gold_list_helpers_return_empty_lists_on_empty_db(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    assert list_gold_extraction_labels(db_path) == []
    assert list_gold_retrieval_queries(db_path) == []
    assert list_gold_retrieval_targets(db_path, "missing") == []


def test_list_predicted_extractions_for_run_filters_history_without_latest_fallback(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)
    _insert_eval_document(db_path, "doc-a")
    _insert_eval_document(db_path, "doc-b")

    upsert_extraction_record(db_path, _eval_record("doc-a", vendor_name="Baseline Vendor A", run_id="baseline-run"))
    upsert_extraction_record(db_path, _eval_record("doc-b", vendor_name="Baseline Vendor B", run_id="baseline-run"))
    upsert_extraction_record(db_path, _eval_record("doc-a", vendor_name="Candidate Vendor A", run_id="candidate-run"))

    baseline_rows = list_predicted_extractions_for_run(db_path, "baseline-run")
    candidate_rows = list_predicted_extractions_for_run(db_path, "candidate-run")
    latest_rows = list_predicted_extractions(db_path)

    assert len(baseline_rows) == 12
    assert len(candidate_rows) == 6
    assert [(row["doc_id"], row["field_name"]) for row in baseline_rows] == sorted(
        (row["doc_id"], row["field_name"]) for row in baseline_rows
    )
    baseline_vendors = [row for row in baseline_rows if row["field_name"] == "vendor_name"]
    assert baseline_vendors == [
        {
            "doc_id": "doc-a",
            "field_name": "vendor_name",
            "normalized_value": "Baseline Vendor A",
            "review_state": "pending",
        },
        {
            "doc_id": "doc-b",
            "field_name": "vendor_name",
            "normalized_value": "Baseline Vendor B",
            "review_state": "pending",
        },
    ]
    assert [row["normalized_value"] for row in candidate_rows if row["field_name"] == "vendor_name"] == [
        "Candidate Vendor A"
    ]
    assert [row["normalized_value"] for row in latest_rows if row["field_name"] == "vendor_name"] == [
        "Candidate Vendor A",
        "Baseline Vendor B",
    ]
    assert list_predicted_extractions_for_run(db_path, "missing-run") == []


def test_rag_eval_observation_insert_and_list_multiple_rows(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    first_id = insert_rag_eval_observation(
        db_path,
        RAGEvalObservationRow(
            source_run_id="rag-run-1",
            query_id="q1",
            status="complete",
            latency_ms="123.5",
            input_tokens="10",
            output_tokens=20,
            total_tokens=30,
            cost_usd="0.0042",
            faithfulness="0.9",
            answer_relevancy=0.8,
            cited_doc_id="doc-a",
            cited_page_num="2",
        ),
    )
    second_id = insert_rag_eval_observation(
        db_path,
        RAGEvalObservationRow(
            source_run_id="rag-run-2",
            query_id="q2",
            status="weak_evidence",
            latency_ms=50,
            input_tokens=5,
            output_tokens=6,
            total_tokens=11,
            cost_usd=0.001,
            faithfulness=None,
            answer_relevancy=None,
            cited_doc_id=None,
            cited_page_num=None,
        ),
    )

    assert first_id != second_id
    observations = list_rag_eval_observations(db_path)
    assert [row.observation_id for row in observations] == [first_id, second_id]
    assert observations[0].source_run_id == "rag-run-1"
    assert observations[0].query_id == "q1"
    assert observations[0].latency_ms == 123.5
    assert observations[0].input_tokens == 10
    assert observations[0].output_tokens == 20
    assert observations[0].total_tokens == 30
    assert observations[0].cost_usd == 0.0042
    assert observations[0].faithfulness == 0.9
    assert observations[0].answer_relevancy == 0.8
    assert observations[0].cited_doc_id == "doc-a"
    assert observations[0].cited_page_num == 2
    assert observations[0].created_at is not None

    by_source = list_rag_eval_observations(db_path, source_run_id="rag-run-2")
    assert [row.query_id for row in by_source] == ["q2"]

    by_query = list_rag_eval_observations(db_path, query_id="q1")
    assert [row.source_run_id for row in by_query] == ["rag-run-1"]


def test_rag_eval_observation_empty_and_nullable_numeric_fields(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    assert list_rag_eval_observations(db_path, source_run_id="missing") == []

    row_id = insert_rag_eval_observation(
        db_path,
        RAGEvalObservationRow(source_run_id="rag-run-null", query_id="q-null", status="error"),
    )

    observations = list_rag_eval_observations(db_path)
    assert len(observations) == 1
    assert observations[0].observation_id == row_id
    assert observations[0].latency_ms is None
    assert observations[0].input_tokens is None
    assert observations[0].output_tokens is None
    assert observations[0].total_tokens is None
    assert observations[0].cost_usd is None
    assert observations[0].faithfulness is None
    assert observations[0].answer_relevancy is None
    assert observations[0].cited_page_num is None


def test_rag_eval_observation_rejects_malformed_numeric_values(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    with pytest.raises(ValueError, match="latency_ms"):
        insert_rag_eval_observation(
            db_path,
            RAGEvalObservationRow(status="complete", latency_ms="slow"),
        )

    with pytest.raises(ValueError, match="input_tokens"):
        insert_rag_eval_observation(
            db_path,
            RAGEvalObservationRow(status="complete", input_tokens=True),
        )

    assert list_rag_eval_observations(db_path) == []
