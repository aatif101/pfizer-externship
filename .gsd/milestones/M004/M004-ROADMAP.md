# M004: Real SDF Extraction Evaluation Hardening

**Vision:** Harden the real SDF extraction evaluation workflow so baseline and candidate runs can coexist, be inspected, costed, and compared without latest-write ambiguity, then add targeted visual fallback for suspicious fields using local stored page images.

## Success Criteria

- Extraction and compliance runs are preserved by run id without breaking latest-write compatibility.
- Compliance dashboard can select and label extraction runs clearly.
- Gemini extraction usage and estimated cost are captured as bounded metrics.
- Targeted visual fallback improves or honestly measures suspicious-field extraction without overwriting good grounded text values.
- A final real 5-document comparison is produced against existing baselines and candidates.
- Confidential artifacts remain local and ignored.
- All verification uses Windows-native commands only.

## Slices

- [x] **S01: Run scoped extraction history** `risk:high` `depends:[]`
  > After this: A test can persist two extraction runs for the same document and query both independently while existing latest-write repository behavior still works.

- [x] **S02: Compliance dashboard run selector** `risk:medium` `depends:[S01]`
  > After this: The Compliance tab can select a specific extraction run and clearly labels whether the user is viewing baseline, candidate, or latest compatibility state.

- [x] **S03: Gemini extraction usage observations** `risk:medium` `depends:[S01]`
  > After this: A mocked Gemini extraction persists bounded token and estimated-cost observations and exposes aggregate eval metrics without storing raw prompts or confidential data.

- [x] **S04: Targeted visual fallback extraction** `risk:high` `depends:[S01,S03]`
  > After this: A suspicious-field extraction can invoke visual fallback on stored page images, fill only eligible missing or suspicious fields, and preserve good grounded text values.

- [x] **S05: Real five document comparison and UAT** `risk:high` `depends:[S02,S04]`
  > After this: The local 5-SDF database has a final visual-fallback candidate eval run compared against the real text baseline and packet-aware candidates, with dashboard verification passing.

## Boundary Map

### S01 -> S02
Produces:
- Run-scoped extraction and compliance history query functions.
- Stable run summary metadata for dashboard selectors.
Consumes:
- Existing latest-write extraction and compliance repository compatibility.

### S01 -> S03
Produces:
- Extraction run identity and history persistence surfaces that usage observations can reference.
Consumes:
- Existing eval run and metric repository patterns.

### S03 -> S04
Produces:
- Bounded extraction usage observation contract and aggregate metric names.
Consumes:
- Gemini provider call boundaries and run identity.

### S01 and S03 -> S04
Produces:
- Run history and usage observation surfaces required by visual fallback.
Consumes:
- Existing extraction provider and pipeline contracts.

### S02 and S04 -> S05
Produces:
- Dashboard run selection and final visual-fallback candidate extraction behavior.
Consumes:
- Local real 5-document `compliance.db`, gold labels, and existing eval comparison patterns.
