# Qwen3-ASR 分样本评测记录

> 本记录用于 v0.5.7。每条样本在独立子进程中运行，长音频崩溃时保留已完成样本和失败原因。

## 运行信息

- 生成时间：2026-07-08T09:49:42+08:00
- 音频目录：`C:\mra_qwen_runtime\course_medical_cn\audio`
- 标注目录：`C:\mra_qwen_runtime\course_medical_cn\ground_truth`
- 报告目录：`data\asr_eval\reports\v0_5_6_cn_medical_compare\qwen3`
- 样本数量：3
- 成功样本：3
- 失败样本：0

## 样本状态

| 样本 | 状态 | 退出码 | 耗时秒 | 报告 | 错误 |
| --- | --- | ---: | ---: | --- | --- |
| snakebite_01 | measured | 0 | 143.108 | `samples/snakebite_01/snakebite_01_qwen3_sample.csv` | - |
| fever_01 | measured | 0 | 179.672 | `samples/fever_01/fever_01_qwen3_sample.csv` | - |
| chest_pain_01 | measured | 0 | 244.378 | `samples/chest_pain_01/chest_pain_01_qwen3_sample.csv` | - |

## 结论

- `measured` 表示该样本完成同口径 CER、关键词召回、RTF、CPU/RSS 记录。
- `failed` 表示子进程异常退出、超时或没有生成可合并 CSV，不代表 Qwen3-ASR 模型效果差。
- 长音频失败时，优先记录资源与稳定性问题，后续再评估切片策略或 GPU/边缘端部署。
