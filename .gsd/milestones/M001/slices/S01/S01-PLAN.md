# S01: Migration readiness cleanup

**Goal:** Make the migrated GSD 1.0 project safe and ready for Phase 2 execution.
**Demo:** Repo is on current GitHub main, local secrets are untracked, Python 3.11 editable install works, tests pass, and current GSD artifacts reflect migrated project state.

## Must-Haves

- Local main matches origin/main.
- settings.local.json is removed from Git tracking and ignored.
- pyproject editable install works in the Python 3.11 venv.
- Tests pass with ./venv/Scripts/python.exe.
- Current .gsd PROJECT, REQUIREMENTS, DECISIONS, and ROADMAP exist.

## Proof Level

- This slice proves: Repository inspection plus editable install and pytest in Python 3.11 venv.

## Integration Closure

Git state, packaging, local secret handling, tests, and current GSD artifacts all agree on the next working baseline.

## Verification

- Documents environment/security gotchas in GSD decisions and requirements for future agents.

## Tasks

- [x] **T01: Reconcile GitHub main** `est:small`
  Fast-forward local main to origin/main and confirm both refs match before editing.
  - Verify: git rev-parse HEAD && git rev-parse origin/main

- [x] **T02: Make local settings secret-safe** `est:small`
  Remove settings.local.json from Git tracking, add it to .gitignore, and verify the local file does not contain known token prefixes.
  - Files: `.gitignore`, `settings.local.json`
  - Verify: git check-ignore settings.local.json && python - <<'PY'
from pathlib import Path
text = Path('settings.local.json').read_text() if Path('settings.local.json').exists() else ''
assert not any(x in text for x in ['sk-or-v1-', 'sk-ant-', 'sk-', 'AIza'])
print('secret scan passed')
PY

- [x] **T03: Fix package editable install** `est:small`
  Replace the broken setuptools legacy backend with setuptools.build_meta and verify editable install with dev extras in the Python 3.11 venv.
  - Files: `pyproject.toml`
  - Verify: ./venv/Scripts/python.exe -m pip install -e ".[dev]"

- [x] **T04: Normalize GSD artifacts** `est:medium`
  Seed current GSD artifacts from the old .planning state: project summary, requirements register, roadmap, slice plan, and decisions.
  - Files: `.gsd/PROJECT.md`, `.gsd/REQUIREMENTS.md`, `.gsd/ROADMAP.md`, `.gsd/DECISIONS.md`
  - Verify: test -f .gsd/PROJECT.md && test -f .gsd/REQUIREMENTS.md && test -f .gsd/ROADMAP.md && test -f .gsd/DECISIONS.md

- [x] **T05: Verify readiness cleanup** `est:small`
  Run the project test suite using the supported Python 3.11 venv and inspect git status for expected changes only.
  - Verify: ./venv/Scripts/python.exe -m pytest -q && git status --short

## Files Likely Touched

- .gitignore
- settings.local.json
- pyproject.toml
- .gsd/PROJECT.md
- .gsd/REQUIREMENTS.md
- .gsd/ROADMAP.md
- .gsd/DECISIONS.md
