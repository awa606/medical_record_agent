# Diarization Recovery Acceptance Log - 2026-07-18

## Purpose

This log records acceptance evidence after PR #56, `fix: prevent invented speakers and support manual diarization merging`, was merged.

This is an audit artifact only. It does not change production code, role thresholds, ASR evaluation data, disease packages, provider behavior, or audio assets.

## Repository State

- #55 merged in `origin/main`: `2df07f336f335aee9e1232cdc74fe01e037c417a`.
- #56 squash-merged into `main`: `4dd97d3a76dd65bc43a354f8ac1b4680ec47fe0f`.
- #56 PR page showed the PR merged and the PR check passed.
- Local `gh` and `git` network access on this workstation could not resolve `github.com`, so GitHub connector APIs were used for merge and branch creation.

## #55 Clinical Fact Regression Confirmation

Validated with browser-side preview calls through `/static/doctor.html` and `fetch('/api/records/preview')`.

The original Chinese inputs are recorded with escaped Unicode to keep this audit file ASCII-safe:

| Case | Input | Confirmed result |
| --- | --- | --- |
| short fever | `\u6211\u53d1\u70e739\u00b0C` | Partial chief complaint and present illness; fever and 39C are retained; no invented duration or symptoms. |
| fever + headache | `\u6211\u611f\u89c9\u6211\u53d1\u70e7\u4e86\uff0c\u5934\u5f88\u75db\uff0c39\u00b0C` | Partial fever + headache; accompanying symptom headache is retained. |
| absent fever | `\u6211\u6ca1\u6709\u53d1\u70e7\uff0c\u53ea\u662f\u5934\u75db` | Fever is treated as an absent fact; no positive fever complaint is generated. |
| resolved fever | `\u6628\u5929\u53d1\u70e7\uff0c\u4eca\u5929\u5df2\u7ecf\u9000\u4e86` | Fever is treated as previously present and currently resolved, not active high fever. |
| doctor asks, patient denies | `\u533b\u751f\uff1a\u6709\u6ca1\u6709\u53d1\u70ed\uff1f\u60a3\u8005\uff1a\u6ca1\u6709` | No positive chief complaint is generated; present illness records fever denial. |

Safety wording: unsupported invented facts were 0 in these regression cases. This does not prove the global unsupported-generation rate is 0. Field-level semantic support checking remains a future hardening task.

Forbidden invented facts checked in the short-fever case:

- `3 days before`
- `rain exposure`
- `rust-colored sputum`
- `ibuprofen`

Extraction metadata returned by preview:

- `actual_provider=mock`
- `model=mock-deterministic-extractor`
- `extraction_mode=clinical_fact_rules_v1`
- `fallback=false`

## #56 Diarization Recovery Confirmation

Synthetic ASRResult fixture was used for recoverability validation because no large `fever.wav` is committed in the repository.

Before merge:

| Segment | Raw speaker | Normalized speaker | Role |
| --- | --- | --- | --- |
| `seg-1` | `spk1` | `spk1` | doctor |
| `seg-2` | `spk2` | `spk2` | patient |
| `seg-3` | `spk3` | `spk3` | pending |

Manual recovery action:

```json
{
  "source_speaker": "spk3",
  "target_speaker": "spk2",
  "reviewer": "doctor",
  "note": "manual diarization merge from doctor UI"
}
```

Expected and confirmed behavior:

- Speaker count changes from 3 to 2.
- All `spk3` segments are rewritten to `spk2`.
- `speaker_assignments` and `diarization_turns` are rewritten consistently.
- `conversation_text` is regenerated from merged segments.
- `role_quality` is recalculated after merge.
- If the merged role remains unconfirmed, record generation stays gated with 409.
- After role confirmation, record generation can continue successfully.
- Each speaker remains manually recoverable as doctor, patient, companion, other, or pending.

Missing-label behavior:

- FunASR `sentence_info` entries without `spk` or `speaker` now normalize to `speaker_unassigned`.
- Missing labels include audit fields: `speaker_raw=null`, `speaker_normalized=speaker_unassigned`, `diarization_source=missing_label`.
- Five unlabeled segments no longer become five invented people.

## Local Validation Commands

Run in clean worktree `medical_record_agent_clinical_fact_p0` on branch `codex/prevent-invented-speakers-and-merge-diarization`:

```powershell
$env:PYTHONPATH=(Get-Location).Path
pytest -q tests\test_clinical_fact_extraction.py tests\test_records_api.py
pytest -q tests\test_asr_factory.py tests\test_asr_sessions_api.py tests\test_doctor_manual_speaker_merge_static.py
pytest -q
node --check static\doctor.js
git diff --check
```

Observed results:

- Clinical fact focused tests: 18 passed.
- Diarization focused tests: 36 passed, 1 warning.
- Full test suite: 229 passed, 1 warning.
- `node --check static/doctor.js`: passed.
- `git diff --check`: passed.
- Local `/health`: `200 {"status":"ok"}`.
- Browser clinical fact preview smoke: passed.
- Browser manual diarization merge controls smoke: passed.

## Boundary

This evidence confirms recoverability for missing speaker labels and manual speaker merge. It does not implement automatic voiceprint similarity merging. Automatic merging remains a separate risk-sensitive feature because true three-person consultations must not be collapsed into two speakers without evaluated thresholds.
