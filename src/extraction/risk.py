"""Pure compliance risk helpers for SDF extraction records.

The policy is intentionally conservative: uncertain or malformed relevant dates do
not raise and do not get treated as safe. Callers can persist the returned values
onto ``SDFExtractionRecord`` before repository upsert.

Per ``docs/field-definitions.md``, a printed "N/A" expiry is a real asserted value
meaning "no expiry" (it is extracted as the literal string "N/A", not abstained).
For risk scoring, such not-applicable markers on a date field are therefore treated
as "no date present" rather than an ambiguous/invalid date error: a document with a
printed-N/A expiry is not at-risk on expiry, and risk falls through to age-based
scoring on the manufacturing/effective/revision dates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName


@dataclass(frozen=True)
class RiskMetadata:
    """Dashboard-ready document risk metadata."""

    risk_level: str
    risk_reason: str
    compliance_status: str
    age_days: int | None


_DATE_FIELDS_FOR_AGE: tuple[SDFFieldName, ...] = (
    SDFFieldName.MANUFACTURING_DATE,
    SDFFieldName.EFFECTIVE_DATE,
    SDFFieldName.REVISION_DATE,
)

# Printed "not-applicable" markers (per docs/field-definitions.md). On a date field
# these are real asserted values meaning "no date / no expiry", not invalid dates.
_NOT_APPLICABLE_DATE_MARKERS: frozenset[str] = frozenset(
    {"n/a", "n.a.", "na", "not applicable"}
)


def compute_record_risk(record: SDFExtractionRecord, *, today: date) -> RiskMetadata:
    """Compute conservative risk metadata for a validated extraction record."""

    return compute_fields_risk(record.fields, today=today)


def compute_fields_risk(fields: Mapping[SDFFieldName, ExtractedField], *, today: date) -> RiskMetadata:
    """Compute conservative risk metadata from validated SDF extraction fields.

    Policy:
    - A usable expiry date before ``today`` is red/at-risk.
    - If expiry is not expired, compute age from the oldest usable
      manufacturing/effective/revision date.
    - Age under two years is green; two to three years is amber; over three
      years is red.
    - Missing, abstained, or ambiguous relevant dates produce unknown/needs_review
      when no safe risk can be computed.
    """

    expiry_value = _field_date(fields.get(SDFFieldName.EXPIRY_DATE))
    if expiry_value.error:
        return _needs_review(expiry_value.reason)
    if expiry_value.value is not None and expiry_value.value < today:
        return RiskMetadata(
            risk_level="red",
            risk_reason=f"Expiry date {expiry_value.value.isoformat()} is before {today.isoformat()}.",
            compliance_status="at_risk",
            age_days=None,
        )

    age_dates: list[date] = []
    invalid_reasons: list[str] = []
    for field_name in _DATE_FIELDS_FOR_AGE:
        parsed = _field_date(fields.get(field_name))
        if parsed.error:
            invalid_reasons.append(parsed.reason)
        elif parsed.value is not None:
            age_dates.append(parsed.value)

    if invalid_reasons:
        return _needs_review("; ".join(invalid_reasons))
    if not age_dates:
        return _needs_review("No usable manufacturing, effective, or revision date was extracted for age-based risk scoring.")

    oldest_date = min(age_dates)
    age_days = (today - oldest_date).days
    if age_days < 0:
        return _needs_review(f"Oldest relevant date {oldest_date.isoformat()} is after {today.isoformat()}.")

    two_year_cutoff = _subtract_years(today, 2)
    three_year_cutoff = _subtract_years(today, 3)

    if oldest_date > two_year_cutoff:
        return RiskMetadata(
            risk_level="green",
            risk_reason=f"Oldest relevant date {oldest_date.isoformat()} is {age_days} days old, under the 2-year threshold.",
            compliance_status="compliant",
            age_days=age_days,
        )
    if oldest_date >= three_year_cutoff:
        return RiskMetadata(
            risk_level="amber",
            risk_reason=f"Oldest relevant date {oldest_date.isoformat()} is {age_days} days old, between 2 and 3 years.",
            compliance_status="needs_review",
            age_days=age_days,
        )
    return RiskMetadata(
        risk_level="red",
        risk_reason=f"Oldest relevant date {oldest_date.isoformat()} is {age_days} days old, over the 3-year threshold.",
        compliance_status="at_risk",
        age_days=age_days,
    )


@dataclass(frozen=True)
class _ParsedDate:
    value: date | None
    error: bool
    reason: str


def _field_date(field: ExtractedField | None) -> _ParsedDate:
    if field is None:
        return _ParsedDate(None, False, "")
    if field.review_state == ReviewState.ABSTAINED:
        return _ParsedDate(None, False, "")

    candidate = field.normalized_date if field.normalized_date is not None else field.normalized_value
    if candidate is None:
        candidate = field.raw_value
    if candidate is None:
        return _ParsedDate(None, False, "")

    # A printed "N/A" (or equivalent) marker is a real "no date present" assertion,
    # not an ambiguous/invalid date. Treat it as absent rather than an error so the
    # document is not parked at risk_level='unknown'. See module docstring and
    # docs/field-definitions.md (expiry_date rules).
    if isinstance(candidate, str) and candidate.strip().casefold() in _NOT_APPLICABLE_DATE_MARKERS:
        return _ParsedDate(None, False, "")

    parsed = _parse_date(candidate)
    if parsed is None:
        return _ParsedDate(
            None,
            True,
            f"{field.field_name.value} has an ambiguous or invalid date value: {candidate!r}.",
        )
    return _ParsedDate(parsed, False, "")


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return date.fromisoformat(stripped)
        except ValueError:
            return None
    return None


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        # Feb 29 has no equivalent in non-leap years; Feb 28 is the conservative
        # anniversary cutoff for calendar-year document age thresholds.
        return value.replace(year=value.year - years, day=28)


def _needs_review(reason: str) -> RiskMetadata:
    return RiskMetadata(
        risk_level="unknown",
        risk_reason=reason,
        compliance_status="needs_review",
        age_days=None,
    )
