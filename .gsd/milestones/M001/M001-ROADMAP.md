# M001: Phase 2 Extraction and Compliance

**Vision:** Deliver the baseline structured extraction and compliance workflow on top of the completed Phase 1 ingestion foundation.

## Success Criteria

- Migration cleanup leaves no tracked local secrets.
- Python 3.11 venv is the documented and verified execution path.
- Phase 2 extraction stores required metadata with source evidence.
- Compliance risk levels are computed and visible to the user.
- Langfuse/tracing behavior remains non-fatal when credentials are absent.

## Slices

- [x] **S01: S01** `risk:medium` `depends:[]`
  > After this: Repo is on current GitHub main, local secrets are untracked, Python 3.11 editable install works, tests pass, and current GSD artifacts reflect migrated project state.

- [ ] **S02: Extraction contract and persistence** `risk:high` `depends:[S01]`
  > After this: A typed extraction schema can represent required SDF fields, source evidence, confidence, and review state for sample records.

- [ ] **S03: Baseline extraction pipeline** `risk:high` `depends:[S02]`
  > After this: Running extraction against sample PDFs produces structured metadata rows with page/source evidence or explicit abstentions.

- [ ] **S04: Compliance dashboard records** `risk:medium` `depends:[S03]`
  > After this: The Compliance tab shows document metadata, age, risk color, confidence, and source page links from SQLite.

## Boundary Map

Not provided.
