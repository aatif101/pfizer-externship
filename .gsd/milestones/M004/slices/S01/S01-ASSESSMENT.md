---
sliceId: S01
uatType: browser-executable
verdict: PASS
date: 2026-06-03T22:22:00.131Z
---

# UAT Result — S01

## Checks

| Check | Mode | Result | Notes |
|-------|------|--------|-------|
| Smoke test: run `venv\\Scripts\\python.exe -m pytest -q tests/test_extraction_persistence.py` and confirm the suite passes. | runtime | PASS | Covered by the planned pytest run in `.gsd/exec/99752228-abbe-4870-bf3c-17a61c49a072.stdout`: `venv\\Scripts\\python.exe -m pytest -q tests/test_extraction_run_history_schema.py tests/test_extraction_persistence.py tests/test_extraction_cli.py tests/test_eval_repository.py` exited 0 with `34 passed in 9.01s`. The detailed run in `.gsd/exec/7e8d878b-9f60-4f4e-bd2b-6de44f8d8ef0.stdout` also exited 0 with `34 passed in 9.10s`. |
| Two extraction runs for the same document remain independently queryable. | runtime | PASS | Detailed pytest evidence: `tests/test_extraction_persistence.py::test_run_scoped_history_preserves_two_runs_while_latest_shows_newest PASSED`, proving run-scoped history preserves separate runs while compatibility latest shows newest. |
| Latest-write compatibility still works. | runtime | PASS | Detailed pytest evidence includes `test_upsert_record_round_trips_field_and_compliance_rows PASSED`, `test_record_upsert_is_idempotent_and_replaces_existing_values PASSED`, `test_list_compliance_records_orders_expiring_docs_before_nulls PASSED`, and `test_run_scoped_history_preserves_two_runs_while_latest_shows_newest PASSED`, confirming latest-write APIs keep returning compatible shapes and values. |
| CLI can persist a shared explicit run identity. | runtime | PASS | Detailed pytest evidence: `tests/test_extraction_cli.py::test_extract_command_uses_explicit_run_id_for_provider_and_history PASSED` and `tests/test_extraction_cli.py::test_extract_all_uses_shared_explicit_run_id_for_provider_and_history PASSED`. |
| Eval reads selected-run predictions only. | runtime | PASS | Detailed pytest evidence: `tests/test_eval_repository.py::test_list_predicted_extractions_for_run_filters_history_without_latest_fallback PASSED`, confirming explicit selected-run predictions come from history and do not fall back to latest-write rows. |
| Edge case: same run and document is upserted again. | runtime | PASS | Detailed pytest evidence: `tests/test_extraction_persistence.py::test_rerunning_same_run_doc_updates_history_without_duplicate_rows PASSED`, confirming idempotent update semantics for the same run/document pair. |
| Edge case: missing or orphaned history parent rows. | runtime | PASS | Detailed pytest evidence: `tests/test_extraction_run_history_schema.py::test_extraction_history_requires_existing_run_and_document PASSED` and `tests/test_extraction_run_history_schema.py::test_compliance_history_requires_existing_run_and_document PASSED`, confirming SQLite foreign-key constraints reject orphaned history relationships. |
| Edge case: confidential data remains outside run metadata. | runtime | PASS | Detailed pytest evidence: `tests/test_extraction_run_history_schema.py::test_history_tables_do_not_expose_forbidden_raw_content_columns PASSED`; CLI safety tests also passed, including `test_extract_all_reports_provider_failure_without_raw_document_text PASSED` and `test_missing_gemini_credentials_fail_safely PASSED`. |

## Overall Verdict

PASS — All automatable S01 UAT checks passed through Windows-native pytest execution with run-scoped history, latest-write compatibility, CLI explicit run identity, eval selected-run reads, idempotency, foreign-key enforcement, and bounded metadata all verified.

## Notes

- The UAT spec itself declares artifact-driven mode, while the runner detected `browser-executable`; there is no dashboard/UI target for S01, and the UAT explicitly defers dashboard run selector behavior to S02, so no browser screenshots were applicable.
- Primary evidence: `.gsd/exec/99752228-abbe-4870-bf3c-17a61c49a072.stdout` records the planned quiet pytest suite passing with exit code 0.
- Detailed test-name evidence: `.gsd/exec/7e8d878b-9f60-4f4e-bd2b-6de44f8d8ef0.stdout` records all 34 relevant tests passing with exit code 0.
- Commands were executed through `gsd_exec` with `runtime=node` spawning `venv\\Scripts\\python.exe`, avoiding `/bin/bash` and respecting the Windows verification rule.
