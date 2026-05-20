"""Typed DTOs for the persisted retrieval index boundary.

These models intentionally expose page metadata, hashes, and display page
numbers, but not raw page text. The repository owns raw text handoff to SQLite
FTS so callers cannot accidentally log indexed page contents.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RetrievalIndexStatus(StrEnum):
    """Persisted index run states surfaced by future CLI/status commands."""

    BUILT = "built"
    EMPTY = "empty"
    MISSING = "missing"
    STALE = "stale"
    ERROR = "error"


class RetrievalEvidenceReason(StrEnum):
    """Reason-coded query outcomes for deterministic evidence gating."""

    STRONG_EVIDENCE = "strong_evidence"
    EMPTY_QUESTION = "empty_question"
    INDEX_MISSING = "index_missing"
    INDEX_EMPTY = "index_empty"
    INDEX_STALE = "index_stale"
    NO_MATCH = "no_match"
    BELOW_THRESHOLD = "below_threshold"
    RETRIEVAL_ERROR = "retrieval_error"


@dataclass(frozen=True)
class CorpusFingerprint:
    """Stable summary of the source corpus used to decide freshness."""

    document_count: int
    page_count: int
    content_hash: str


@dataclass(frozen=True)
class RetrievalIndexRun:
    """Inspectable metadata for one retrieval index build/status run."""

    run_id: str
    status: RetrievalIndexStatus
    built_at: str | None
    source_document_count: int
    source_page_count: int
    indexed_page_count: int
    content_hash: str | None = None
    previous_content_hash: str | None = None
    is_stale: bool = False
    stale_reason: str | None = None
    error_reason: str | None = None


@dataclass(frozen=True)
class PageIndexInput:
    """Raw page text input accepted only at the repository boundary."""

    doc_id: str
    page_num: int
    filename: str
    page_text: str | None


@dataclass(frozen=True)
class RetrievalIndexPageRecord:
    """Persisted page-level retrieval metadata without raw page text."""

    doc_id: str
    page_num: int
    display_page_num: int
    filename: str
    text_sha256: str
    text_length: int
    snippet: str
    run_id: str
    indexed_at: str | None


@dataclass(frozen=True)
class RetrievalIndexStatusReport:
    """Safe diagnostic view of the current source corpus versus persisted index state."""

    status: RetrievalIndexStatus
    run_id: str | None
    source_document_count: int
    source_page_count: int
    indexed_page_count: int
    content_hash: str | None
    previous_content_hash: str | None = None
    is_stale: bool = False
    stale_reason: str | None = None
    error_reason: str | None = None


@dataclass(frozen=True)
class RetrievalScoreComponents:
    """Compact inspectable scoring factors for one retrieval hit."""

    fts_score: float = 0.0
    lexical_score: float = 0.0
    token_coverage: float = 0.0
    phrase_bonus: float = 0.0
    proximity_bonus: float = 0.0
    source: str = "lexical"


@dataclass(frozen=True)
class RetrievalHit:
    """Citation-ready page evidence without raw full page text."""

    doc_id: str
    filename: str
    page_num: int
    display_page_num: int
    score: float
    score_components: RetrievalScoreComponents
    snippet: str


@dataclass(frozen=True)
class RetrievalResult:
    """Reason-coded safe retrieval response for a user question."""

    reason: RetrievalEvidenceReason
    hits: tuple[RetrievalHit, ...]
    query_terms: tuple[str, ...]
    top_score: float
    run_id: str | None
    content_hash: str | None
    message: str | None = None
