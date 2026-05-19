---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T03: Fix package editable install

Replace the broken setuptools legacy backend with setuptools.build_meta and verify editable install with dev extras in the Python 3.11 venv.

## Inputs

- `pyproject.toml`

## Expected Output

- `pyproject.toml`

## Verification

./venv/Scripts/python.exe -m pip install -e ".[dev]"

## Observability Impact

Documents the supported environment path for future agents.
