"""Tests for provider-free hybrid text retrieval over the SQLite index."""
from __future__ import annotations

import sqlite3

from src.db.queries import insert_document, insert_page, mark_document_ingested
from src.db.schema import init_db
from src.retrieval.indexer import build_retrieval_index
from src.retrieval.models import RetrievalEvidenceReason
from src.retrieval.retriever import HybridTextRetriever, extract_search_terms, make_fts_query, retrieve_evidence


def _seed_doc(db_path: str, *, doc_id: str, filename: str, pages: tuple[str, ...]) -> None:
    insert_document(db_path, doc_id, filename, f"/tmp/{filename}", len(pages), docling_json=None)
    mark_document_ingested(db_path, doc_id)
    for page_num, text in enumerate(pages):
        insert_page(db_path, doc_id, page_num, text, image_blob=None)


def test_hybrid_retriever_ranks_expected_supplier_page_first(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-acme",
        filename="acme-supplier-sdf.pdf",
        pages=(
            "Supplier Declaration Form. Vendor Name: Acme Pharma Ltd. Quality Unit Approval: Pfizer supplier compliance documentation controls apply. Expiry Date: 2027-01-31.",
            "Packaging specification appendix with storage conditions and unrelated dimensional tolerances.",
        ),
    )
    _seed_doc(
        tmp_db_path,
        doc_id="doc-beta",
        filename="beta-certificate.pdf",
        pages=("Certificate of Analysis for Beta Labs. No Acme supplier compliance statement is included here.",),
    )
    built = build_retrieval_index(tmp_db_path)

    result = HybridTextRetriever(tmp_db_path).retrieve("Which page mentions Acme supplier compliance approval?", top_k=2)

    assert result.is_strong is True
    assert result.reason_code is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert result.reason is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert result.run_id == built.run.run_id
    assert result.content_hash == built.run.content_hash[:16]
    assert result.query_terms == ("mentions", "acme", "supplier", "compliance", "approval")
    assert result.top_score > 0
    assert result.hits
    top = result.hits[0]
    assert top.filename == "acme-supplier-sdf.pdf"
    assert top.doc_id == "doc-acme"
    assert top.page_num == 0
    assert top.display_page_num == 1
    assert top.score > 0
    assert top.score_components.token_coverage > 0
    assert top.score_components.lexical_score > 0
    assert top.score_components.source in {"fts", "lexical"}
    assert "Acme Pharma Ltd." in top.snippet
    assert "supplier compliance documentation controls" in top.snippet
    assert len(top.snippet) <= 222  # allows ellipsis on both sides around the 220-char payload
    assert not hasattr(top, "page_text")


