# Qwen3-ASR 分样本评测记录

> 本记录用于 v0.5.7。每条样本在独立子进程中运行，长音频崩溃时保留已完成样本和失败原因。

## 运行信息

- 生成时间：2026-07-08T11:37:22+08:00
- 音频目录：`C:\mra_qwen_runtime\long_audio_stability\audio`
- 标注目录：`C:\mra_qwen_runtime\long_audio_stability\ground_truth`
- 报告目录：`data\asr_eval\reports\v0_5_8_long_audio_stability\qwen3`
- 样本数量：2
- 成功样本：2
- 失败样本：0

## 样本状态

| 样本 | 状态 | 退出码 | 耗时秒 | 报告 | 错误 |
| --- | --- | ---: | ---: | --- | --- |
| long_16min_course_cn | measured | 0 | 597.921 | `samples/long_16min_course_cn/long_16min_course_cn_qwen3_sample.csv` | - |
| long_30min_course_cn | measured | 0 | 1879.603 | `samples/long_30min_course_cn/long_30min_course_cn_qwen3_sample.csv` | - |

## 结论

- `measured` 表示该样本完成同口径 CER、关键词召回、RTF、CPU/RSS 记录。
- `failed` 表示子进程异常退出、超时或没有生成可合并 CSV，不代表 Qwen3-ASR 模型效果差。
- 长音频失败时，优先记录资源与稳定性问题，后续再评估切片策略或 GPU/边缘端部署。
