# v0.8.20 pyannote 隔离环境安装与令牌门禁

## 目标

上一轮 `v0.8.19` 只证明 pyannote 缺依赖。本轮进一步把 `.venv-diarization` 隔离环境创建并安装完成，让 pyannote 从“包缺失”推进到“依赖可导入，仅缺 HF_TOKEN”。

## 本轮完成

- 新增 `.gitignore` 规则：`.venv-diarization/`。
- 固定 `requirements-diarization-experimental.txt`：
  - `torch==2.2.2`
  - `torchaudio==2.2.2`
  - `numpy<2`
  - `pyannote.audio==3.4.0`
- 在 `.venv-diarization` 中安装 pyannote 研究依赖和项目基础依赖。
- 增强 `scripts/bootstrap_diarization_eval.py`，从简单 `find_spec` 改为真实 import probe，并记录版本。
- 使用隔离环境运行 pyannote 评测入口，结果到达预期的 `HF_TOKEN` 门禁。

## 实测环境

| 组件 | 结果 |
| --- | --- |
| Python | 3.11.6 |
| NumPy | 1.26.4 |
| torch | 2.2.2+cpu |
| torchaudio | 2.2.2+cpu |
| `torchaudio.AudioMetaData` | available |
| pyannote.audio | 3.4.0 |
| pyannote.metrics | 3.2.1 |
| HF_TOKEN | missing |

## 实测结论

pyannote 依赖已经可导入，项目评测脚本也能在 `.venv-diarization` 中运行。当前唯一阻塞是 `HF_TOKEN is required for pyannote Community-1`。这说明下一步不是继续修 Python 依赖，而是配置本地 Hugging Face token 并确认模型访问权限。

## 证据文件

- `data/asr_eval/reports/v0_8_20_pyannote_env/diarization_bootstrap_status.md`
- `data/asr_eval/reports/v0_8_20_pyannote_env/diarization_engine_compare_summary.md`
- `data/asr_eval/reports/v0_8_20_pyannote_env/pyannote_three_speaker_alimeeting_01.json`
- GitHub Issue [#19](https://github.com/awa606/medical_record_agent/issues/19)

## 下一步

配置本机 `HF_TOKEN` 后运行：

```powershell
$env:HF_TOKEN='<your local Hugging Face token>'
.\.venv-diarization\Scripts\python scripts\run_diarization_engine_compare.py --engines pyannote --reports-dir data\asr_eval\reports\v0_8_21_pyannote_measured
```

如果 pyannote 能输出 measured turns，再接入：

```powershell
python scripts\apply_diarization_turns_to_asr_result.py --turns-report data\asr_eval\reports\v0_8_21_pyannote_measured\pyannote_three_speaker_alimeeting_01.json --reports-dir data\asr_eval\reports\v0_8_21_pyannote_alignment
```

## 边界

- `.venv-diarization` 不提交。
- `HF_TOKEN` 不提交。
- AliMeeting 原始音频不提交。
- 本轮仍不输出 measured diarization 成绩；只说明依赖已准备到令牌门禁。
