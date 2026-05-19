---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T02: Make local settings secret-safe

Remove settings.local.json from Git tracking, add it to .gitignore, and verify the local file does not contain known token prefixes.

## Inputs

- `settings.local.json`
- `.gitignore`

## Expected Output

- `.gitignore`

## Verification

git check-ignore settings.local.json && python - <<'PY'
from pathlib import Path
text = Path('settings.local.json').read_text() if Path('settings.local.json').exists() else ''
assert not any(x in text for x in ['sk-or-v1-', 'sk-ant-', 'sk-', 'AIza'])
print('secret scan passed')
PY

## Observability Impact

Captures the local-secret rule as durable project state.
