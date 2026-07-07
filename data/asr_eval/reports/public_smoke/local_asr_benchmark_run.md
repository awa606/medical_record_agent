# 本地 ASR 多引擎评测运行记录

> 本记录用于 v0.5.3。它只说明哪些引擎在当前环境完成评测、哪些因依赖或配置缺失被跳过，不代表最终模型优劣。

## 运行信息

- 生成时间：2026-07-07T15:58:32+08:00
- 音频目录：`data\asr_eval\public_smoke\audio`
- 标注目录：`data\asr_eval\public_smoke\ground_truth`
- 模式：`smoke`
- 样本数量：5

## 引擎状态

| 引擎 | 状态 | 报告 | 样本数 | 失败样本 | 说明 |
| --- | --- | --- | ---: | ---: | --- |
| mock | measured_with_smoke | `mock_report.csv` | 5 | 0 | completed with measured and smoke-only samples |
| funasr | measured_with_smoke | `funasr_report.csv` | 5 | 0 | completed with measured and smoke-only samples |
| sensevoice | measured_with_smoke | `sensevoice_report.csv` | 5 | 0 | completed with measured and smoke-only samples |
| whisper | measured_with_smoke | `whisper_report.csv` | 5 | 0 | completed with measured and smoke-only samples |
| qwen3 | skipped | - | 0 | 0 | Could not read model from <PROJECT_ROOT>\.venv-asr\Lib\site-packages\nagisa/data/nagisa_v001.model |

## 结论

- `measured` 表示当前环境完成了该引擎评测并生成 CSV。
- `smoke_measured` 表示无标注样本完成转写，只用于可用性冒烟测试。
- `skipped` 表示依赖、模型或配置缺失，本轮不评价该模型效果。
- `failed` 表示引擎已创建，但样本转写全部失败，需要进入 Debug Log 分析。
