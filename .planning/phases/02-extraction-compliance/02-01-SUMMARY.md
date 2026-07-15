---
phase: "02-extraction-compliance"
plan: "01"
slug: strict-gemini-provider-contract
status: complete
completed: 2026-07-15
requirements:
  - EXTRACT-01
---

# Phase 2 Plan 01 — Strict Gemini Provider Contract Summary

## Outcome

Text and visual Gemini extraction now share one fixed-six, fail-closed Pydantic
contract. Provider output is revalidated locally before it can enter domain DTOs,
model and usage identities are auditable, retries have one bounded owner, and July
2026 standard synchronous costs are calculated from exact model keys.

## What changed

- Replaced the provider-controlled field list and handwritten prompt schema with
  private strict Pydantic models for exactly `doc_type`, `vendor_name`,
  `manufacturing_date`, `effective_date`, `revision_date`, and `expiry_date`.
- Added bounded finite confidence/bbox values, exact ISO date parsing, compact
  evidence, and value-or-abstention semantic invariants. Missing or extra keys,
  malformed JSON, contradictory abstentions, and invalid nested values yield a
  complete safe abstention result.
- Passed the strict model's generated JSON Schema through
  `response_json_schema` for both text and visual requests. Prompts retain the
  pharmaceutical packet/date/vendor policy but no longer duplicate JSON shape or
  send content-derived document, filename, or run identifiers.
- Added requested, response-resolved, and pricing model identities plus candidate,
  thought, and total-token counters to content-free usage metadata.
- Added an immutable exact-price registry: Gemini 2.5 Flash uses $0.30 input and
  $2.50 output/thinking per million tokens; Gemini 3.5 Flash uses $1.50 and $9.00.
  Unknown identities retain token counts with null price/cost.
- Bounded the configurable adapter retry count to 1..5, added randomized
  exponential backoff with a no-sleep test seam, and configured the Google SDK to
  make one attempt so retry multiplication cannot occur.
- Bounded `google-genai` to the tested `>=2.7,<3.0` compatibility range and
  confirmed a lazy real client can be constructed without a network call.
- Sanitized public provider failures and removed exception cause chains so raw
  SDK messages, content, paths, images, payloads, and keys cannot surface through
  the adapter boundary.

## Verification evidence

- Focused provider/schema/usage gate:
  `venv\Scripts\python.exe -m pytest tests\test_extraction_provider_gemini.py tests\test_extraction_gemini_visual.py tests\test_extraction_gemini_usage.py -q --tb=short`
  — **47 passed** in 4.58s.
- Real installed-SDK config construction using
  `types.GenerateContentConfig(response_json_schema=...)` — **passed**, with all
  six fixed properties present and required.
- Lazy `google.genai.client.Client` construction with SDK retries disabled —
  **passed**.
- `venv\Scripts\python.exe -m pip check` — **no broken requirements found**.

## Deviation resolved during review

The original plan used the legacy `response_schema=PydanticModel` path. Recording
fake clients accepted it, but a real google-genai 2.7 construction check failed
before HTTP because the SDK attempted to parameterize the Pydantic v2 class.
Google's supported `response_json_schema=Model.model_json_schema()` path works
with the installed SDK and preserves the exact same strict local Pydantic source
of truth. The plan, research, patterns, implementation, and tests were updated to
record this evidence rather than preserve a green-but-nonfunctional seam.

## Remaining scope

Plan 02 owns durable manifest/resume lifecycle. Plan 03 owns grounded evidence,
usage persistence, confidence/critic/HITL integration, deterministic date risk,
and the frozen extraction-quality gate.
