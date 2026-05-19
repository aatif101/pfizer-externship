# Decisions Register

<!-- Append-only. Never edit or remove existing rows.
     To reverse a decision, add a new row that supersedes it.
     Read this file at the start of any planning or research phase. -->

| # | When | Scope | Decision | Choice | Rationale | Revisable? | Made By |
|---|------|-------|----------|--------|-----------|------------|---------|
| D001 | M001 migration cleanup | environment | Supported local runtime for development and verification | Use Python 3.11 project virtual environment for all project commands. | The global Python 3.14 environment has incompatible Pydantic/pydantic-settings packages, while the project venv on Python 3.11 supports editable install and test execution. | Yes | collaborative |
| D002 | M001 migration cleanup | security | Handling local provider/model settings | Remove settings.local.json from Git tracking and add it to .gitignore. | A token-like value had been tracked previously. Local provider keys and machine-specific model settings must remain outside version control. | No for secrets; Yes for local config file naming | collaborative |
| D003 | M001 migration cleanup | packaging | Python package build backend | Switch build backend from setuptools.backends.legacy:build to setuptools.build_meta. | The legacy backend failed editable installation in the Python 3.11 venv; the standard setuptools.build_meta backend supports editable installs successfully. | Yes | agent |
| D004 | M001 migration cleanup | workflow | GSD 1.0 project state migration strategy | Seed current .gsd PROJECT, REQUIREMENTS, and ROADMAP from the GSD 1.0 .planning artifacts. | The repo was created with GSD 1.0 .planning artifacts; current workflows need current-format root artifacts, requirement rows, and milestone/slice roadmap entries. | Yes | agent |
