# S08: Record Eval tab UAT evidence

**Goal:** Record sanitized runtime UAT evidence proving the Streamlit Eval tab renders persisted evaluation metric history, supports comparing two synthetic runs, and shows actionable fresh database empty-state guidance without crashing.
**Demo:** After this: A recorded dashboard walkthrough proves the Eval tab shows at least one run and metrics, compares two runs, and displays actionable messaging for a fresh DB without crashing.

## Must-Haves

- A deterministic synthetic populated UAT database exists with two complete evaluation runs and sanitized R007-style metric families: retrieval recall, citation accuracy, rag faithfulness, rag answer relevancy, latency, cost, and token metrics.
- Browser or equivalent runtime walkthrough evidence shows the Streamlit Eval tab on the populated DB with run history, metric table, comparison selection, and visible deltas between two runs.
- Browser or equivalent runtime walkthrough evidence shows the Streamlit Eval tab on a fresh or empty DB with clear no-runs guidance and no traceback.
- The evidence artifact explicitly records redaction compliance: no raw prompts, answers, snippets, provider payloads, secrets, sensitive document images, Docling JSON, raw text, or full hashes are included.
- Regression tests for dashboard eval rendering, eval repository boundaries, optional metrics, app startup, and the S08 seed helper pass on Windows-safe commands.

## Proof Level

- This slice proves: Final-assembly runtime UAT. Real Streamlit runtime evidence is required; supporting tests prove helper determinism and redaction boundaries. Human judgment is not required, but the final evidence artifact must be readable by a future reviewer.

## Integration Closure

S08 consumes the completed S06 SQLite eval_runs and eval_metrics contracts and S07 safe observability constraints without changing the dashboard computation boundary. It introduces only deterministic UAT seed and evidence artifacts; no provider, Langfuse, RAGAS, or dashboard-side evaluator wiring is added. When complete, M003 has runtime evidence that the dashboard's Eval tab satisfies R007-visible persisted metric history and preserves R010 redaction boundaries.

## Verification

- The slice makes evaluation observability inspectable through three surfaces: the synthetic UAT SQLite database rows, the Streamlit Eval tab screenshots or debug bundles, and the final S08 UAT evidence markdown. Failure visibility is captured as actionable empty-state guidance rather than traceback. Redaction constraints remain explicit in artifacts and seed data uses only synthetic run IDs and metric names.

## Tasks

- [x] **T01: Add deterministic UAT seed helper** `est:45m`
  ---
  estimated_steps: 7
  estimated_files: 2
  skills_used:
    - tdd
    - verify-before-complete
  ---
  Why: S08 needs repeatable, sanitized data that visibly exercises R007 metric history without relying on the mutable local compliance.db or any raw document content. The helper must use existing schema and repository boundaries so the dashboard remains read-only and provider-free.
  - Files: `scripts/seed_s08_uat_eval_db.py`, `tests/test_s08_uat_seed.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_s08_uat_seed.py tests/test_dashboard_eval_tab.py

- [x] **T02: Capture populated Eval tab walkthrough** `est:1h`
  ---
  estimated_steps: 8
  estimated_files: 3
  skills_used:
    - write-docs
    - verify-before-complete
  ---
  Why: Unit tests are not enough for S08. The slice must prove the real Streamlit app renders persisted metric history and comparison deltas from SQLite without triggering evaluator computation on rerun.
  - Files: `.gsd/milestones/M003/slices/S08/s08-uat-populated.db`, `.gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md`
  - Verify: venv/Scripts/python.exe scripts/seed_s08_uat_eval_db.py --db-path .gsd/milestones/M003/slices/S08/s08-uat-populated.db
Browser assertion: http://localhost:8608 Eval tab shows Run history, Metrics, rag.faithfulness.avg, retrieval.recall@5, and a comparison delta for two synthetic runs.

- [x] **T03: Capture fresh database empty state and final evidence** `est:1h`
  ---
  estimated_steps: 9
  estimated_files: 3
  skills_used:
    - write-docs
    - verify-before-complete
  ---
  Why: M003 success criteria require no crashes on missing prerequisites. S08 must prove the Eval tab handles a fresh or empty DB with actionable guidance and must package all evidence with final regression results.
  - Files: `.gsd/milestones/M003/slices/S08/s08-fresh-empty.db`, `.gsd/milestones/M003/slices/S08/S08-UAT-EMPTY.md`, `.gsd/milestones/M003/slices/S08/S08-UAT-EVIDENCE.md`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_dashboard_eval_tab.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_app.py tests/test_s08_uat_seed.py
Browser assertion: http://localhost:8609 Eval tab shows No evaluation runs yet and no traceback.

## Files Likely Touched

- scripts/seed_s08_uat_eval_db.py
- tests/test_s08_uat_seed.py
- .gsd/milestones/M003/slices/S08/s08-uat-populated.db
- .gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md
- .gsd/milestones/M003/slices/S08/s08-fresh-empty.db
- .gsd/milestones/M003/slices/S08/S08-UAT-EMPTY.md
- .gsd/milestones/M003/slices/S08/S08-UAT-EVIDENCE.md
