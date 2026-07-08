# v0.5.9 长音频切片 ASR 评测运行记录

> 本记录用于验证 16/30 分钟中文医患拼接音频在切片转写后的稳定性。该结果只代表当前开发机，不代表医院 PC 最终性能。

## 运行信息

- 生成时间：2026-07-08T13:38:16+08:00
- 音频目录：`data\asr_eval\long_audio_stability\audio`
- 标注目录：`data\asr_eval\long_audio_stability\ground_truth`
- 切片时长：`300` 秒
- 样本数量：2
- 模式：`strict`

## 引擎状态

| 引擎 | 状态 | 报告 | 成功样本 | 失败样本 | 说明 |
| --- | --- | --- | ---: | ---: | --- |
| sensevoice | measured | `sensevoice_chunked_report.csv` | 2 | 0 | all chunked samples completed |
| funasr | measured | `funasr_chunked_report.csv` | 2 | 0 | all chunked samples completed |

## 判读边界

- `measured` 表示所有切片均转写并合并成功，且有人工标注可计算 CER。
- `failed` 表示至少一个样本没有得到完整合并结果；具体失败切片见 `chunk_status/` JSON。
- 切片结果用于稳定性验证，不改变默认 ASR 模型，也不证明医学诊断正确性。