def test_hybrid_retriever_falls_back_to_lexical_when_fts_table_is_absent(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-gamma",
        filename="gamma-sdf.pdf",
        pages=("Gamma supplier declaration includes validated compliance controls for Pfizer.",),
    )
    build_retrieval_index(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("DROP TABLE retrieval_index_page_fts")
    conn.commit()
    conn.close()

    result = HybridTextRetriever(tmp_db_path).retrieve("Gamma compliance controls", top_k=1)

    assert result.reason is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert result.hits[0].doc_id == "doc-gamma"
    assert result.hits[0].score_components.source == "lexical"
    assert result.hits[0].score_components.fts_score == 0


def test_hybrid_retriever_sanitizes_punctuation_metacharacters_and_repeated_terms(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-delta",
        filename="delta-sdf.pdf",
        pages=("Delta supplier certificate states GMP compliance and approved vendor status.",),
    )
    build_retrieval_index(tmp_db_path)

    result = HybridTextRetriever(tmp_db_path).retrieve('Delta NEAR/1 compliance* OR "x" supplier supplier', top_k=1)

    assert result.reason is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert result.query_terms == ("delta", "near", "compliance", "supplier")
    assert result.hits[0].doc_id == "doc-delta"
    assert "Delta supplier certificate" in result.hits[0].snippet


def test_hybrid_retriever_returns_empty_question_for_stopword_only_query(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-empty", filename="empty.pdf", pages=("Some searchable text",))
    build_retrieval_index(tmp_db_path)

    result = HybridTextRetriever(tmp_db_path).retrieve("the and of to in", top_k=1)

    assert result.reason is RetrievalEvidenceReason.EMPTY_QUESTION
    assert result.hits == ()
    assert result.query_terms == ()
    assert result.top_score == 0


def test_evidence_gate_returns_strong_evidence_for_fixture_supplier_question(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-acme",
        filename="acme-supplier-sdf.pdf",
        pages=(
            "Supplier Declaration Form. Vendor Name: Acme Pharma Ltd. Quality Unit Approval: Pfizer supplier compliance documentation controls apply. Expiry Date: 2027-01-31.",
        ),
    )
    built = build_retrieval_index(tmp_db_path)

    result = retrieve_evidence(tmp_db_path, "Acme supplier compliance approval", top_k=1)

    assert result.is_strong is True
    assert result.reason_code is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert result.run_id == built.run.run_id
    assert result.content_hash_prefix == built.run.content_hash[:16]
    assert result.top_score >= 0.45
    assert result.hits[0].filename == "acme-supplier-sdf.pdf"
    assert result.hits[0].display_page_num == 1
    assert "Acme Pharma Ltd." in result.hits[0].snippet


def test_evidence_gate_returns_empty_question_for_blank_and_stopword_only_queries(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-empty", filename="empty.pdf", pages=("Some searchable text",))
    build_retrieval_index(tmp_db_path)

    for question in ("", "   \t\n ", "the and of to in"):
        result = retrieve_evidence(tmp_db_path, question, top_k=1)

        assert result.is_strong is False
        assert result.reason_code is RetrievalEvidenceReason.EMPTY_QUESTION
        assert result.hits == ()
        assert result.query_terms == ()
        assert result.top_score == 0


def test_evidence_gate_returns_index_missing_before_build(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-missing", filename="missing.pdf", pages=("Supplier compliance text",))

    result = retrieve_evidence(tmp_db_path, "supplier compliance", top_k=1)

    assert result.is_strong is False
    assert result.reason_code is RetrievalEvidenceReason.INDEX_MISSING
    assert result.hits == ()
    assert result.run_id is None
    assert result.content_hash_prefix is not None


def test_evidence_gate_returns_index_empty_for_empty_indexed_corpus(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    build_retrieval_index(tmp_db_path)

    result = retrieve_evidence(tmp_db_path, "supplier compliance", top_k=1)

    assert result.is_strong is False
    assert result.reason_code is RetrievalEvidenceReason.INDEX_EMPTY
    assert result.hits == ()
    assert result.top_score == 0


def test_evidence_gate_returns_index_stale_without_querying_old_hits(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-stale", filename="stale.pdf", pages=("Original supplier compliance evidence",))
    build_retrieval_index(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("UPDATE pages SET page_text = ? WHERE doc_id = ? AND page_num = ?", ("Mutated source page text", "doc-stale", 0))
    conn.commit()
    conn.close()

    result = retrieve_evidence(tmp_db_path, "Original supplier compliance", top_k=1)

    assert result.is_strong is False
    assert result.reason_code is RetrievalEvidenceReason.INDEX_STALE
    assert result.hits == ()
    assert result.top_score == 0


def test_evidence_gate_returns_no_match_for_unrelated_question(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-zeta", filename="zeta-sdf.pdf", pages=("Zeta supplier compliance page",))
    build_retrieval_index(tmp_db_path)

    result = retrieve_evidence(tmp_db_path, "astronomy telescope nebula", top_k=1)

    assert result.is_strong is False
    assert result.reason_code is RetrievalEvidenceReason.NO_MATCH
    assert result.hits == ()
    assert result.top_score == 0


def test_evidence_gate_returns_below_threshold_without_hits_for_weak_partial_overlap(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-zeta", filename="zeta-sdf.pdf", pages=("Zeta supplier compliance page",))
    build_retrieval_index(tmp_db_path)

    result = retrieve_evidence(tmp_db_path, "zeta astronomy telescope nebula", top_k=1)

    assert result.is_strong is False
    assert result.reason_code is RetrievalEvidenceReason.BELOW_THRESHOLD
    assert result.hits == ()
    assert result.top_score > 0
    assert result.query_terms == ("zeta", "astronomy", "telescope", "nebula")


def test_hybrid_retriever_diagnostics_do_not_expose_full_page_text(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    secret_tail = " SECRET_FULL_TEXT_TAIL_SHOULD_NOT_APPEAR"
    long_text = "Omega supplier compliance evidence appears near the beginning. " + ("filler words " * 50) + secret_tail
    _seed_doc(tmp_db_path, doc_id="doc-omega", filename="omega-sdf.pdf", pages=(long_text,))
    build_retrieval_index(tmp_db_path)

    result = HybridTextRetriever(tmp_db_path).retrieve("Omega supplier compliance", top_k=1)

    assert result.reason is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert secret_tail not in repr(result)
    assert secret_tail not in result.hits[0].snippet
    assert len(result.hits[0].snippet) <= 222


def test_hybrid_retriever_reports_no_match_for_unrelated_query(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-zeta", filename="zeta-sdf.pdf", pages=("Zeta supplier compliance page",))
    build_retrieval_index(tmp_db_path)

    result = HybridTextRetriever(tmp_db_path).retrieve("astronomy telescope nebula", top_k=1)

    assert result.reason is RetrievalEvidenceReason.NO_MATCH
    assert result.hits == ()
    assert result.top_score == 0


def test_hybrid_query_helpers_are_deterministic_and_safe() -> None:
    assert extract_search_terms('Supplier supplier OR compliance: "Acme"') == ("supplier", "compliance", "acme")
    assert make_fts_query(("supplier", "compliance", "acme")) == '"supplier" OR "compliance" OR "acme"'


def test_retrieval_package_exports_stable_s02_contract_only() -> None:
    from src import retrieval
    from src.retrieval import (  # noqa: PLC0415 - contract import under test
        EvidenceGate,
        EvidenceGateResult,
        RetrievalEvidenceReason,
        RetrievalHit,
        RetrievalIndexStatusReport,
        RetrievalResult,
        RetrievalScoreComponents,
        retrieve_evidence,
    )

    assert EvidenceGate is retrieval.EvidenceGate
    assert EvidenceGateResult is retrieval.EvidenceGateResult
    assert RetrievalEvidenceReason is retrieval.RetrievalEvidenceReason
    assert RetrievalHit is retrieval.RetrievalHit
    assert RetrievalIndexStatusReport is retrieval.RetrievalIndexStatusReport
    assert RetrievalResult is retrieval.RetrievalResult
    assert RetrievalScoreComponents is retrieval.RetrievalScoreComponents
    assert retrieve_evidence is retrieval.retrieve_evidence
    assert "extract_search_terms" not in retrieval.__all__
    assert "make_fts_query" not in retrieval.__all__
    assert "make_query_snippet" not in retrieval.__all__
    assert "HybridTextRetriever" not in retrieval.__all__


def test_hybrid_retriever_uses_deterministic_filename_doc_page_tiebreakers(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    page_text = "Matched supplier compliance approval evidence appears here."
    _seed_doc(tmp_db_path, doc_id="doc-b", filename="b-sdf.pdf", pages=(page_text,))
    _seed_doc(tmp_db_path, doc_id="doc-a", filename="a-sdf.pdf", pages=(page_text, page_text))
    build_retrieval_index(tmp_db_path)

    result = retrieve_evidence(tmp_db_path, "supplier compliance approval", top_k=3)

    assert result.reason_code is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert [(hit.filename, hit.doc_id, hit.page_num, hit.display_page_num) for hit in result.hits] == [
        ("a-sdf.pdf", "doc-a", 0, 1),
        ("a-sdf.pdf", "doc-a", 1, 2),
        ("b-sdf.pdf", "doc-b", 0, 1),
    ]
    assert len({hit.score for hit in result.hits}) == 1


def test_hybrid_retriever_falls_back_to_lexical_when_fts_returns_no_rows(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-theta",
        filename="theta-sdf.pdf",
        pages=("Theta supplier compliance approval evidence is available on this page.",),
    )
    build_retrieval_index(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    try:
        conn.execute("DELETE FROM retrieval_index_page_fts")
        conn.commit()
    finally:
        conn.close()

    result = retrieve_evidence(tmp_db_path, "Theta supplier compliance approval", top_k=1)

    assert result.reason_code is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert result.hits[0].doc_id == "doc-theta"
    assert result.hits[0].score_components.source == "lexical"


def test_hybrid_retriever_query_metacharacters_do_not_raise_or_mutate_schema(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-safe",
        filename="safe-sdf.pdf",
        pages=("Safe supplier compliance approval page remains queryable after hostile syntax.",),
    )
    build_retrieval_index(tmp_db_path)

    result = retrieve_evidence(
        tmp_db_path,
        '" OR supplier) NEAR/0 compliance* ; DROP TABLE documents; -- approval',
        top_k=1,
    )

    assert result.reason_code in {
        RetrievalEvidenceReason.STRONG_EVIDENCE,
        RetrievalEvidenceReason.NO_MATCH,
        RetrievalEvidenceReason.BELOW_THRESHOLD,
    }
    conn = sqlite3.connect(tmp_db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM retrieval_index_pages").fetchone()[0] == 1
    finally:
        conn.close()


def test_hybrid_retriever_normalizes_non_positive_top_k_and_bounds_hits(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-bounds",
        filename="bounds.pdf",
        pages=(
            "Bounds supplier compliance approval evidence on page one.",
            "Bounds supplier compliance approval evidence on page two.",
        ),
    )
    build_retrieval_index(tmp_db_path)

    zero_result = retrieve_evidence(tmp_db_path, "Bounds supplier compliance approval", top_k=0)
    negative_result = retrieve_evidence(tmp_db_path, "Bounds supplier compliance approval", top_k=-10)

    assert zero_result.reason_code is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert negative_result.reason_code is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert len(zero_result.hits) == 1
    assert len(negative_result.hits) == 1
    assert zero_result.hits[0].display_page_num == 1
    assert negative_result.hits[0].display_page_num == 1


def test_evidence_gate_repr_exposes_only_bounded_snippets_and_hash_prefix(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    secret_tail = " API_KEY_SHOULD_NOT_APPEAR_IN_REPR"
    long_text = "Sigma supplier compliance approval evidence is near the beginning. " + ("middle filler " * 80) + secret_tail
    _seed_doc(tmp_db_path, doc_id="doc-sigma", filename="sigma-sdf.pdf", pages=(long_text,))
    built = build_retrieval_index(tmp_db_path)

    result = retrieve_evidence(tmp_db_path, "Sigma supplier compliance approval", top_k=1)
    result_repr = repr(result)
    hit_repr = repr(result.hits[0])

    assert result.reason_code is RetrievalEvidenceReason.STRONG_EVIDENCE
    assert built.run.content_hash not in result_repr
    assert built.run.content_hash[:16] in result_repr
    assert secret_tail not in result_repr
    assert secret_tail not in hit_repr
    assert long_text not in result_repr
    assert long_text not in hit_repr
    assert len(result.hits[0].snippet) <= 222
