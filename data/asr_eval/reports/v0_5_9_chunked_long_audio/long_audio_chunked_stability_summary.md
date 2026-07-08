# v0.5.9 长音频切片稳定性结论摘要

生成日期：2026-07-08

## 测试边界

- 本轮使用 `v0.5.8` 已生成的 16 分钟和 30 分钟课程中文医患拼接音频。
- 样本只用于长音频稳定性、资源占用和切片恢复验证，不代表真实门诊平均问诊时长。
- 默认切片长度为 300 秒，即 5 分钟。
- 本轮不切换默认 ASR 模型，不修改医生端业务流程。

## 结果对比

| 模型 | 16 分钟切片状态 | 30 分钟切片状态 | 30 分钟 CER | 30 分钟关键词召回 | 30 分钟 RTF | 30 分钟峰值 RSS | 结论 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| SenseVoice | measured，4 个切片，0 失败 | measured，6 个切片，0 失败 | 0.170886 | 0.266667 | 0.173731 | 3254.68 MB | v0.5.8 的 30 分钟整文件失败可通过 5 分钟切片规避。 |
| FunASR | measured，4 个切片，0 失败 | measured，6 个切片，0 失败 | 0.203343 | 0.333333 | 0.208204 | 5024.94 MB | 继续作为长音频稳定 fallback。 |

## 与 v0.5.8 整文件结果对比

| 模型 | v0.5.8 整文件 30 分钟 | v0.5.9 5 分钟切片 30 分钟 | 判断 |
| --- | --- | --- | --- |
| SenseVoice | failed，`[Errno 22] Invalid argument` | measured | 切片策略有效，后续 v0.6 可把切片作为长音频 fallback。 |
| FunASR | measured，RTF 0.231400，RSS 4819.74 MB | measured，RTF 0.208204，RSS 5024.94 MB | 两种方式均稳定，切片后 RTF 略好但 RSS 略高。 |
| Qwen3-ASR | measured，但 30 分钟 RTF 0.955827，RSS 18909.36 MB | 本轮未复测 | 保留为研究路线，不作为普通医院 PC 默认模型。 |

## 当前工程结论

- SenseVoice 可以进入 `v0.6` 默认候选，但长音频必须走切片转写。
- FunASR 仍是更稳妥的长音频 fallback。
- 普通医院 16GB Windows PC 预估部署时，应优先采用 FunASR/SenseVoice，并开启长音频切片；Qwen3-ASR 建议放到边缘端或独显工作站复测。
- 后续产品化时，前端应显示“转写中、当前切片、总切片、失败原因”，避免长音频等待过程不可见。

## 证据文件

- `data/asr_eval/reports/v0_5_9_chunked_long_audio/chunked_asr_benchmark_run.md`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/local_model_benchmark.md`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/sensevoice_chunked_report.csv`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/funasr_chunked_report.csv`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/chunk_status/`
