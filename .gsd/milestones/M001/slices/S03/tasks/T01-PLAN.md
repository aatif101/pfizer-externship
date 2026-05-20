---
estimated_steps: 21
estimated_files: 5
skills_used: []
---

# T01: Compute and persist document risk metadata

---
estimated_steps: 7
estimated_files: 4
skills_used:
  - tdd
  - verify-before-complete
---

Why: S02 created nullable risk columns, but repository persistence currently writes `None` for `risk_reason` and `age_days`. S03 needs deterministic compliance metadata before the runtime extractor can populate dashboard rows.

Do:
1. Extend `src/extraction/models.py` so `SDFExtractionRecord` carries `risk_reason: str | None` and `age_days: int | None` with the same trim/nullable behavior as existing document-level text fields.
2. Update `src/extraction/repository.py` so `_upsert_compliance_record()` persists `record.risk_reason` and `record.age_days`, and `get_extraction_record()` selects/reconstructs both fields.
3. Add `src/extraction/risk.py` with pure functions that accept validated fields/records and an injectable `today` date.
4. Implement conservative policy: expired `expiry_date` => red; otherwise use oldest available manufacturing/effective/revision date for age; under 2 years => green; 2 to 3 years => amber; over 3 years => red; all missing/abstained/ambiguous relevant dates => `needs_review`/unknown with clear reason.
5. Keep date parsing robust for `date` objects and ISO strings because repository round-trips normalized dates as dashboard strings.
6. Add tests in `tests/test_extraction_risk.py` and update persistence tests to assert risk fields round-trip through SQLite.

Threat Surface (Q3): Risk inputs are extracted untrusted document text normalized through Pydantic. No raw SQL interpolation; do not log source spans while computing risk.
Requirement Impact (Q4): Advances R003 and supports R004. Re-verify extraction model, persistence, and schema tests. Decisions D009/D010 apply.
Failure Modes (Q5): Missing/invalid date values must not crash risk computation; they produce a needs-review result and reason. SQLite write failures should rollback through existing repository behavior.
Load Profile (Q6): Pure CPU/date parsing per document; trivial compared with provider calls. At 10x load, DB write volume dominates, not risk computation.
Negative Tests (Q7): Expired expiry date, no usable dates, malformed date strings, threshold boundary dates, and repository reconstruction of risk fields.

Done when risk policy is covered by unit tests and persisted compliance rows expose `risk_level`, `risk_reason`, `compliance_status`, and `age_days` from records instead of hardcoded nulls.

## Inputs

- `src/extraction/models.py`
- `src/extraction/repository.py`
- `tests/test_extraction_models.py`
- `tests/test_extraction_persistence.py`

## Expected Output

- `src/extraction/models.py`
- `src/extraction/repository.py`
- `src/extraction/risk.py`
- `tests/test_extraction_risk.py`
- `tests/test_extraction_persistence.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_persistence.py tests/test_extraction_risk.py -q

## Observability Impact

Adds persisted document-level risk reason and age fields that future agents can inspect via `list_compliance_records()` and `get_extraction_record()` without rerunning extraction.
