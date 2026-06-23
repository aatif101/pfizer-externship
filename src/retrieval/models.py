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
    """Compact inspectable scoring factors for one retrieval hit.

    ``source`` records which retrieval tier produced the hit and is one of
    ``{"lexical", "fts", "visual", "fused"}``:

    - ``"lexical"`` / ``"fts"`` — text tier (lexical fallback or FTS5 BM25).
    - ``"visual"`` — page came only from the ColQwen2.5 visual tier.
    - ``"fused"`` — page appeared in both tiers and was RRF-fused.

    The field stays a free ``str`` (no enum); the set above is documentation
    only, so existing text-tier construction is unaffected.
    """

    fts_score: float = 0.0
    lexical_score: float = 0.0
    token_coverage: float = 0.0
    phrase_bonus: float = 0.0
    proximity_bonus: float = 0.0
    source: str = "lexical"


@dataclass(frozen=True)
class RetrievalHit:
    """Citation-ready page evidence with bounded in-memory evidence text.

    ``snippet`` stays the short, dashboard-facing teaser (<=222 chars).
    ``evidence_text`` is a wider, bounded slice of the full page text used only
    in memory by the generator prompt and the RAGAS faithfulness judge; it is
    never persisted nor added to any trace allowlist.
    """

    doc_id: str
    filename: str
    page_num: int
    display_page_num: int
    score: float
    score_components: RetrievalScoreComponents
    snippet: str
    evidence_text: str = ""


@dataclass(frozen=True)
class EvidenceGateResult:
    """Reason-coded safe evidence decision for a user question.

    The gate exposes bounded citation-ready hits only when evidence is strong.
    Hash metadata is truncated for public diagnostics; raw page text and full
    corpus hashes remain confined to the index/retriever internals.
    """

    is_strong: bool
    reason_code: RetrievalEvidenceReason
    hits: tuple[RetrievalHit, ...]
    top_score: float
    query_terms: tuple[str, ...]
    run_id: str | None
    content_hash_prefix: str | None = None
    message: str | None = None

    @property
    def reason(self) -> RetrievalEvidenceReason:
        """Backward-compatible alias for earlier retriever callers/tests."""

        return self.reason_code

    @property
    def content_hash(self) -> str | None:
        """Backward-compatible safe hash metadata alias.

        This intentionally returns the public prefix, not the full corpus hash.
        """

        return self.content_hash_prefix


RetrievalResult = EvidenceGateResult
