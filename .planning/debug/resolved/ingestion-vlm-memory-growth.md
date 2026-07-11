---
status: resolved
trigger: "The ingestion regression test fails because three sequential Docling VLM ingests grow process RSS by about 2.17 GB while reloading model weights for every document."
created: "2026-07-11"
updated: "2026-07-11T04:36:12-04:00"
---

# Ingestion VLM Memory Growth

## Symptoms

- Expected behavior: sequential PDF ingestion reuses or releases heavyweight Docling model state so process memory remains bounded and documents do not pay repeated model-load latency.
- Actual behavior: `tests/test_ingest.py::test_memory_no_leak` reports 2173.9 MB RSS growth across three one-page ingests, and logs show all 470 model tensors loading on every call.
- Error message: `AssertionError: Memory grew 2173.9 MB across 3 ingests (C3 leak?)`.
- Timeline: reproduced on 2026-07-11 against commit `f04f14d`; the converter module currently recreates `DocumentConverter` per document.
- Reproduction: `venv\\Scripts\\python.exe -m pytest tests\\test_ingest.py::test_memory_no_leak -vv --durations=5`.

## Current Focus

- hypothesis: confirmed with an important correction — the 2.17 GB assertion mostly measured legitimate cold imports/model allocation, while recreating `DocumentConverter` bypassed Docling's instance-local pipeline cache and reloaded 470 tensors per document without producing a proven linear RSS leak.
- test: separate the first cold conversion from three steady-state conversions, pin one converter construction through the public `convert_pdf` interface, and verify real Docling behavior plus offline-safe module import.
- expecting: one bounded cold-start allocation, a single converter/model construction per process, and less than 200 MB RSS growth across three steady-state conversions.
- next_action: none — fix verified and session resolved.
- tdd_checkpoint: lifecycle regression failed at 3 constructions versus 1 before the fix, then passed after process-scoped lazy reuse was implemented.

## Evidence

- timestamp: "2026-07-11T04:22:55-04:00"
  observation: full reproduction failed after 31.63 seconds with 2173.9 MB RSS growth and three separate weight-loading progress bars.
  source: `tests/test_ingest.py::test_memory_no_leak`
- timestamp: "2026-07-11T04:27:00-04:00"
  observation: installed Docling 2.91.0 keeps `initialized_pipelines` on each `DocumentConverter`; `_get_pipeline()` reuses a VLM pipeline only within that converter instance.
  source: runtime inspection of `docling.document_converter.DocumentConverter.__init__` and `_get_pipeline`
- timestamp: "2026-07-11T04:28:00-04:00"
  observation: a controlled persistent-converter probe measured a 1448.4 MB first-conversion allocation followed by only 59.0 MB total RSS growth over conversions 2-4, with one weight load.
  source: isolated real-Docling process probe against `tests/fixtures/sample.pdf`
- timestamp: "2026-07-11T04:30:00-04:00"
  observation: the cold-versus-steady RSS regression passed before the lifecycle fix, disproving the stronger claim of linear live-memory leakage; the public lifecycle regression then failed with 3 converter constructions where 1 was required.
  source: `tests/test_ingest.py::test_memory_no_leak` and `tests/test_converter.py::test_convert_pdf_initializes_heavy_pipeline_once_per_process`
- timestamp: "2026-07-11T04:36:12-04:00"
  observation: after the fix, a fresh real-Docling probe measured 2187.3 MB cold-start growth and 57.2 MB total growth over three steady-state conversions; only one 470-tensor loading pass appeared.
  source: public `src.pipeline.converter.convert_pdf` probe against `tests/fixtures/sample.pdf`
- timestamp: "2026-07-11T04:36:12-04:00"
  observation: fresh Windows verification passed all 9 converter and ingestion tests in 36.63 seconds.
  source: `venv\\Scripts\\python.exe -m pytest tests\\test_converter.py tests\\test_ingest.py -q --durations=10`

## Eliminated

- hypothesis: rasterization is the dominant memory leak
  reason: each test PDF is one 1275x1651 PNG; the observed multi-gigabyte growth and repeated 470-tensor loading align with the VLM lifecycle, not the image buffer.
- hypothesis: each per-document model reload leaves another full live model in memory and causes linear steady-state RSS growth
  reason: once cold allocation was measured separately, three additional conversions grew only about 59 MB even before the fix; PyTorch reused allocator memory, although the repeated model initialization remained a real latency and churn defect.

## Resolution

- root_cause: the regression sampled RSS before deferred Docling/Torch imports and VLM initialization, misclassifying the legitimate roughly 2.19 GB cold allocation as a leak. Independently, `convert_pdf` recreated `DocumentConverter` for every document even though Docling's VLM pipeline cache belongs to the converter instance, forcing repeated 470-tensor initialization and avoidable latency.
- fix: cache the lazily built `DocumentConverter` for the process, keep Docling/Torch imports deferred, retain transient-object/CUDA-cache cleanup, and rewrite the RSS regression to measure the cold start separately from three steady-state calls. Add subprocess-isolated public-interface tests for single construction and offline-safe import.
- verification: lifecycle TDD test RED at 3 constructions versus 1 and GREEN after the fix; fresh real probe measured 2187.3 MB cold allocation and 57.2 MB across the next three conversions; fresh focused suite passed 9/9 tests in 36.63 seconds.
- files_changed: `src/pipeline/converter.py`, `src/pipeline/ingest.py`, `tests/test_converter.py`, `tests/test_ingest.py`, `.planning/debug/resolved/ingestion-vlm-memory-growth.md`
