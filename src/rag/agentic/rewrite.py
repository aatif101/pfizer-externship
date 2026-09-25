"""Progress-guarded query rewriting for weak retrieval rounds (RAG-03).

Candidate order: deterministic pharma-domain synonym expansion first, then (only
when configured) an LLM keyword rewrite. A candidate equal to any already-tried
query (case- and whitespace-insensitive) is no progress, so the loop terminates
monotonically (T-06-24). Never raises.

Pure module: no graph framework or model SDK imports.
"""
from __future__ import annotations

import re
from typing import Callable, Collection

from src.retrieval.retriever import _TOKEN_RE

__all__ = [
    "DOMAIN_SYNONYMS",
    "build_rewrite_prompt",
    "expand_with_synonyms",
    "parse_llm_rewrite",
    "rewrite_query",
]

MIN_REWRITE_CHARS = 3
MAX_REWRITE_CHARS = 200

_EXPIRY_SYNONYMS: tuple[str, ...] = ("expiration", "use by", "valid until", "expiry date")

# Lower-case token -> synonyms appended when the token appears in the query.
DOMAIN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "expiry": _EXPIRY_SYNONYMS,
    "expire": ("expiry",) + _EXPIRY_SYNONYMS,
    "expires": ("expiry",) + _EXPIRY_SYNONYMS,
    "expired": ("expiry",) + _EXPIRY_SYNONYMS,
    "expiration": ("expiry", "use by", "valid until", "expiry date"),
    "manufacturing": ("mfg", "date of manufacture", "production", "manufactured"),
    "coa": ("certificate of analysis",),
    "coq": ("certificate of quality",),
    "revision": ("rev", "version", "revised"),
    "vendor": ("supplier", "manufacturer"),
    "effective": ("effective date", "valid from"),
}

_FENCE_RE = re.compile(r"^```(?:[a-zA-Z0-9_-]+)?\s*|\s*```$")
_QUOTE_CHARS = "\"'`“”‘’"


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def expand_with_synonyms(query: str) -> str | None:
    """Append domain synonyms for recognised tokens; None when nothing new is added."""

    text = " ".join((query or "").split())
    if not text:
        return None
    tokens = {token.lower() for token in _TOKEN_RE.findall(text)}
    additions: list[str] = []
    for key, synonyms in DOMAIN_SYNONYMS.items():
        if key not in tokens:
            continue
        for synonym in synonyms:
            candidate = " ".join([text, *additions])
            if not _contains_phrase(candidate, synonym):
                additions.append(synonym)
    if not additions:
        return None
    return " ".join([text, *additions])


def build_rewrite_prompt(query: str) -> str:
    """Prompt asking for a single keyword-style search query line."""

    return (
        "Rewrite the search query below as ONE keyword-style search query for a pharmaceutical "
        "supplier-document index (certificates of analysis, vendor certificates, compliance forms). "
        "Use domain synonyms where helpful. Reply with the query line only, no prose.\n\n"
        f"Query: {query}"
    )


def parse_llm_rewrite(text: str) -> str | None:
    """First non-empty line of the LLM output, unquoted and length-bounded; else None."""

    try:
        if not isinstance(text, str):
            return None
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = _FENCE_RE.sub("", stripped).strip()
        for line in stripped.splitlines():
            candidate = " ".join(line.strip().strip(_QUOTE_CHARS).split())
            if not candidate:
                continue
            if MIN_REWRITE_CHARS <= len(candidate) <= MAX_REWRITE_CHARS:
                return candidate
            return None
        return None
    except Exception:  # noqa: BLE001
        return None


def _strip_prompt_echo(raw: str, prompt: str) -> str:
    """Drop a verbatim echo of the prompt; an echo alone is no progress."""

    stripped = raw.strip()
    prompt_stripped = prompt.strip()
    if prompt_stripped and stripped.startswith(prompt_stripped):
        return stripped[len(prompt_stripped):]
    return raw


def rewrite_query(
    query: str,
    *,
    tried: Collection[str],
    llm: Callable[[str], str] | None = None,
) -> tuple[str | None, str]:
    """Return ``(new_query, method)``; method is synonyms, llm, or exhausted. Never raises."""

    try:
        seen = {_normalize(item) for item in tried if isinstance(item, str)}
        seen.add(_normalize(query or ""))

        expanded = expand_with_synonyms(query)
        if expanded is not None and _normalize(expanded) not in seen:
            return expanded, "synonyms"

        if llm is not None:
            prompt = build_rewrite_prompt(query)
            try:
                raw = llm(prompt)
            except Exception:  # noqa: BLE001 - a failed rewrite is "no progress", not a crash.
                return None, "exhausted"
            if not isinstance(raw, str):
                return None, "exhausted"
            candidate = parse_llm_rewrite(_strip_prompt_echo(raw, prompt))
            if candidate is not None and _normalize(candidate) not in seen:
                return candidate, "llm"
    except Exception:  # noqa: BLE001
        return None, "exhausted"
    return None, "exhausted"
