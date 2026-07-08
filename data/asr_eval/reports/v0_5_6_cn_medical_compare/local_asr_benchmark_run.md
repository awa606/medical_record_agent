# 本地 ASR 多引擎评测运行记录

> 本记录用于 v0.5.6。它只说明哪些引擎在当前环境完成评测、哪些因依赖或配置缺失被跳过，不代表最终模型优劣。

## 运行信息

- 生成时间：2026-07-07T18:07:19+08:00
- 音频目录：`video`
- 标注目录：`data\asr_eval\ground_truth`
- 模式：`strict`
- 评测分层：`course_medical_cn`
- 分层说明：三条课程中文医患样本，是本项目 ASR 主评测，可用于医学关键词和流程效果分析。
- 样本数量：3

## 引擎状态

| 引擎 | 状态 | 报告 | 样本数 | 失败样本 | 说明 |
| --- | --- | --- | ---: | ---: | --- |
| funasr | measured | `funasr_report.csv` | 3 | 0 | completed |
| sensevoice | measured | `sensevoice_report.csv` | 3 | 0 | completed |

## 结论

- `measured` 表示当前环境完成了该引擎评测并生成 CSV。
- `smoke_measured` 表示无标注样本完成转写，只用于可用性冒烟测试。
- `skipped` 表示依赖、模型或配置缺失，本轮不评价该模型效果。
- `failed` 表示引擎已创建，但样本转写全部失败，需要进入 Debug Log 分析。
- `course_medical_cn` 是中文医患主评测；`public_en_smoke` 只用于可选多语种冒烟验证。
