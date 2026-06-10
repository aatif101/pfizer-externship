"""Tests for conservative SDF document risk scoring."""
from __future__ import annotations

from datetime import date

from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
from src.extraction.risk import compute_fields_risk, compute_record_risk


def make_field(
    field_name: SDFFieldName,
    value: str | None,
    *,
    normalized_date: date | None = None,
    review_state: ReviewState = ReviewState.PENDING,
    abstention_reason: str | None = None,
) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        raw_value=value,
        normalized_value=value,
        normalized_date=normalized_date,
        confidence=0.9 if value else 0.0,
        evidence=SourceEvidence(page_num=0, verbatim_span=value),
        review_state=review_state,
        abstention_reason=abstention_reason,
    )


def make_fields(
    *,
    manufacturing_date: date | str | None = date(2024, 1, 1),
    effective_date: date | str | None = None,
    revision_date: date | str | None = None,
    expiry_date: date | str | None = date(2027, 1, 1),
) -> dict[SDFFieldName, ExtractedField]:
    fields = {
        SDFFieldName.DOC_TYPE: make_field(SDFFieldName.DOC_TYPE, "SDF"),
        SDFFieldName.VENDOR_NAME: make_field(SDFFieldName.VENDOR_NAME, "Acme Pharma"),
    }
    for field_name, value in {
        SDFFieldName.MANUFACTURING_DATE: manufacturing_date,
        SDFFieldName.EFFECTIVE_DATE: effective_date,
        SDFFieldName.REVISION_DATE: revision_date,
        SDFFieldName.EXPIRY_DATE: expiry_date,
    }.items():
        if value is None:
            fields[field_name] = make_field(
                field_name,
                None,
                review_state=ReviewState.ABSTAINED,
                abstention_reason=f"{field_name.value} not present.",
            )
        elif isinstance(value, date):
            fields[field_name] = make_field(field_name, value.isoformat(), normalized_date=value)
        else:
            fields[field_name] = make_field(field_name, value)
    return fields


def test_expired_expiry_date_is_red_without_age() -> None:
    risk = compute_fields_risk(make_fields(expiry_date=date(2026, 1, 31)), today=date(2026, 2, 1))

    assert risk.risk_level == "red"
    assert risk.compliance_status == "at_risk"
    assert risk.age_days is None
    assert "Expiry date 2026-01-31" in risk.risk_reason


def test_under_two_years_old_is_green() -> None:
    risk = compute_fields_risk(make_fields(manufacturing_date=date(2024, 1, 2)), today=date(2026, 1, 1))

    assert risk.risk_level == "green"
    assert risk.compliance_status == "compliant"
    assert risk.age_days == 730


def test_two_to_three_year_threshold_is_amber() -> None:
    risk = compute_fields_risk(make_fields(manufacturing_date=date(2024, 1, 1)), today=date(2026, 1, 1))

    assert risk.risk_level == "amber"
    assert risk.compliance_status == "needs_review"
    assert risk.age_days == 731


def test_over_three_year_threshold_is_red() -> None:
    risk = compute_fields_risk(make_fields(manufacturing_date=date(2022, 12, 31)), today=date(2026, 1, 1))

    assert risk.risk_level == "red"
    assert risk.compliance_status == "at_risk"
    assert risk.age_days == 1097


def test_oldest_available_manufacturing_effective_or_revision_date_sets_age() -> None:
    risk = compute_fields_risk(
        make_fields(
            manufacturing_date=None,
            effective_date=date(2024, 6, 1),
            revision_date=date(2024, 3, 1),
        ),
        today=date(2025, 3, 1),
    )

    assert risk.risk_level == "green"
    assert risk.age_days == 365
    assert "2024-03-01" in risk.risk_reason


def test_no_usable_age_dates_needs_review() -> None:
    risk = compute_fields_risk(
        make_fields(manufacturing_date=None, effective_date=None, revision_date=None),
        today=date(2026, 1, 1),
    )

    assert risk.risk_level == "unknown"
    assert risk.compliance_status == "needs_review"
    assert risk.age_days is None
    assert "No usable" in risk.risk_reason


def test_malformed_date_string_needs_review_without_crashing() -> None:
    risk = compute_fields_risk(make_fields(manufacturing_date="not a date"), today=date(2026, 1, 1))

    assert risk.risk_level == "unknown"
    assert risk.compliance_status == "needs_review"
    assert risk.age_days is None
    assert "manufacturing_date" in risk.risk_reason


def test_na_expiry_with_old_effective_date_falls_through_to_age_red() -> None:
    # Printed "N/A" expiry is a real "no expiry" assertion, not an invalid date, so
    # risk falls through to age-based scoring on the effective date.
    # Effective 2023-04-26 vs today 2026-06-10 is over the 3-year threshold -> red.
    risk = compute_fields_risk(
        make_fields(
            manufacturing_date=None,
            effective_date=date(2023, 4, 26),
            revision_date=None,
            expiry_date="N/A",
        ),
        today=date(2026, 6, 10),
    )

    assert risk.risk_level == "red"
    assert risk.compliance_status == "at_risk"
    assert risk.age_days == (date(2026, 6, 10) - date(2023, 4, 26)).days
    assert "over the 3-year threshold" in risk.risk_reason


def test_na_expiry_alone_with_no_age_dates_needs_review() -> None:
    # "N/A" expiry with no manufacturing/effective/revision date leaves no usable
    # date for age scoring, so the document needs review (unknown), not an error.
    risk = compute_fields_risk(
        make_fields(
            manufacturing_date=None,
            effective_date=None,
            revision_date=None,
            expiry_date="N/A",
        ),
        today=date(2026, 6, 10),
    )

    assert risk.risk_level == "unknown"
    assert risk.compliance_status == "needs_review"
    assert risk.age_days is None
    assert "No usable" in risk.risk_reason


def test_na_expiry_marker_variants_are_treated_as_no_date() -> None:
    for marker in ("N/A", "n/a", "N.A.", "NA", "Not Applicable", "  N/A  "):
        risk = compute_fields_risk(
            make_fields(
                manufacturing_date=None,
                effective_date=date(2025, 1, 1),
                revision_date=None,
                expiry_date=marker,
            ),
            today=date(2026, 6, 10),
        )
        assert risk.risk_level == "green", marker
        assert "ambiguous or invalid" not in risk.risk_reason, marker


def test_record_risk_accepts_repository_style_iso_strings() -> None:
    record = SDFExtractionRecord(
        doc_id="doc-001",
        filename="supplier.pdf",
        fields=make_fields(manufacturing_date="2024-01-01", expiry_date="2027-01-01"),
    )

    risk = compute_record_risk(record, today=date(2026, 1, 1))

    assert risk.risk_level == "amber"
    assert risk.age_days == 731
