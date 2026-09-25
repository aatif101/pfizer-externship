"""Deterministic-first question decomposition for the agentic RAG graph (RAG-03).

Single-intent questions are never decomposed and never trigger an LLM call
(protects the free-tier Gemini quota). Compound questions are split by a
deterministic heuristic; an optional LLM decomposer may refine the split, but
malformed LLM output always falls back to the heuristic result. Output is
bounded by ``MAX_SUB_QUERIES`` and a per-item length cap (T-06-23).

Pure module: no graph framework or model SDK imports.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from src.rag.agentic.state import MAX_SUB_QUERIES
from src.retrieval.retriever import _STOPWORDS, _TOKEN_RE

__all__ = [
    "FIELD_MENTIONS",
    "build_decompose_prompt",
    "decompose_question",
    "heuristic_split",
    "is_compound",
    "parse_llm_subqueries",
]

MAX_SUB_QUERY_CHARS = 200

# SDFFieldName value -> surface phrases that signal the field is being asked about.
# doc_type deliberately excludes bare "coa"/"coq"/"certificate": those words are
# usually the *subject* of a question ("expiry date of the Sigma CoA"), not a
# request for the document type, and counting them would decompose single-intent
# questions.
FIELD_MENTIONS: dict[str, tuple[str, ...]] = {
    "expiry_date": ("expiry", "expiration", "expire", "valid until", "use by"),
    "manufacturing_date": ("manufacturing", "manufactured", "mfg", "date of manufacture", "production"),
    "effective_date": ("effective",),
    "revision_date": ("revision", "rev", "version", "revised"),
    "vendor_name": ("vendor", "supplier", "manufacturer"),
    "doc_type": ("document type", "type of document", "doc type"),
}

# Canonical retrieval phrase emitted per field when splitting by field mention.
_FIELD_QUERY_PHRASE: dict[str, str] = {
    "expiry_date": "expiry date",
    "manufacturing_date": "manufacturing date",
    "effective_date": "effective date",
    "revision_date": "revision date",
    "vendor_name": "vendor",
    "doc_type": "document type",
}

_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    field: re.compile(
        r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(phrase) for phrase in phrases) + r")(?:s|d)?(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    for field, phrases in FIELD_MENTIONS.items()
}

_FIELD_WORDS: frozenset[str] = frozenset(
    word for phrases in FIELD_MENTIONS.values() for phrase in phrases for word in phrase.lower().split()
)
_GENERIC_WORDS: frozenset[str] = frozenset(
    {"date", "dates", "name", "names", "both", "each", "compare", "comparison", "vs", "versus", "and", "type"}
)
_COMPARISON_RE = re.compile(r"\s+(?:vs\.?|versus|and)\s+", re.IGNORECASE)
_COMPARISON_SIGNAL_RE = re.compile(r"(?<![A-Za-z0-9])(?:vs\.?|versus|compare[ds]?|comparing)(?![A-Za-z0-9])", re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:[a-zA-Z0-9_-]+)?\s*|\s*```$")


def _mentioned_fields(question: str) -> list[str]:
    """Return mentioned SDF fields ordered by first appearance in the question."""

    positions: list[tuple[int, str]] = []
    for field, pattern in _FIELD_PATTERNS.items():
        match = pattern.search(question)
        if match is not None:
            positions.append((match.start(), field))
    return [field for _, field in sorted(positions)]


def _is_comparison(question: str) -> bool:
    return bool(_COMPARISON_SIGNAL_RE.search(question))


def is_compound(question: str) -> bool:
    """True when the question carries more than one information need."""

    text = (question or "").strip()
    if not text:
        return False
    if text.count("?") >= 2:
        return True
    if _is_comparison(text):
        return True
    return len(_mentioned_fields(text)) >= 2


def _dedupe_cap(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        cleaned = " ".join(part.split())
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= MAX_SUB_QUERIES:
            break
    return result


def _subject_tokens(question: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(question):
        lowered = token.lower()
        if lowered in _STOPWORDS or lowered in _FIELD_WORDS or lowered in _GENERIC_WORDS:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        tokens.append(token)
    return tokens


def heuristic_split(question: str) -> list[str]:
    """Deterministically split a compound question; never empty, capped at MAX_SUB_QUERIES."""

    text = (question or "").strip()
    parts: list[str] = []
    if text.count("?") >= 2:
        parts = [segment.strip() for segment in re.findall(r"[^?]*\?|[^?]+$", text)]
    elif _is_comparison(text):
        parts = [segment.strip(" ,.;:") for segment in _COMPARISON_RE.split(text)]
    else:
        fields = _mentioned_fields(text)
        if len(fields) >= 2:
            subject = " ".join(_subject_tokens(text))
            parts = [f"{_FIELD_QUERY_PHRASE[field]} {subject}".strip() for field in fields]
    result = _dedupe_cap(parts)
    if len(result) < 2:
        return [text]
    return result


def build_decompose_prompt(question: str) -> str:
    """Prompt asking for a bare JSON array of short keyword search queries."""

    return (
        "Split the question below into short keyword search queries for a pharmaceutical "
        "supplier-document index (certificates of analysis, vendor certificates, compliance forms).\n"
        f"Return ONLY a JSON array of at most {MAX_SUB_QUERIES} strings, one per distinct "
        "information need. No prose, no explanation.\n\n"
        f"Question: {question}"
    )


def parse_llm_subqueries(text: str) -> list[str] | None:
    """Parse the decomposer's JSON array; None on any malformed or unbounded output."""

    try:
        if not isinstance(text, str):
            return None
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = _FENCE_RE.sub("", stripped).strip()
        data = json.loads(stripped)
        if not isinstance(data, list):
            return None
        items: list[str] = []
        for item in data:
            if not isinstance(item, str):
                return None
            cleaned = item.strip()
            if not cleaned:
                continue
            if len(cleaned) > MAX_SUB_QUERY_CHARS:
                return None
            items.append(cleaned)
        result = _dedupe_cap(items)
        return result or None
    except Exception:  # noqa: BLE001 - any parse failure means "use the heuristic".
        return None


def decompose_question(
    question: str,
    *,
    llm: Callable[[str], str] | None = None,
) -> tuple[list[str], str]:
    """Return ``(sub_queries, method)`` with method in single/heuristic/llm/llm_fallback. Never raises."""

    text = (question or "").strip()
    try:
        compound = is_compound(text)
    except Exception:  # noqa: BLE001 - defensive: decomposition must never abort the graph.
        compound = False
    if not compound:
        return [text], "single"
    try:
        heuristic = heuristic_split(text)
    except Exception:  # noqa: BLE001
        heuristic = [text]
    if llm is None:
        return heuristic, "heuristic"
    try:
        parsed = parse_llm_subqueries(llm(build_decompose_prompt(text)))
    except Exception:  # noqa: BLE001 - an LLM failure falls back, never abstains.
        parsed = None
    if parsed is None:
        return heuristic, "llm_fallback"
    return parsed, "llm"
