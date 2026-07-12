# v0.8.19 说话人分离引擎环境准备

## 目标

`v0.8.17` 已经证明当前本机没有可 measured 的真实多说话人分离引擎。`v0.8.19` 的目标是补齐下一次真实复测的环境准备脚本和可执行命令，让 pyannote 或 3D-Speaker 配置完成后可以直接复测。

## 当前检查结果

| 引擎 | 当前状态 | 原因 |
| --- | --- | --- |
| pyannote community-1 | blocked | `pyannote.audio` 未安装，`HF_TOKEN` 未配置。 |
| 3D-Speaker | blocked | `THREED_SPEAKER_PYTHON` 和 `THREED_SPEAKER_SCRIPT` 未配置。 |

## 新增文件

- `requirements-diarization-experimental.txt`：可选研究依赖，只建议安装到隔离环境。
- `scripts/bootstrap_diarization_eval.py`：检查 pyannote、3D-Speaker、HF_TOKEN 和本地路径，并生成复测命令。
- `tests/test_bootstrap_diarization_eval.py`：验证 blocked/ready 两类状态。
- `data/asr_eval/reports/v0_8_19_diarization_bootstrap/diarization_bootstrap_status.md`：本机实际检查报告。

## 推荐 pyannote 复测路径

```powershell
py -3.11 -m venv .venv-diarization
.\.venv-diarization\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.venv-diarization\Scripts\python -m pip install -r requirements-diarization-experimental.txt
$env:HF_TOKEN='<your local Hugging Face token>'
.\.venv-diarization\Scripts\python scripts\run_diarization_engine_compare.py --engines pyannote --reports-dir data\asr_eval\reports\v0_8_19_pyannote_measured
```

## 推荐 3D-Speaker 复测路径

```powershell
$env:THREED_SPEAKER_PYTHON='C:\path\to\3d-speaker\venv\Scripts\python.exe'
$env:THREED_SPEAKER_SCRIPT='C:\path\to\3d-speaker\diarize_wrapper.py'
python scripts\run_diarization_engine_compare.py --engines three_d_speaker --reports-dir data\asr_eval\reports\v0_8_19_three_d_speaker_measured
```

## 边界

- 本轮不提交模型权重、音频、HF_TOKEN、虚拟环境或下载缓存。
- 缺依赖状态记录为 blocked，不代表模型效果差。
- AliMeeting 样本只用于多说话人分离工程评测，不代表医疗问诊场景。

## 下一步

配置 pyannote 或 3D-Speaker 后，重新跑同口径评测，拿到 measured speaker turns，再接入 `scripts/apply_diarization_turns_to_asr_result.py` 复测混合语句率。
