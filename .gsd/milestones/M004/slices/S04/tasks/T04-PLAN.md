---
estimated_steps: 8
estimated_files: 2
skills_used: []
---

# T04: Expose opt-in visual fallback wiring for extraction runs

skills_used: api-design, tdd, verify-before-complete

Why: The final S05 real five-document comparison needs a concrete way to run a visual-fallback candidate without changing existing text-only extraction defaults or latest-write compatibility.

Do:
1. Wire an opt-in visual fallback path through `src/extraction/cli.py`, such as a `--visual-fallback` flag that composes the existing Gemini text provider with the new Gemini visual provider only when explicitly requested.
2. Preserve default behavior for existing CLI commands: no visual provider is constructed unless the flag is set, and existing explicit `--run-id` propagation remains unchanged.
3. Extend `tests/test_extraction_cli.py` or add focused CLI tests proving the flag passes a visual provider into the pipeline, default runs remain text-only, and explicit run IDs still reach both text and visual stages.
4. Run the slice closeout gate set with Windows-native pytest commands. If recording GSD evidence, use `gsd_exec runtime=node` spawning `venv/Scripts/python.exe`; do not invoke `/bin/bash` or `runtime=bash`.

Done when: CLI tests prove opt-in composition for candidate runs, all prior pipeline/Gemini/usage/persistence tests still pass, and S05 has a real command path for visual-fallback evaluation.

## Inputs

- `src/extraction/cli.py`
- `src/extraction/pipeline.py`
- `src/extraction/gemini.py`
- `tests/test_extraction_cli.py`
- `tests/test_visual_fallback_pipeline.py`
- `tests/test_extraction_gemini_visual.py`
- `tests/test_extraction_usage_observations.py`
- `tests/test_eval_repository.py`

## Expected Output

- `src/extraction/cli.py`
- `tests/test_extraction_cli.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_extraction_cli.py tests/test_visual_fallback_pipeline.py tests/test_extraction_gemini_visual.py tests/test_extraction_usage_observations.py tests/test_eval_repository.py

## Observability Impact

Makes visual fallback an explicit run-mode in CLI usage, enabling run-scoped usage observations and history to distinguish text-only and visual-candidate runs.
