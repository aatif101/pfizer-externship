"""Extraction contract models for Pfizer SDF documents."""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class SDFFieldName(str, Enum):
    """Required structured fields extracted from a supplier SDF document."""

    DOC_TYPE = "doc_type"
    VENDOR_NAME = "vendor_name"
    MANUFACTURING_DATE = "manufacturing_date"
    EFFECTIVE_DATE = "effective_date"
    REVISION_DATE = "revision_date"
    EXPIRY_DATE = "expiry_date"


class ReviewState(str, Enum):
    """Human-review lifecycle for an extracted field or document."""

    PENDING = "pending"
    NEEDS_REVIEW = "needs_review"
    REVIEWED = "reviewed"
    ABSTAINED = "abstained"


class SourceEvidence(BaseModel):
    """Source-page evidence for an extracted value.

    Page numbers are 0-indexed to match the ingestion/page persistence layer. Bounding
    boxes are intentionally schema-light because Docling/vision models may emit either
    list-style coordinates or object-style page regions, but values must still be JSON
    serializable before later SQLite writes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_num: int = Field(ge=0, description="0-indexed source page number")
    bbox: dict[str, Any] | list[Any] | None = Field(
        default=None,
        description="Optional JSON-serializable source bounding box or polygon.",
    )
    verbatim_span: str | None = Field(
        default=None,
        description="Short source text span supporting the extracted value.",
    )

    @field_validator("bbox")
    @classmethod
    def bbox_must_be_json_shape(cls, value: dict[str, Any] | list[Any] | None) -> dict[str, Any] | list[Any] | None:
        if value is None:
            return value
        if not isinstance(value, (dict, list)):
            raise ValueError("bbox must be a JSON-serializable dict or list")
        _assert_json_serializable(value, path="bbox")
        return value

    @field_validator("verbatim_span")
    @classmethod
    def normalize_verbatim_span(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ExtractedField(BaseModel):
    """One validated SDF field extraction with confidence, evidence, and review state."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    field_name: SDFFieldName
    raw_value: str | None = None
    normalized_value: str | int | float | bool | None = None
    normalized_date: date | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: SourceEvidence
    review_state: ReviewState = ReviewState.PENDING
    abstention_reason: str | None = None

    @field_validator("raw_value", "abstention_reason")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_value_review_state_and_evidence(self) -> ExtractedField:
        if self.review_state == ReviewState.ABSTAINED:
            if not self.abstention_reason:
                raise ValueError("abstained fields require an abstention_reason")
            return self

        if self.raw_value is None and self.normalized_value is None and self.normalized_date is None:
            raise ValueError("non-abstained fields require a raw or normalized value")
        if self.evidence.verbatim_span is None:
            raise ValueError("non-abstained fields require evidence.verbatim_span")
        if self.abstention_reason is not None:
            raise ValueError("abstention_reason is only valid for abstained fields")
        return self

    @computed_field
    @property
    def needs_review(self) -> bool:
        """Whether the field should be surfaced for compliance-officer review."""

        return self.review_state in {ReviewState.NEEDS_REVIEW, ReviewState.ABSTAINED}

    @computed_field
    @property
    def value_for_dashboard(self) -> str | int | float | bool | None:
        """Prefer normalized date/value for dashboard tables, falling back to raw text."""

        if self.normalized_date is not None:
            return self.normalized_date.isoformat()
        if self.normalized_value is not None:
            return self.normalized_value
        return self.raw_value


class SDFExtractionRecord(BaseModel):
    """Validated extraction contract for a single SDF document."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    doc_id: str
    filename: str
    fields: dict[SDFFieldName, ExtractedField]
    trace_id: str | None = None
    run_id: str | None = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    risk_level: str | None = Field(default=None, description="Dashboard compliance risk band.")
    risk_reason: str | None = Field(default=None, description="Human-readable reason for the computed risk band.")
    compliance_status: str | None = Field(default=None, description="Dashboard compliance status derived from risk policy.")
    age_days: int | None = Field(default=None, description="Age in days from the oldest relevant document date.")

    @field_validator("doc_id", "filename", "trace_id", "run_id", "risk_level", "risk_reason", "compliance_status")
    @classmethod
    def strip_optional_record_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_exact_required_fields(self) -> SDFExtractionRecord:
        expected = set(SDFFieldName)
        actual = set(self.fields)
        if actual != expected:
            missing = sorted(field.value for field in expected - actual)
            extra = sorted(str(field) for field in actual - expected)
            raise ValueError(f"SDFExtractionRecord requires exactly six SDF fields; missing={missing}; extra={extra}")

        mismatched = [name.value for name, field in self.fields.items() if field.field_name != name]
        if mismatched:
            raise ValueError(f"field dictionary keys must match each ExtractedField.field_name: {mismatched}")
        return self

    @computed_field
    @property
    def aggregate_confidence(self) -> float:
        """Mean field confidence for quick sorting and dashboards."""

        if not self.fields:
            return 0.0
        return sum(field.confidence for field in self.fields.values()) / len(self.fields)

    @computed_field
    @property
    def aggregate_review_state(self) -> ReviewState:
        """Summarize field review states into a document-level review state."""

        states = {field.review_state for field in self.fields.values()}
        if ReviewState.NEEDS_REVIEW in states or ReviewState.ABSTAINED in states:
            return ReviewState.NEEDS_REVIEW
        if states == {ReviewState.REVIEWED}:
            return ReviewState.REVIEWED
        return ReviewState.PENDING

    @computed_field
    @property
    def dashboard_values(self) -> dict[str, str | int | float | bool | None]:
        """Dashboard-friendly field value mapping keyed by stable field names."""

        return {field_name.value: field.value_for_dashboard for field_name, field in self.fields.items()}

    @computed_field
    @property
    def dashboard_needs_review(self) -> bool:
        """Document-level review flag for compliance dashboard filtering."""

        return any(field.needs_review for field in self.fields.values())

    @computed_field
    @property
    def dashboard_review_state(self) -> str:
        """String review state suitable for tabular persistence/UI display."""

        return self.aggregate_review_state.value


def _assert_json_serializable(value: Any, *, path: str) -> None:
    """Recursively validate a JSON-compatible primitive/list/dict shape."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_serializable(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string key: {key!r}")
            _assert_json_serializable(item, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} contains non-JSON-serializable value {value!r}")
