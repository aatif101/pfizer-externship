# S04: Compliance dashboard records — UAT

**Milestone:** M001
**Written:** 2026-05-20T18:04:36.634Z

# UAT: S04 Compliance Dashboard Records

## UAT Type
Manual evaluator walkthrough over an offline local SQLite database, supported by automated pytest regression evidence.

## Preconditions
1. Use the project Python 3.11 virtual environment at `venv/Scripts/python.exe`.
2. Have either an extracted demo SQLite database configured by `src.config.get_settings().db_path`, or use an empty/missing database to verify the empty state.
3. Do not set Gemini, Claude, or Langfuse credentials for this UAT; the Compliance tab must remain usable without provider secrets.

## Steps
1. Start the Streamlit app with the project environment, for example `venv/Scripts/python.exe -m streamlit run src/app.py`.
2. Open the app in a browser and navigate to the **Compliance** tab.
3. If no compliance database/table exists, observe the empty state.
4. With a database containing extracted compliance records, reload the app and open the **Compliance** tab again.
5. Review the summary metrics for total records, risk distribution, and review state.
6. Review the records table for document metadata: document type, vendor, relevant dates/age, risk level/reason, confidence, review state, run_id/trace_id, and source-page display.
7. Select or expand a record's source evidence detail.
8. Confirm the detail shows sanitized source page/span evidence and, when available, a page image preview.
9. Repeat with a record that has missing/null source evidence or no page image.

## Expected Outcomes
- The app starts and the Compliance tab renders without Gemini, Claude, or Langfuse credentials.
- Missing DB or missing `compliance_records` table produces a friendly empty state rather than a stack trace.
- Persisted records from SQLite appear in the Compliance tab with readable metadata, risk coloring/status, confidence, review state, run metadata, and trace metadata.
- Source page numbers are displayed to users as 1-indexed pages.
- Source evidence is visible enough to support auditability but does not expose API keys, raw provider responses, full page text blobs, or stack traces.
- Page image lookup is lazy/optional; absent images produce a tolerant detail state rather than a crash.

## Edge Cases
- Empty database or missing compliance table.
- Null source span/page fields.
- 0-indexed persisted page values displayed as 1-indexed user-facing pages.
- `needs_review` persisted as integer values and rendered as boolean/review labels.
- Missing page image for a selected source evidence record.

## Not Proven By This UAT
- Live LLM extraction quality or provider availability.
- Langfuse SaaS trace ingestion with real credentials.
- Large-corpus performance beyond the expected small demo corpus.
- Visual retrieval or chatbot behavior from later milestones.
