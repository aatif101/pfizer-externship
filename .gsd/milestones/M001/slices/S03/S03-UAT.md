# S03: Baseline extraction pipeline — UAT

**Milestone:** M001
**Written:** 2026-05-20T17:40:56.153Z

No human UAT required for S03. Integration proof completed through deterministic offline automated tests. Evidence: `venv/Scripts/python.exe -m pytest -q` exited 0 with 65 passed and 19 warnings. CLI tests exercise extract and extract-all against temporary SQLite databases with mocked providers. Provider tests cover missing Gemini credentials, malformed output abstentions, retryable failure wrapping/redaction, low-confidence review state, and source-span mismatch abstention.
