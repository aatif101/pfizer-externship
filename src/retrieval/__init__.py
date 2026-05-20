"""Retrieval index persistence package."""

from src.retrieval.models import (
    CorpusFingerprint,
    EvidenceGateResult,
    PageIndexInput,
    RetrievalEvidenceReason,
    RetrievalHit,
    RetrievalIndexPageRecord,
    RetrievalIndexRun,
    RetrievalIndexStatus,
    RetrievalIndexStatusReport,
    RetrievalResult,
    RetrievalScoreComponents,
)
from src.retrieval.retriever import EvidenceGate, retrieve_evidence
from src.retrieval.repository import (
    compute_corpus_fingerprint,
    list_page_index_records,
    load_latest_index_run,
    retrieval_fts_available,
    save_index_run,
    upsert_page_index_records,
)

__all__ = [
    "CorpusFingerprint",
    "EvidenceGate",
    "EvidenceGateResult",
    "PageIndexInput",
    "RetrievalEvidenceReason",
    "RetrievalHit",
    "RetrievalIndexPageRecord",
    "RetrievalIndexRun",
    "RetrievalIndexStatus",
    "RetrievalIndexStatusReport",
    "RetrievalResult",
    "RetrievalScoreComponents",
    "compute_corpus_fingerprint",
    "list_page_index_records",
    "load_latest_index_run",
    "retrieval_fts_available",
    "retrieve_evidence",
    "save_index_run",
    "upsert_page_index_records",
]
