# S05: Validation remediation boundary and end to end proof — UAT

**Milestone:** M001
**Written:** 2026-05-20T19:27:17.490Z

# S05 UAT: Validation remediation boundary and end to end proof

## Automated UAT Result

This slice does not require manual UI UAT. The required evaluator-facing behavior was verified through automated final-assembly tests and dashboard adapter assertions.

## Commands Run

1. `venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py -q`
   - Result: 1 passed, 15 warnings in 53.18s.
   - Proves: realistic generated SDF PDF ingestion, non-empty persisted page text, grounded fake-provider extraction, six extraction rows, one compliance row, amber risk, source evidence, and dashboard adapter formatting.

2. `venv/Scripts/python.exe -m pytest tests/test_ingest.py tests/test_extraction_pipeline.py tests/test_compliance_dashboard.py tests/test_app.py -q`
   - Result: 20 passed, 18 warnings in 93.88s.
   - Proves: focused regression across ingestion, extraction, dashboard, and app startup.

3. `venv/Scripts/python.exe -m pytest -q`
   - Result: 72 passed, 20 warnings in 145.56s.
   - Proves: full project regression after S05 changes.

## Human Check Status

No human check is required to close M001. Optional human demo after this milestone: run the Streamlit app against a populated SQLite database and visually inspect the Compliance tab.
