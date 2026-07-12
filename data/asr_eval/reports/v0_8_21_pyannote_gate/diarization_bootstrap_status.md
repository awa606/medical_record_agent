# Diarization Engine Bootstrap Report

## Current Status

| Engine | Status | Reason |
| --- | --- | --- |
| pyannote community-1 | `blocked` | HF_TOKEN is not configured |
| 3D-Speaker | `blocked` | THREED_SPEAKER_PYTHON is missing or does not exist; THREED_SPEAKER_SCRIPT is missing or does not exist |

## pyannote Retest Commands

```powershell
py -3.11 -m venv .venv-diarization
.\.venv-diarization\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.venv-diarization\Scripts\python -m pip install -r requirements-diarization-experimental.txt
.\.venv-diarization\Scripts\python -m pip install -r requirements.txt
$env:HF_TOKEN='<your local Hugging Face token>'
.\.venv-diarization\Scripts\python scripts\run_diarization_engine_compare.py --engines pyannote --reports-dir data\asr_eval\reports\v0_8_21_pyannote_measured
```

## 3D-Speaker Retest Commands

```powershell
$env:THREED_SPEAKER_PYTHON='C:\path\to\3d-speaker\venv\Scripts\python.exe'
$env:THREED_SPEAKER_SCRIPT='C:\path\to\3d-speaker\diarize_wrapper.py'
python scripts\run_diarization_engine_compare.py --engines three_d_speaker --reports-dir data\asr_eval\reports\v0_8_21_three_d_speaker_measured
```

## Engineering Boundaries

- This script records environment readiness only.
- It does not download public audio, commit model weights, or commit HF_TOKEN.
- Missing pyannote or 3D-Speaker dependencies are recorded as blocked, not as poor model quality.
- AliMeeting public meeting samples are used only for diarization evaluation, not for medical consultation accuracy.
