# Diarization Recovery Acceptance Log - 2026-07-18

## Purpose

This log records the acceptance evidence after merging PR #56, `fix: prevent invented speakers and support manual diarization merging`.

It is an audit artifact only. It does not change production code, role thresholds, ASR evaluation data, disease packages, or provider behavior.

## Repository State

- #55 merged in `origin/main`: `2df07f336f335aee9e1232cdc74fe01e037c417a`.
- #56 squash-merged into `main`: `4dd97d3a76dd65bc43a354f8ac1b4680ec47fe0f`.
- #56 PR page showed the PR merged and the PR check passed.
- Local `gh`/git network access on this workstation could not resolve `github.com`, so GitHub connector APIs were used for merge and branch creation.

## #55 Clinical Fact Regression Confirmation

Validated with browser-side preview calls through `/static/doctor.html` and `fetch('/api/records/preview')`:

| Input | Expected state | Confirmed result |
| --- | --- | --- |
| `我发烧39°C` | Partial chief complaint and present illness | `发热，体温39℃（持续时间待补问）`; no invented duration or symptoms |
| `我感觉我发烧了，头很痛，39°C` | Partial fever + headache | `发热伴头痛（病程待补问）`; accompanying symptom `头痛` |
| `我没有发烧，只是头痛` | Absent fever fact, no positive fever complaint | Chief complaint remains `头痛（病程待补问）`; present illness records `患者否认发热` |
| `昨天发烧，今天已经退了` | Resolved fever, not active high fever | Present illness records `曾有发热，目前已缓解` |
| `医生：有没有发热？患者：没有` | No positive chief complaint | Chief complaint missing; present illness records `患者否认发热` |

Safety wording: in these regression cases, unsupported invented facts were 0. This does not prove global unsupported-generation rate is 0; field-level semantic support checking remains a future hardening task.

Forbidden invented facts checked in the short-fever case:

- `3天前`
- `淋雨`
- `铁锈色痰`
- `布洛芬`

Extraction metadata returned by preview:

- `actual_provider=mock`
- `model=mock-deterministic-extractor`
- `extraction_mode=clinical_fact_rules_v1`
- `fallback=false`

## #56 Diarization Recovery Confirmation

Synthetic ASRResult fixture used for recoverability validation because no large `fever.wav` is committed in the repository.

Before merge:

| Segment | Raw speaker | Normalized speaker | Role |
| --- | --- | --- | --- |
| `seg-1` | `spk1` | `spk1` | 医生 |
| `seg-2` | `spk2` | `spk2` | 患者 |
| `seg-3` | `spk3` | `spk3` | 待确认 |

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
- Each speaker remains manually recoverable as 医生 / 患者 / 陪同人员 / 其他 / 暂不确定.

Missing-label behavior:

- FunASR sentence_info entries without `spk` or `speaker` now normalize to `speaker_unassigned`.
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
