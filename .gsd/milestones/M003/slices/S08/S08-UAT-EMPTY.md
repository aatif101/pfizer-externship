# S08 Fresh Empty Eval Tab UAT Evidence

## Scope

This evidence proves the Streamlit dashboard Eval tab handles a freshly initialized SQLite database with zero evaluation runs without crashing, and presents actionable guidance for how to populate evaluation history.

## Runtime setup

- Fresh DB initialization command executed successfully:
  - `venv\\Scripts\\python.exe -c <init_db .gsd/milestones/M003/slices/S08/s08-fresh-empty.db>`
- Streamlit runtime command used on port `8609`:
  - `DB_PATH=.gsd/milestones/M003/slices/S08/s08-fresh-empty.db venv\\Scripts\\python.exe -m streamlit run src/app.py --server.port 8609 --server.headless true`
- Local URL:
  - `http://localhost:8609`
- DB path:
  - `.gsd/milestones/M003/slices/S08/s08-fresh-empty.db`

## Fresh DB state

The database was initialized through `src.db.schema.init_db` and intentionally left with no evaluation rows.

| Table | Row count |
|---|---:|
| `eval_runs` | `0` |
| `eval_metrics` | `0` |

## Eval tab assertions

Browser automation tools were not available in this execution namespace, so this UAT used the task-approved Streamlit AppTest fallback against the real `src/app.py` entry point with `DB_PATH` pointed at the fresh database. A separate live Streamlit process was also started on port `8609` and reached over HTTP without startup traceback.

Assertions passed:

| Assertion | Result |
|---|---|
| Fresh SQLite database contains the `eval_runs` table | Pass |
| Fresh SQLite database contains the `eval_metrics` table | Pass |
| `eval_runs` contains zero rows | Pass |
| `eval_metrics` contains zero rows | Pass |
| AppTest rendered the app with the Eval tab content | Pass |
| Eval tab displayed `No evaluation runs yet` guidance | Pass |
| Eval tab guidance tells the user to run evaluation CLI/tests | Pass |
| Eval tab caption displayed the resolved DB path | Pass |
| No Streamlit exception elements were emitted | Pass |
| No traceback text appeared in the rendered element snapshot | Pass |
| Live Streamlit process started on port `8609` and returned HTTP 200 | Pass |
| Live startup logs announced `Local URL: http://localhost:8609` | Pass |
| Live startup logs contained no traceback | Pass |

## Evidence artifacts

- Fresh empty SQLite database:
  - `.gsd/milestones/M003/slices/S08/s08-fresh-empty.db`
- AppTest debug bundle focused on the empty Eval state:
  - `.gsd/milestones/M003/slices/S08/s08-uat-empty-apptest-debug.json`
- GSD command output artifacts:
  - DB initialization: `.gsd/exec/fc46b360-5725-4171-acc4-96f64322688e.stdout`
  - Empty Eval AppTest assertions: `.gsd/exec/b1a70e67-7ae9-44c4-816f-ee70ca888269.stdout`
  - Live Streamlit startup on port `8609`: `.gsd/exec/12c62141-46e9-4680-a8ef-b14d32bd204a.stdout`

## Redaction note

This evidence contains only synthetic database paths, table names, UI guidance text, and assertion outcomes. It does not include provider payloads, prompts, answers, document snippets, source document text, images of sensitive documents, Docling JSON, full hashes, or secrets.

## Outcome

Passed. The Eval tab rendered actionable fresh-database guidance from a zero-run SQLite database and did not crash.