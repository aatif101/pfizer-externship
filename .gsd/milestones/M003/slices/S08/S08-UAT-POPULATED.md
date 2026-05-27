# S08 Populated Eval Tab UAT Evidence

## Scope

This evidence proves the real Streamlit dashboard Eval tab renders persisted evaluation metric history from a seeded SQLite database and compares two synthetic runs without triggering evaluator computation or exposing raw document contents.

## Runtime setup

- Seed command executed successfully:
  - `venv/Scripts/python.exe scripts/seed_s08_uat_eval_db.py --db-path .gsd/milestones/M003/slices/S08/s08-uat-populated.db`
- Streamlit runtime command used on port `8608`:
  - `powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:DB_PATH='.gsd/milestones/M003/slices/S08/s08-uat-populated.db'; & 'venv/Scripts/python.exe' -m streamlit run 'src/app.py' --server.port 8608 --server.headless true"`
- Local URL:
  - `http://localhost:8608`
- DB path:
  - `.gsd/milestones/M003/slices/S08/s08-uat-populated.db`

## Synthetic runs observed

The populated Eval tab run history rendered two complete synthetic runs:

| Run ID | Eval type | Pipeline label | Status |
|---|---|---|---|
| `s08-uat-eval-run-b` | `rag_retrieval_uat` | `synthetic-uat-candidate` | `complete` |
| `s08-uat-eval-run-a` | `rag_retrieval_uat` | `synthetic-uat-baseline` | `complete` |

The selected primary run was `s08-uat-eval-run-b`; the selected comparison run was `s08-uat-eval-run-a`.

## Metric families observed

The Eval tab rendered global metrics for the synthetic runs, including:

- Retrieval metrics:
  - `retrieval.recall@5`
  - `retrieval.recall@10`
  - `retrieval.citation_accuracy@5`
  - `retrieval.citation_accuracy@10`
- RAG quality metrics:
  - `rag.faithfulness.avg`
  - `rag.answer_relevancy.avg`
- Operational metrics:
  - `rag.latency_ms.avg`
  - `rag.latency_ms.p50`
  - `rag.latency_ms.p95`
  - `rag.cost_usd.total`
  - `rag.cost_usd.avg`
  - `rag.tokens.total`

## Browser/runtime assertions

Verification used Playwright Chromium against the live Streamlit runtime at `http://localhost:8608`. The browser clicked the real `Eval` tab, selected `s08-uat-eval-run-a` in the comparison combobox, and asserted both visible page text and Streamlit dataframe HTML output.

Assertions passed:

| Assertion | Result |
|---|---|
| HTTP navigation reached the Streamlit app on port `8608` | Pass |
| Eval tab showed the `Evaluation` heading | Pass |
| Eval tab rendered `Run history` | Pass |
| Eval tab rendered `Metrics` | Pass |
| Eval tab rendered `rag.faithfulness.avg` | Pass |
| Eval tab rendered `retrieval.recall@5` | Pass |
| Eval tab rendered both synthetic run IDs | Pass |
| No traceback or app exception text appeared before comparison | Pass |
| Primary and comparison Streamlit comboboxes rendered | Pass |
| Comparison run `s08-uat-eval-run-a` was selected | Pass |
| Eval tab rendered `Compare runs` | Pass |
| Comparison dataframe output contained a `delta` column/token | Pass |
| Comparison dataframe output contained nonzero deltas `-7.0%`, `-8.0%`, and `+145.0 ms` | Pass |
| No traceback or app exception text appeared after comparison | Pass |

## Comparison evidence

The comparison table rendered changed global metric rows. Representative deltas from `s08-uat-eval-run-b` compared to `s08-uat-eval-run-a` included:

| Metric | Candidate value | Baseline value | Delta |
|---|---:|---:|---:|
| `rag.faithfulness.avg` | `88.0%` | `81.0%` | `-7.0%` |
| `retrieval.recall@5` | `80.0%` | `72.0%` | `-8.0%` |
| `rag.latency_ms.avg` | `1275.0 ms` | `1420.0 ms` | `+145.0 ms` |
| `rag.tokens.total` | `17,650` | `18,400` | `+750` |

Note: The dashboard currently computes delta as `compare_value - primary_value`, so improvements in primary-over-baseline appear as negative deltas for ratio metrics when comparing candidate primary to baseline comparison.

## Evidence artifacts

- Browser screenshot focused on the Eval tab:
  - `.gsd/milestones/M003/slices/S08/s08-uat-populated-eval-tab.png`
- Browser assertion/debug JSON:
  - `.gsd/milestones/M003/slices/S08/s08-uat-populated-browser-debug.json`
- GSD command output artifacts:
  - Seed run: `.gsd/exec/c6af9f13-96d9-4e60-b13d-035d06ede14b.stdout`
  - Final browser-backed Eval tab assertions and screenshot capture: `.gsd/exec/4068f45a-6c3d-4dce-84c6-b005cf8a70bc.stdout`

## Redaction note

This evidence intentionally stays on the Eval surface and uses only synthetic UAT run IDs, pipeline labels, metric names, and numeric metric values. It does not include raw document contents, prompts, answers, snippets, source text, file paths to pharmaceutical PDFs, hashes, images, credentials, or Compliance/Chat screenshots.

## Outcome

Passed. The real Streamlit app rendered persisted Eval run history, retrieval/RAG/operational metrics, and nonzero comparison deltas from the synthetic SQLite database without crashing or invoking evaluator computation.
