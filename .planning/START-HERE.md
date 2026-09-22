# Start here: build toward submission

Prepared 2026-09-22. Planning is ready; the product is not yet submission-ready.

## First command

```text
/gsd-plan-phase 2.1
```

Codex skill spelling, if the slash command is unavailable: `$gsd-plan-phase 2.1`.

Phase 2.1 already has CONTEXT.md, so there is no need to repeat discovery or ask the owner to restate the assignment. Read `.planning/SUBMISSION-READINESS.md` as the submission contract. Plan only recovery work first. The initial tracer is one synthetic development document generated and verified on Windows, followed by a complete frozen benchmark and passing required offline suite.

## Then

```text
/gsd-execute-phase 2.1
/gsd-verify-work 2.1
/gsd-plan-phase 3
```

At Phase 3, inspect existing 03-00..05 plans and Phase 2.1 verification first. Reconcile the 03-00 prerequisite work instead of recreating it. Replan only unexecuted/affected tasks with current research. Do not execute all phases unattended merely because this handoff exists.

## Ordered route

| Phase | Deliverable |
|---|---|
| 2.1 | Recover reproducible benchmark, environment and offline test gate |
| 3 | Real hybrid text retrieval and claim-grounded RAG |
| 4 | Isolated evaluation runs, measured metrics and verified dashboard |
| 5 | Revalidate existing visual foundation on a real GPU |
| 5.1 | Wire visual retrieval into Chat; finish critic/confidence work |
| 6 | Integrated workflow, bounded agentic behavior, HITL and traces |
| 7 | Final holdout report, fresh Colab, documentation and actual video |

Later unplanned phases have phase-local CONTEXT.md or submission addenda pointing at the shared contract. Use `/gsd-plan-phase <number>`, then execute and verify. Phase 5 already has historical plans/summaries: verify and plan gaps rather than rebuilding completed work.

## Preserve when resuming

- Work in `C:/Users/smati/VS Code Projects/pfizer-externship` on the current working branch. Do not switch to main and lose the newer work.
- `.planning/` is active; `.gsd/` contains historical work. Preserve old artifacts as evidence.
- Existing uncommitted dependency/benchmark/agent configuration changes predate this planning task. Do not reset or blindly include them in planning commits.
- Do not expose `.env`, private PDFs, local databases or supplier details in output, commits or demo artifacts.
- Use PowerShell/Node/Python on Windows; never `/bin/bash` verification.
- Model/API access, paid evaluation acknowledgement, GPU session, independent review and video recording are explicit later checkpoints. No fabricated test pass, live score, human review or recording.

## Review baseline

644 passed / 10 benchmark failures / 7 skipped / 1 deselected in the ordinary selected suite. Socket-disabled RAGAS also needs Windows asyncio compatibility repair. No implementation fixes were made during the review or roadmap preparation. Historical 17-query scores are exploratory; the release must be measured from the final implementation and frozen data.
