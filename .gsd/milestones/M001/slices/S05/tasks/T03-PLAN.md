---
estimated_steps: 18
estimated_files: 10
skills_used: []
---

# T03: Run closeout verification and package evidence

---
estimated_steps: 6
estimated_files: 0
skills_used:
  - verify-before-complete
---

Why: S05 is the final M001 remediation slice, so completion must be based on fresh evidence rather than prior S04 regression output or research probes.

Do:
1. Run the targeted S05 proof test using `venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py -q`.
2. Run focused regression across ingestion, extraction, dashboard, and app startup: `venv/Scripts/python.exe -m pytest tests/test_ingest.py tests/test_extraction_pipeline.py tests/test_compliance_dashboard.py tests/test_app.py -q`.
3. Run the full test suite with `venv/Scripts/python.exe -m pytest -q`; expect Docling warnings and roughly multi-minute runtime.
4. Capture command, exit code, duration, and concise stdout/stderr paths through `gsd_exec` or equivalent GSD evidence in the task/slice completion summaries.
5. Confirm no generated PDF/SQLite temporary artifacts are left in tracked project paths; test-generated files should remain under pytest temp directories.
6. If full regression fails for an unrelated environment reason, preserve targeted proof evidence, document the failure mode, and do not claim M001 is complete until the regression issue is resolved or explicitly scoped.

Failure Modes: Docling conversions are slow/noisy and may fail if local model/cache dependencies change. Missing Gemini/Langfuse credentials must not fail these offline tests. Test commands must use `venv/Scripts/python.exe` rather than global Python.

Load Profile: Full pytest is the heaviest operation in this slice and exercises Docling-backed ingestion. At larger corpus sizes this proof would not establish throughput; it only establishes one-document final assembly correctness.

Negative Tests: Full regression should preserve existing tests for empty DB/table dashboard states, app startup without credentials, invalid extraction spans, missing page text, malformed Gemini output, and sanitized provider/CLI errors.

Done when: Targeted proof, focused regression, and full suite results are freshly recorded, and S05 completion artifacts can cite evidence without secrets.

## Inputs

- `tests/test_s05_end_to_end_proof.py`
- `tests/test_ingest.py`
- `tests/test_extraction_pipeline.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_app.py`
- `src/pipeline/ingest.py`
- `src/extraction/pipeline.py`
- `src/dashboard/compliance.py`
- `.gsd/milestones/M001/M001-ROADMAP.md`
- `.gsd/milestones/M001/M001-VALIDATION.md`

## Expected Output

- Update the implementation and proof artifacts needed for this task.

## Verification

venv/Scripts/python.exe -m pytest -q

## Observability Impact

Produces fresh executable evidence for S05 closeout. The evidence should name gsd_exec IDs/stdout paths, test counts, and any failure diagnostics while avoiding raw secrets or provider payloads.
