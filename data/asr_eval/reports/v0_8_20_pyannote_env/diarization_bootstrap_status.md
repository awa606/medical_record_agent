# v0.8.19 说话人分离引擎环境准备报告

## 当前状态

| 引擎 | 状态 | 说明 |
| --- | --- | --- |
| pyannote community-1 | `blocked` | HF_TOKEN is not configured |
| 3D-Speaker | `blocked` | THREED_SPEAKER_PYTHON is missing or does not exist; THREED_SPEAKER_SCRIPT is missing or does not exist |

## pyannote 复测命令

```powershell
py -3.11 -m venv .venv-diarization
.\.venv-diarization\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.venv-diarization\Scripts\python -m pip install -r requirements-diarization-experimental.txt
.\.venv-diarization\Scripts\python -m pip install -r requirements.txt
$env:HF_TOKEN='<your local Hugging Face token>'
.\.venv-diarization\Scripts\python scripts\run_diarization_engine_compare.py --engines pyannote --reports-dir data\asr_eval\reports\v0_8_20_pyannote_measured
```

## 3D-Speaker 复测命令

```powershell
$env:THREED_SPEAKER_PYTHON='C:\path\to\3d-speaker\venv\Scripts\python.exe'
$env:THREED_SPEAKER_SCRIPT='C:\path\to\3d-speaker\diarize_wrapper.py'
python scripts\run_diarization_engine_compare.py --engines three_d_speaker --reports-dir data\asr_eval\reports\v0_8_19_three_d_speaker_measured
```

## 工程边界

- 本脚本只记录环境准备状态，不下载公开音频、不提交模型权重、不提交 HF_TOKEN。
- pyannote 和 3D-Speaker 缺失时记录为 blocked，不解释为模型效果差。
- AliMeeting 公开会议样本只用于多说话人分离评测，不代表医疗问诊效果。
