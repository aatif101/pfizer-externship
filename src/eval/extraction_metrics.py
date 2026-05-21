"""Extraction evaluation metrics.

This module is intentionally provider/LLM-free. It computes deterministic,
field-level precision/recall/F1 from gold labels vs predicted extractions.

Matching strategy
-----------------
Scores are computed per (doc_id, field_name) using *exact match* after
normalization.

Classification rules per gold instance (doc_id, field_name)
-----------------------------------------------------------
Let ``gold_norm`` be the normalized expected value from gold labels and
``pred_norm`` be the normalized predicted value (or ``None`` when abstained /
missing).

- If ``gold_norm`` is not ``None`` and ``pred_norm == gold_norm`` -> TP
- If ``gold_norm`` is not ``None`` and ``pred_norm is None`` -> FN
- If ``gold_norm`` is not ``None`` and ``pred_norm`` is not ``None`` but differs
  -> FP + FN (a wrong answer *and* a missed correct answer)
- If ``gold_norm`` is ``None`` -> skip (not counted)

Notes:
- We only score fields that appear in gold labels. Extra predicted fields are
  ignored here (they are out-of-scope for this slice's definition).
- Macro-averages are computed across fields with at least one gold instance.

"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass


_WHITESPACE_RE = re.compile(r"\s+")


def _clean_string(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip())


_DATE_FIELD_TOKENS: tuple[str, ...] = (
    "manufacturing",
    "manufacture",
    "mfg",
    "effective",
    "revision",
    "rev",
    "expiry",
    "expiration",
    "expire",
)


def _looks_date_like_field(field_name: str) -> bool:
    lowered = field_name.casefold()
    return any(token in lowered for token in _DATE_FIELD_TOKENS)


def normalize_extracted_value(field_name: str, value: str | None) -> str | None:
    """Normalize an extracted (or gold) value for deterministic evaluation.

    Rules:
    - ``None`` stays ``None``
    - Trim whitespace + collapse internal whitespace to single spaces
    - Casefold (lower) for general string fields
    - For date-like fields (manufacturing/effective/revision/expiry), attempt
      best-effort parsing into ISO ``YYYY-MM-DD`` (via python-dateutil when
      available). If parsing fails, fall back to the cleaned string.

    This function is deterministic and side-effect-free.
    """

    if value is None:
        return None

    cleaned = _clean_string(str(value))
    if cleaned == "":
        return None

    if _looks_date_like_field(field_name):
        try:
            from dateutil import parser as date_parser  # type: ignore

            parsed = date_parser.parse(cleaned, fuzzy=True)
            return parsed.date().isoformat()
        except Exception:
            # Fall back to cleaned string for robustness (still casefolded).
            return cleaned.casefold()

    return cleaned.casefold()


@dataclass(frozen=True)
class FieldScore:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


def _safe_div(numer: int, denom: int) -> float:
    return float(numer) / float(denom) if denom else 0.0


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def compute_extraction_field_scores(
    gold_rows: list[dict],
    pred_rows: list[dict],
) -> dict[str, FieldScore]:
    """Compute per-field TP/FP/FN and precision/recall/F1.

    Input row shapes (dict-like):
    - gold_rows items must have: doc_id, field_name, expected_value OR normalized_value
    - pred_rows items must have: doc_id, field_name, normalized_value, review_state

    Predictions are treated as ``None`` when:
    - ``normalized_value`` is missing/None/blank
    - review_state indicates abstention ("abstained", case-insensitive)

    Returns a deterministic mapping keyed by ``field_name``.
    """

    pred_by_key: dict[tuple[str, str], str | None] = {}
    for row in pred_rows:
        doc_id = str(row.get("doc_id"))
        field_name = str(row.get("field_name"))
        review_state = (row.get("review_state") or "").__str__()

        pred_norm: str | None
        if review_state.casefold() == "abstained":
            pred_norm = None
        else:
            raw_pred = row.get("normalized_value")
            pred_norm = normalize_extracted_value(field_name, raw_pred)

        pred_by_key[(doc_id, field_name)] = pred_norm

    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    for row in gold_rows:
        doc_id = str(row.get("doc_id"))
        field_name = str(row.get("field_name"))

        gold_value = row.get("normalized_value")
        if gold_value is None:
            gold_value = row.get("expected_value")
        gold_norm = normalize_extracted_value(field_name, gold_value)

        if gold_norm is None:
            continue

        pred_norm = pred_by_key.get((doc_id, field_name))

        if pred_norm == gold_norm:
            counts[field_name]["tp"] += 1
        elif pred_norm is None:
            counts[field_name]["fn"] += 1
        else:
            counts[field_name]["fp"] += 1
            counts[field_name]["fn"] += 1

    out: dict[str, FieldScore] = {}
    for field_name in sorted(counts.keys()):
        tp = counts[field_name]["tp"]
        fp = counts[field_name]["fp"]
        fn = counts[field_name]["fn"]
        precision, recall, f1 = _prf(tp, fp, fn)
        out[field_name] = FieldScore(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)

    return out


def compute_macro_averages(per_field_scores: dict[str, FieldScore]) -> dict[str, float]:
    """Compute macro-averaged precision/recall/F1 across fields.

    Fields with zero gold instances are not included (those fields would not be
    present in ``per_field_scores``).
    """

    if not per_field_scores:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    precision = sum(s.precision for s in per_field_scores.values()) / len(per_field_scores)
    recall = sum(s.recall for s in per_field_scores.values()) / len(per_field_scores)
    f1 = sum(s.f1 for s in per_field_scores.values()) / len(per_field_scores)
    return {"precision": precision, "recall": recall, "f1": f1}
