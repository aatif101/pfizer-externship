"""Provider-free hybrid text retriever over the persisted SQLite index.

The retriever reads raw page text only inside this module to score and build
short evidence snippets. Public DTOs expose identifiers, scores, score
components, and bounded snippets only.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from src.db.schema import _connect, init_db
from src.retrieval.indexer import get_retrieval_index_status, normalize_index_text
from src.retrieval.models import (
    RetrievalEvidenceReason,
    RetrievalHit,
    RetrievalIndexStatus,
    RetrievalResult,
    RetrievalScoreComponents,
)
from src.retrieval.repository import retrieval_fts_available
from src.tracing import observe, safe_update_current_trace

# Injectable test seams: tests monkeypatch both symbols. langfuse_context=None
# means "resolve the live v3 client lazily inside src.tracing".
_LANGFUSE_AVAILABLE: bool = True
langfuse_context: Any | None = None

_RETRIEVAL_TRACE_ALLOWED_KEYS = frozenset(
    {
        "boundary",
        "run_id",
        "evidence_reason",
        "top_score",
        "citation_count",
        "is_strong",
        "error_class",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_SNIPPET_MAX_CHARS = 220
_SNIPPET_MIN_CHARS = 180
_MAX_EVIDENCE_TEXT_CHARS = 2000
_HASH_PREFIX_CHARS = 16
_DEFAULT_CANDIDATE_LIMIT = 50
DEFAULT_MIN_TOP_SCORE = 0.45
DEFAULT_MIN_QUERY_TERM_COVERAGE = 0.50
DEFAULT_MIN_HIT_COUNT = 1

_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "all",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "com",
        "did",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "of",
        "on",
        "or",
        "page",
        "pages",
        "please",
        "show",
        "tell",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
    }
)


@dataclass(frozen=True)
class _Candidate:
    doc_id: str
    page_num: int
    display_page_num: int
    filename: str
    indexed_snippet: str
    page_text: str
    fts_rank: float | None = None


class HybridTextRetriever:
    """Deterministic hybrid FTS + lexical retriever for indexed SDF pages."""

    def __init__(
        self,
        db_path: str,
        *,
        candidate_limit: int = _DEFAULT_CANDIDATE_LIMIT,
        min_score: float = DEFAULT_MIN_TOP_SCORE,
        min_query_term_coverage: float = DEFAULT_MIN_QUERY_TERM_COVERAGE,
        min_hit_count: int = DEFAULT_MIN_HIT_COUNT,
    ) -> None:
        self.db_path = db_path
        self.candidate_limit = max(1, candidate_limit)
        self.min_score = max(0.0, min_score)
        self.min_query_term_coverage = min(max(0.0, min_query_term_coverage), 1.0)
        self.min_hit_count = max(1, min_hit_count)

    def retrieve(self, question: str, *, top_k: int = 5) -> RetrievalResult:
        """Return citation-ready ranked evidence or a weak-evidence reason code."""

        top_k = max(1, top_k)
        terms = extract_search_terms(question)
        if not terms:
            return self._result(
                RetrievalEvidenceReason.EMPTY_QUESTION,
                is_strong=False,
                hits=(),
                terms=(),
                top_score=0.0,
                run_id=None,
                content_hash=None,
                message="Question did not contain searchable non-stopword terms.",
            )

        try:
            init_db(self.db_path)
            status = get_retrieval_index_status(self.db_path)
            if status.status is RetrievalIndexStatus.MISSING:
                return self._weak_result(RetrievalEvidenceReason.INDEX_MISSING, terms, status.run_id, status.content_hash)
            if status.status is RetrievalIndexStatus.EMPTY:
                return self._weak_result(RetrievalEvidenceReason.INDEX_EMPTY, terms, status.run_id, status.content_hash)
            if status.status is RetrievalIndexStatus.STALE:
                return self._weak_result(RetrievalEvidenceReason.INDEX_STALE, terms, status.run_id, status.content_hash)
            if status.status is not RetrievalIndexStatus.BUILT:
                return self._weak_result(RetrievalEvidenceReason.RETRIEVAL_ERROR, terms, status.run_id, status.content_hash)

            candidates = self._fts_candidates(terms)
            if not candidates:
                candidates = self._lexical_candidates()
            scored = [self._score_candidate(candidate, terms) for candidate in candidates]
            hits = [hit for hit in scored if hit.score > 0.0]
            hits.sort(key=lambda hit: (-hit.score, hit.filename, hit.doc_id, hit.page_num))
            hits = hits[:top_k]
            top_score = hits[0].score if hits else 0.0
            if not hits:
                reason = RetrievalEvidenceReason.NO_MATCH
                strong_hits: tuple[RetrievalHit, ...] = ()
                is_strong = False
            elif top_score < self.min_score:
                reason = RetrievalEvidenceReason.BELOW_THRESHOLD
                strong_hits = ()
                is_strong = False
            elif hits[0].score_components.token_coverage < self.min_query_term_coverage:
                reason = RetrievalEvidenceReason.BELOW_THRESHOLD
                strong_hits = ()
                is_strong = False
            elif len(hits) < self.min_hit_count:
                reason = RetrievalEvidenceReason.BELOW_THRESHOLD
                strong_hits = ()
                is_strong = False
            else:
                reason = RetrievalEvidenceReason.STRONG_EVIDENCE
                strong_hits = tuple(hits)
                is_strong = True
            return self._result(
                reason,
                is_strong=is_strong,
                hits=strong_hits,
                terms=terms,
                top_score=top_score,
                run_id=status.run_id,
                content_hash=status.content_hash,
            )
        except sqlite3.Error as exc:
            return self._result(
                RetrievalEvidenceReason.RETRIEVAL_ERROR,
                is_strong=False,
                hits=(),
                terms=terms,
                top_score=0.0,
                run_id=None,
                content_hash=None,
                message=f"SQLite retrieval failed: {exc.__class__.__name__}",
            )

    def _weak_result(
        self,
        reason: RetrievalEvidenceReason,
        terms: tuple[str, ...],
        run_id: str | None,
        content_hash: str | None,
    ) -> RetrievalResult:
        return self._result(reason, is_strong=False, hits=(), terms=terms, top_score=0.0, run_id=run_id, content_hash=content_hash)

    def _result(
        self,
        reason: RetrievalEvidenceReason,
        *,
        is_strong: bool,
        hits: tuple[RetrievalHit, ...],
        terms: tuple[str, ...],
        top_score: float,
        run_id: str | None,
        content_hash: str | None,
        message: str | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(
            is_strong=is_strong,
            reason_code=reason,
            hits=hits,
            query_terms=terms,
            top_score=top_score,
            run_id=run_id,
            content_hash_prefix=_hash_prefix(content_hash),
            message=message,
        )

    def _fts_candidates(self, terms: tuple[str, ...]) -> list[_Candidate]:
        if not retrieval_fts_available(self.db_path):
            return []
        query = make_fts_query(terms)
        conn = _connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                    f.doc_id,
                    f.page_num,
                    COALESCE(rp.display_page_num, f.page_num + 1) AS display_page_num,
                    rp.filename,
                    rp.snippet,
                    COALESCE(p.page_text, '') AS page_text,
                    bm25(retrieval_index_page_fts) AS fts_rank
                FROM retrieval_index_page_fts f
                JOIN retrieval_index_pages rp
                  ON rp.doc_id = f.doc_id AND rp.page_num = f.page_num
                LEFT JOIN pages p
                  ON p.doc_id = f.doc_id AND p.page_num = f.page_num
                WHERE retrieval_index_page_fts MATCH ?
                ORDER BY fts_rank ASC, rp.filename ASC, f.doc_id ASC, f.page_num ASC
                LIMIT ?
                """,
                (query, self.candidate_limit),
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()
        return [_candidate_from_row(row) for row in rows]

    def _lexical_candidates(self) -> list[_Candidate]:
        conn = _connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                    rp.doc_id,
                    rp.page_num,
                    rp.display_page_num,
                    rp.filename,
                    rp.snippet,
                    COALESCE(p.page_text, '') AS page_text,
                    NULL AS fts_rank
                FROM retrieval_index_pages rp
                LEFT JOIN pages p
                  ON p.doc_id = rp.doc_id AND p.page_num = rp.page_num
                ORDER BY rp.filename ASC, rp.doc_id ASC, rp.page_num ASC
                LIMIT ?
                """,
                (self.candidate_limit,),
            ).fetchall()
        finally:
            conn.close()
        return [_candidate_from_row(row) for row in rows]

    def _score_candidate(self, candidate: _Candidate, terms: tuple[str, ...]) -> RetrievalHit:
        text = normalize_index_text(candidate.page_text) or candidate.indexed_snippet
        lower_text = text.lower()
        counts = {term: lower_text.count(term) for term in terms}
        matched_terms = [term for term, count in counts.items() if count > 0]
        token_coverage = len(matched_terms) / len(terms) if terms else 0.0
        lexical_score = sum(min(counts[term], 3) for term in terms) / max(len(terms), 1)
        phrase_bonus = 0.35 if " ".join(terms) in lower_text else 0.0
        proximity_bonus = _proximity_bonus(lower_text, matched_terms)
        fts_score = _positive_fts_score(candidate.fts_rank)
        source = "fts" if candidate.fts_rank is not None else "lexical"
        components = RetrievalScoreComponents(
            fts_score=round(fts_score, 4),
            lexical_score=round(lexical_score, 4),
            token_coverage=round(token_coverage, 4),
            phrase_bonus=round(phrase_bonus, 4),
            proximity_bonus=round(proximity_bonus, 4),
            source=source,
        )
        score = fts_score + lexical_score + token_coverage + phrase_bonus + proximity_bonus
        return RetrievalHit(
            doc_id=candidate.doc_id,
            filename=candidate.filename,
            page_num=candidate.page_num,
            display_page_num=candidate.display_page_num,
            score=round(score, 4),
            score_components=components,
            snippet=make_query_snippet(text, terms),
            evidence_text=_bounded_evidence_text(candidate.page_text, fallback=candidate.indexed_snippet),
        )


class EvidenceGate(HybridTextRetriever):
    """Named evidence-gate API for callers that should not use raw retrieval directly."""


@observe(name="retrieval_evidence_gate")
def retrieve_evidence(
    db_path: str,
    question: str,
    *,
    top_k: int = 5,
    candidate_limit: int = _DEFAULT_CANDIDATE_LIMIT,
    min_top_score: float = DEFAULT_MIN_TOP_SCORE,
    min_query_term_coverage: float = DEFAULT_MIN_QUERY_TERM_COVERAGE,
    min_hit_count: int = DEFAULT_MIN_HIT_COUNT,
) -> RetrievalResult:
    """Return a deterministic strong/weak evidence decision over the index.

    The gate checks index status before scoring and returns citation-ready hits
    only for ``strong_evidence`` outcomes. Weak outcomes expose diagnostics but
    never fabricate or leak page evidence.
    """

    try:
        result = EvidenceGate(
            db_path,
            candidate_limit=candidate_limit,
            min_score=min_top_score,
            min_query_term_coverage=min_query_term_coverage,
            min_hit_count=min_hit_count,
        ).retrieve(question, top_k=top_k)
    except Exception as exc:
        _safe_update_trace_metadata(
            {
                "boundary": "retrieval_evidence",
                "evidence_reason": RetrievalEvidenceReason.RETRIEVAL_ERROR.value,
                "top_score": 0.0,
                "citation_count": 0,
                "error_class": exc.__class__.__name__,
            }
        )
        raise
    _safe_update_trace_metadata(
        {
            "boundary": "retrieval_evidence",
            "run_id": result.run_id,
            "evidence_reason": result.reason_code.value,
            "top_score": result.top_score,
            "citation_count": len(result.hits),
            "is_strong": result.is_strong,
        }
    )
    return result


def extract_search_terms(question: str) -> tuple[str, ...]:
    """Normalize and de-duplicate searchable question terms deterministically."""

    normalized = normalize_index_text(question).lower()
    terms: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_RE.finditer(normalized):
        term = match.group(0).strip("_-")
        if len(term) < 2 or term in _STOPWORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return tuple(terms)


def make_fts_query(terms: tuple[str, ...]) -> str:
    """Build an FTS5 query from pre-tokenized terms without exposing syntax."""

    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


def make_query_snippet(text: str, terms: tuple[str, ...], *, max_chars: int = _SNIPPET_MAX_CHARS) -> str:
    """Return a bounded verbatim-order snippet centered on the first term hit."""

    normalized = normalize_index_text(text)
    if len(normalized) <= max_chars:
        return normalized
    lower_text = normalized.lower()
    positions = [lower_text.find(term) for term in terms if lower_text.find(term) >= 0]
    if not positions:
        return normalized[:max_chars]
    anchor = min(positions)
    half_window = max(_SNIPPET_MIN_CHARS // 2, max_chars // 2)
    start = max(0, anchor - half_window)
    end = min(len(normalized), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    snippet = normalized[start:end].strip()
    if start > 0:
        snippet = "…" + snippet.lstrip()
    if end < len(normalized):
        snippet = snippet.rstrip() + "…"
    return snippet


def _bounded_evidence_text(text: str, *, fallback: str, max_chars: int = _MAX_EVIDENCE_TEXT_CHARS) -> str:
    """Return bounded grounding text from full page text with word-boundary truncation.

    The full page text is normalized first. If it is empty/whitespace after
    normalization, the indexed snippet is used as the (normalized) fallback so
    scanned/empty pages still yield non-empty grounding. Text at/under the cap is
    returned verbatim; longer text is truncated at the last whitespace boundary
    at/under the cap (never mid-word) with a trailing ellipsis. A single token
    longer than the cap is hard-sliced as a last resort.
    """

    normalized = normalize_index_text(text)
    if not normalized.strip():
        return normalize_index_text(fallback)
    if len(normalized) <= max_chars:
        return normalized
    head = normalized[:max_chars]
    if " " in head:
        head = head.rsplit(" ", 1)[0]
    return head.rstrip() + "…"


def _hash_prefix(content_hash: str | None) -> str | None:
    if not content_hash:
        return None
    return content_hash[:_HASH_PREFIX_CHARS]


def _candidate_from_row(row: sqlite3.Row) -> _Candidate:
    return _Candidate(
        doc_id=row["doc_id"],
        page_num=int(row["page_num"]),
        display_page_num=int(row["display_page_num"]),
        filename=row["filename"],
        indexed_snippet=row["snippet"] or "",
        page_text=row["page_text"] or "",
        fts_rank=float(row["fts_rank"]) if row["fts_rank"] is not None else None,
    )


def _positive_fts_score(fts_rank: float | None) -> float:
    if fts_rank is None:
        return 0.0
    if fts_rank < 0:
        return min(abs(fts_rank), 5.0)
    return 1.0 / (1.0 + fts_rank)


def _proximity_bonus(lower_text: str, matched_terms: list[str]) -> float:
    if len(matched_terms) < 2:
        return 0.0
    positions = [lower_text.find(term) for term in matched_terms]
    positions = [position for position in positions if position >= 0]
    if len(positions) < 2:
        return 0.0
    span = max(positions) - min(positions)
    if span <= 40:
        return 0.25
    if span <= 120:
        return 0.1
    return 0.0


def _safe_update_trace_metadata(metadata: dict[str, Any]) -> None:
    """Attach whitelisted retrieval metadata without affecting retrieval behavior."""

    if not _LANGFUSE_AVAILABLE:
        return
    safe_update_current_trace(
        tags=["retrieval", "evidence"],
        metadata=metadata,
        allowed_metadata_keys=_RETRIEVAL_TRACE_ALLOWED_KEYS,
        context=langfuse_context,
    )
