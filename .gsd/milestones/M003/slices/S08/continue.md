# Continue — post-M003 real SDF extraction hardening

## Last action

Saved and verified a local hardening pass for the real SDF baseline workflow: confidential DB snapshot was created under ignored `local_data/`, dashboard latest-write extraction state is visible, placeholder/date semantic guards were added, and verification passed with `239 passed, 20 warnings`.

## Next action

If continuing implementation, plan a new GSD milestone before editing: add run-scoped extraction/compliance storage, Gemini token/cost capture, and visual extraction fallback, then compare against `real-text-extraction-baseline-20260603T202400Z` and `packet-aware-guarded-extraction-candidate-20260603T211502Z`.

## Why

The current code prevents misleading latest-write dashboard state and blocks deterministic placeholder/date false positives, but the measured real-text pipeline still cannot recover visually present certificate values from page images. The next meaningful capability is run-scoped persistence plus visual fallback, not more prompt-only tuning.

## Open threads

- Local ignored snapshot exists at `local_data/snapshots/compliance_after_packet_candidate.db`.
- Latest guarded candidate run in local `compliance.db`: `packet-aware-guarded-extraction-candidate-20260603T211502Z`.
- Guarded candidate macro F1 is `0.222`, below the real text baseline `0.269`, but `doc_type` improved to `0.889` F1.
- Compliance tab currently displays latest persisted rows and warns that historical baselines/candidates live in Eval.

## Do not

- Do NOT commit or push `compliance.db`, `.env`, `local_data/`, PDFs, page images, screenshots, or DB snapshots.
- Do NOT treat `Delivery Date` as `effective_date` or `Retest Date` as `expiry_date`.
- Do NOT overwrite the real baseline run meaning; candidate experiments must stay identifiable.
- Do NOT invoke `/bin/bash` or use `gsd_exec` runtime `bash` in this Windows repo; use `gsd_exec` runtime `node` spawning `venv\\Scripts\\python.exe` or Windows-native `venv/Scripts/python.exe`.
