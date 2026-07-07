# v0.5.4 中文优先 ASR 评测报告

本报告用于解释 v0.5.4 的评测口径：Medical Record Agent 的目标场景是中文医患对话，因此课程中文医患样本是主评测；公开非医疗样本只用于验证 ASR 引擎可用性、ffmpeg/Whisper 解阻塞和多语种冒烟链路。

## 评测分层

| 分层 | 样本 | 用途 | 是否进入主结论 |
| --- | --- | --- | --- |
| `course_medical_cn` | `fever_01`、`chest_pain_01`、`snakebite_01` | 中文医患场景主评测，计算 CER、医学关键词召回、耗时和 RTF。 | 是 |
| `public_cn_smoke` | Qwen 官方 `asr_zh.wav` | 中文公开非医疗 smoke，只验证中文 ASR 可用性。 | 辅助证据 |
| `public_en_smoke` | Qwen 官方 `asr_en.wav`、Mini LibriSpeech 英文样本 | 可选多语种 smoke，验证 Whisper/ffmpeg 和多语种链路。 | 否 |

## 当前已完成结果

| 阶段 | 结果 | 说明 |
| --- | --- | --- |
| v0.5.2 | `mock/funasr/sensevoice=measured`，`whisper/qwen3=skipped` | 三条课程中文医患样本已完成 FunASR 和 SenseVoice CPU-only 实测。 |
| v0.5.3 | `mock/funasr/sensevoice/whisper=measured_with_smoke`，`qwen3=skipped` | 公开非医疗 smoke 已跑通；Whisper 通过便携 ffmpeg 解阻塞。 |
| v0.5.4 | 待复测 Qwen-ASR Python 3.12 环境 | 当前机器此前未检测到 Python 3.12；需要 `.venv-qwen-asr` 独立环境复测。 |

## 结论边界

- 英文公开样本不代表中文医患场景，不参与医生/患者角色区分结论。
- 非医疗公开样本不参与医学关键词召回结论，不生成医学诊断判断。
- 中文医患主评测仍以 `video/` 中三条课程样本和 `data/asr_eval/ground_truth/` 标注为准。
- Qwen-ASR 如果在 Python 3.12 中仍失败，应记录为依赖、模型下载、资源或网络阻塞，而不是模型效果差。

## 下一步命令

```powershell
py -3.12 -m venv .venv-qwen-asr
.\.venv-qwen-asr\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.venv-qwen-asr\Scripts\python -m pip install -r requirements-qwen3-asr.txt
.\.venv-qwen-asr\Scripts\python scripts\check_qwen_asr_env.py --json-output data\asr_eval\reports\qwen_asr_py312_check.json --markdown-output data\asr_eval\reports\qwen_asr_py312_check.md
.\.venv-qwen-asr\Scripts\python scripts\run_local_asr_benchmark.py --engines qwen3 --mode smoke --evaluation-profile public_cn_smoke --audio-dir data\asr_eval\public_smoke\audio --truth-dir data\asr_eval\public_smoke\ground_truth --reports-dir data\asr_eval\reports\qwen_py312
```
