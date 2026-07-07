# 本地 ASR 多引擎评测运行记录

> 本记录用于 v0.5.1。它只说明哪些引擎在当前环境完成评测、哪些因依赖或配置缺失被跳过，不代表最终模型优劣。

## 运行信息

- 生成时间：2026-07-07T13:26:21+08:00
- 音频目录：`data\asr_eval\audio`
- 标注目录：`data\asr_eval\ground_truth`
- 样本数量：1

## 引擎状态

| 引擎 | 状态 | 报告 | 样本数 | 失败样本 | 说明 |
| --- | --- | --- | ---: | ---: | --- |
| mock | measured | `mock_report.csv` | 1 | 0 | completed |
| funasr | skipped | - | 0 | 0 | FunASR import failed. Please check ASR dependencies with `python scripts/check_funasr_env.py` and install optional dependencies with `pip install -r requirements-asr.txt`. Original error: ModuleNotFoundError("No module named 'funasr'") |
| qwen3 | skipped | - | 0 | 0 | Qwen3-ASR dependencies are not installed. Please install requirements-qwen3-asr.txt |

## 结论

- `measured` 表示当前环境完成了该引擎评测并生成 CSV。
- `skipped` 表示依赖、模型或配置缺失，本轮不评价该模型效果。
- `failed` 表示引擎已创建，但样本转写全部失败，需要进入 Debug Log 分析。
