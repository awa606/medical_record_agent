# Debug Log：SenseVoice 30 分钟长音频失败

日期：2026-07-08  
阶段：v0.5.8 长音频稳定性测试

## Problem

`sensevoice-small` 在 `long_30min_course_cn.wav` 上失败，`run_local_asr_benchmark.py` 记录错误：

```text
[Errno 22] Invalid argument
```

## Steps To Reproduce

```powershell
.\.venv-asr\Scripts\python scripts\run_local_asr_benchmark.py `
  --engines sensevoice `
  --mode strict `
  --evaluation-profile course_medical_cn `
  --audio-dir data\asr_eval\long_audio_stability\audio `
  --truth-dir data\asr_eval\long_audio_stability\ground_truth `
  --reports-dir data\asr_eval\reports\v0_5_8_long_audio_stability
```

## Expected vs Actual

Expected：
- 16 分钟和 30 分钟长音频均完成转写，并输出 CER、RTF、RSS、CPU。

Actual：
- 16 分钟样本完成。
- 30 分钟样本失败，CSV 中记录 `failed` 和 `[Errno 22] Invalid argument`。

## Root Cause

未最终确认。当前只能判断为 SenseVoice/FunASR pipeline 在 30 分钟拼接 WAV 上的长音频稳定性或文件读取边界问题。FunASR 和 Qwen3-ASR 均可读取同一 30 分钟文件，因此音频文件本身不是完全不可读。

## Fix

本轮不修改第三方模型逻辑。后续排查方向：

1. 对 30 分钟音频做 5 分钟或 10 分钟切片后逐片转写。
2. 用 `ffprobe` 检查 WAV header、采样率、声道和时长。
3. 直接调用 SenseVoice engine 最小脚本，区分是文件读取失败、模型推理失败还是结果后处理失败。
4. 若切片可稳定完成，v0.6 长音频采用切片合并策略。

## Verification

当前验证结果：

- FunASR 16/30 分钟均 `measured`。
- SenseVoice 16 分钟 `measured`，30 分钟 `failed`。
- Qwen3-ASR 16/30 分钟均 `measured`，但 CER 和 RSS 不适合作为默认模型。

## v0.5.9 Follow-up Fix

新增 5 分钟切片转写与结果合并后复测：

- SenseVoice 30 分钟切片：`measured`，6 个切片，0 个失败，CER `0.170886`，RTF `0.173731`，RSS 峰值 `3254.68 MB`。
- FunASR 30 分钟切片：`measured`，6 个切片，0 个失败，CER `0.203343`，RTF `0.208204`，RSS 峰值 `5024.94 MB`。

当前判断：

- v0.5.8 的 SenseVoice 30 分钟失败可通过切片规避。
- 根因仍不修改第三方模型内部逻辑，工程修复采用“长音频切片 + 结果合并”。
- v0.6 医生端产品化应显示切片进度、当前切片状态和失败原因。

关联报告：

- `data/asr_eval/reports/v0_5_8_long_audio_stability/long_audio_stability_summary.md`
- `data/asr_eval/reports/v0_5_8_long_audio_stability/sensevoice_report.csv`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/long_audio_chunked_stability_summary.md`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/sensevoice_chunked_report.csv`
