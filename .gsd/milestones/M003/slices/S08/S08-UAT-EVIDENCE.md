# S08 Final UAT Evidence: Eval Tab Runtime Observability

## Scope

S08 proves the Streamlit Eval tab makes evaluation observability inspectable from persisted SQLite history and handles a fresh database safely. The evidence covers both populated synthetic evaluation history and a no-runs empty state.

## Evidence surfaces

| Surface | Artifact | Result |
|---|---|---|
| Populated synthetic UAT SQLite database | `.gsd/milestones/M003/slices/S08/s08-uat-populated.db` | Pass |
| Populated Eval tab walkthrough | `.gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md` | Pass |
| Populated browser/debug artifacts | `.gsd/milestones/M003/slices/S08/s08-uat-populated-eval-tab.png`; `.gsd/milestones/M003/slices/S08/s08-uat-populated-browser-debug.json`; `.gsd/milestones/M003/slices/S08/s08-uat-populated-apptest-debug.json` | Pass |
| Fresh empty SQLite database | `.gsd/milestones/M003/slices/S08/s08-fresh-empty.db` | Pass |
| Fresh empty Eval tab walkthrough | `.gsd/milestones/M003/slices/S08/S08-UAT-EMPTY.md` | Pass |
| Empty-state debug bundle | `.gsd/milestones/M003/slices/S08/s08-uat-empty-apptest-debug.json` | Pass |

## Populated Eval tab walkthrough summary

The populated UAT database contains two complete synthetic runs:

| Run ID | Eval type | Pipeline label | Status |
|---|---|---|---|
| `s08-uat-eval-run-b` | `rag_retrieval_uat` | `synthetic-uat-candidate` | `complete` |
| `s08-uat-eval-run-a` | `rag_retrieval_uat` | `synthetic-uat-baseline` | `complete` |

The Eval tab rendered persisted run history and metric families from SQLite, including retrieval, RAG quality, latency, cost, and token metrics. It also rendered comparison deltas between the synthetic candidate and baseline runs. Representative metrics observed in the populated evidence include:

- `retrieval.recall@5`
- `retrieval.recall@10`
- `retrieval.citation_accuracy@5`
- `retrieval.citation_accuracy@10`
- `rag.faithfulness.avg`
- `rag.answer_relevancy.avg`
- `rag.latency_ms.avg`
- `rag.cost_usd.total`
- `rag.tokens.total`

Representative comparison deltas observed:

| Metric | Candidate value | Baseline value | Delta shown |
|---|---:|---:|---:|
| `rag.faithfulness.avg` | `88.0%` | `81.0%` | `-7.0%` |
| `retrieval.recall@5` | `80.0%` | `72.0%` | `-8.0%` |
| `rag.latency_ms.avg` | `1275.0 ms` | `1420.0 ms` | `+145.0 ms` |
| `rag.tokens.total` | `17,650` | `18,400` | `+750` |

Note: The current dashboard computes delta as comparison value minus primary value. Therefore candidate improvements over baseline appear as negative deltas for ratio metrics when the candidate is selected as primary and the baseline as comparison.

## Fresh empty Eval tab walkthrough summary

The fresh UAT database was initialized through the project schema and intentionally left with no evaluation rows:

| Table | Row count |
|---|---:|
| `eval_runs` | `0` |
| `eval_metrics` | `0` |

With `DB_PATH` pointed at this database, the Eval tab rendered the empty-state message:

- `No evaluation runs yet. Run the evaluation CLI/tests to populate eval_runs and eval_metrics in the SQLite database.`

The rendered caption identified the DB path being inspected. No Streamlit exception elements or traceback text appeared in the AppTest snapshot. A live Streamlit process also started on port `8609`, returned HTTP 200, announced `Local URL: http://localhost:8609`, and emitted no startup traceback.

## Regression commands

Focused regression command required by the task plan:

```text
venv/Scripts/python.exe -m pytest -q tests/test_dashboard_eval_tab.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_app.py tests/test_s08_uat_seed.py
```

Additional runtime evidence commands executed during S08 T03:

```text
venv\\Scripts\\python.exe -c <init_db .gsd/milestones/M003/slices/S08/s08-fresh-empty.db>
venv\\Scripts\\python.exe -c <apptest-empty-eval-state>
DB_PATH=.gsd/milestones/M003/slices/S08/s08-fresh-empty.db venv\\Scripts\\python.exe -m streamlit run src/app.py --server.port 8609 --server.headless true
```

## Pass/fail checklist

| Check | Result | Evidence |
|---|---|---|
| Populated Eval tab shows at least one run | Pass | `S08-UAT-POPULATED.md` |
| Populated Eval tab shows two synthetic complete runs | Pass | `S08-UAT-POPULATED.md` |
| Populated Eval tab shows retrieval and RAG metrics | Pass | `S08-UAT-POPULATED.md` |
| Populated Eval tab compares two runs | Pass | `S08-UAT-POPULATED.md` |
| Populated Eval tab shows nonzero deltas | Pass | `S08-UAT-POPULATED.md` |
| Fresh DB contains zero eval runs | Pass | `S08-UAT-EMPTY.md`; `s08-uat-empty-apptest-debug.json` |
| Fresh DB Eval tab shows actionable no-runs guidance | Pass | `S08-UAT-EMPTY.md`; `s08-uat-empty-apptest-debug.json` |
| Fresh DB Eval tab has no Streamlit exception elements | Pass | `S08-UAT-EMPTY.md`; `s08-uat-empty-apptest-debug.json` |
| Fresh DB Eval tab has no traceback text | Pass | `S08-UAT-EMPTY.md`; `s08-uat-empty-apptest-debug.json` |
| Live Streamlit process starts on port `8609` with fresh DB_PATH | Pass | `.gsd/exec/12c62141-46e9-4680-a8ef-b14d32bd204a.stdout` |
| Focused pytest regression suite passes | Pass | `.gsd/exec/cdde103f-24ee-4769-87c0-05f897b0bb6f.stdout` |

## R010 redaction compliance

This UAT package is sanitized. It includes only:

- Synthetic run IDs
- Synthetic pipeline labels
- Metric names
- Numeric metric values
- SQLite table names and row counts
- Local artifact paths
- Streamlit UI guidance text
- Pass/fail assertion outcomes

This UAT package excludes:

- Provider payloads
- Raw prompts
- Generated answers
- Document snippets or source document text
- Images of sensitive documents
- Docling JSON
- Full hashes
- Secrets or credentials
- Live Langfuse traces or keys

## Known limitations

- Fresh empty-state UI exercise used Streamlit AppTest fallback because browser automation tools were not exposed in this execution namespace. The fallback still executed the real `src/app.py` Streamlit entry point with `DB_PATH` set to the fresh database.
- A live Streamlit process was separately started on port `8609` and checked over HTTP, but direct browser tab interaction for the empty-state case was not available in this harness.
- Live Langfuse UAT was intentionally not attempted; R008 remains prerequisite context only for this slice.

## Outcome

Passed. The Eval tab evidence demonstrates populated persisted metrics, comparison deltas, actionable fresh-database guidance, no empty-state crash, focused regression success, and explicit R010 redaction compliance.