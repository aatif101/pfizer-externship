# S05: S05 — UAT

**Milestone:** M003
**Written:** 2026-05-22T18:42:04.414Z

# UAT: Dashboard polish and presentation consistency (S05)

## UAT Type
Manual UI walkthrough (presentation readiness / UX consistency)

## Preconditions
1. You can run the dashboard locally (Streamlit).
2. You have either:
   - a SQLite DB with some compliance/extraction and evaluation data, OR
   - no DB / empty DB (to validate empty states).

## Steps
1. Launch the dashboard (`streamlit run src/app.py`).
2. Open the **Compliance** tab.
   1. Verify the page shows a clear title and a short explanatory caption.
   2. If records exist: verify the table is easy to scan (key columns prioritized, consistent labels).
   3. If no records exist: verify an empty-state message appears and explains what to do next (e.g., run ingestion/extraction).
3. Open the **Chat** tab.
   1. Verify the title/caption style matches Compliance and Eval.
   2. With an empty DB: verify the empty-state guidance explains prerequisites (documents/index) rather than crashing.
   3. With data present: verify the chat UI remains responsive and does not trigger background evaluation work on rerun.
4. Open the **Eval** tab.
   1. Verify the title/caption and section dividers match the other tabs.
   2. If eval runs exist: verify run status and any error reason are readable; select two runs and confirm the comparison view formats metrics consistently (numeric formatting and grouping readable).
   3. If no eval runs exist: verify the empty-state explains how to create runs and does not error.

## Expected Outcomes
- All tabs share a consistent header hierarchy (title + short caption) and section structure.
- Tables and metrics are formatted consistently and are easy to scan.
- Empty states are actionable and do not crash when prerequisites are missing.
- No provider credentials are required to view the dashboard; no evaluation work is triggered just by viewing tabs.

## Edge Cases to Check
- A run that has a non-empty error_reason: it should be displayed clearly without breaking layout.
- Very small/very large metric values: formatting remains readable.
- Empty DB file / missing eval runs: UI should guide rather than crash.

## Not Proven By This UAT
- Model quality improvements (only presentation/readability changes are validated here).
- Faithfulness/citation correctness of any specific generated answer (handled by earlier evaluation slices).
