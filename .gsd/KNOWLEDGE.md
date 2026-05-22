# Project Knowledge

Append-only register of project-specific rules, patterns, and lessons learned.
Agents read this before every unit. Add entries when you discover something worth remembering.
## Rules

| # | Scope | Rule | Why | Added |
|---|-------|------|-----|-------|
| 1 | Verification tooling (Windows) | Never run verification via `gsd_exec` `runtime=bash` and never invoke `/bin/bash`. Use `gsd_exec` `runtime=node` to spawn `venv\\Scripts\\python.exe` (preferred), or run tests via Windows-native invocation `venv/Scripts/python.exe -m pytest ...` (no leading `./`). | `/bin/bash` is often missing on this Windows environment; using it causes false-negative tool failures and triggers GSD auto-mode safety stops even when tests would pass. | 2026-05-22 |

## Patterns

| # | Pattern | Where | Notes |
|---|---------|-------|-------|

## Lessons Learned

| # | What Happened | Root Cause | Fix | Scope |
|---|--------------|------------|-----|-------|
