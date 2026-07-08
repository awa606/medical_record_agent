# v0.5.8 长音频稳定性结论摘要

生成日期：2026-07-08

## 测试边界

- 本轮样本为课程中文医患音频拼接，并补少量静音到 16 分钟和 30 分钟。
- 16 分钟只作为待验证的使用场景假设，30 分钟作为压力测试场景；二者都不代表中国门诊平均问诊时长。
- 本轮重点验证模型能否完成长音频、RTF、RSS、CPU 和失败原因；CER 只作为同一拼接标注下的工程参考。

## 样本

| 样本 | 目标时长 | 实际时长 | 用途 |
| --- | ---: | ---: | --- |
| `long_16min_course_cn.wav` | 960 秒 | 960.0 秒 | 接近较长问诊场景的稳定性验证 |
| `long_30min_course_cn.wav` | 1800 秒 | 1799.999 秒 | 极端/压力场景稳定性验证 |

## 模型结果

| 模型 | 样本 | 状态 | CER | 关键词召回 | RTF | 峰值 RSS MB | 结论 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| FunASR | 16 分钟 | measured | 0.189779 | 0.333333 | 0.257964 | 4658.45 | 可完成，资源较稳 |
| FunASR | 30 分钟 | measured | 0.197014 | 0.333333 | 0.231400 | 4819.74 | 可完成，适合作为稳定 fallback |
| SenseVoice | 16 分钟 | measured | 0.172639 | 0.266667 | 0.175227 | 2712.36 | 16 分钟表现最好，资源占用低 |
| SenseVoice | 30 分钟 | failed | - | - | - | - | 失败：`[Errno 22] Invalid argument`，需 Debug |
| Qwen3-ASR | 16 分钟 | measured | 0.873169 | 0.000000 | 0.509354 | 14870.71 | 可跑完，但准确率和内存不适合作默认 |
| Qwen3-ASR | 30 分钟 | measured | 0.907498 | 0.000000 | 0.955827 | 18909.36 | 接近实时且内存高，不适合普通医院 PC 默认路线 |

## 当前判断

- **默认交付路线**：FunASR/SenseVoice 继续作为 v0.6 医生端产品化的主要候选，其中 FunASR 长音频更稳，SenseVoice 需要排查 30 分钟失败。
- **Qwen3-ASR 路线**：已证明可以在本机 CPU-only 跑完 16/30 分钟，但 CER、关键词召回和 RSS 不适合作为当前默认模型；保留为研究候选。
- **普通医院 Windows PC 预估**：16GB 内存可优先尝试 FunASR/SenseVoice；30 分钟长音频和多模型评测建议 32GB 内存；Qwen3-ASR 推荐独显或边缘端环境复测。
- **后续必须补充**：真实医院电脑实机采集、真实或更贴近问诊场景的长音频样本、SenseVoice 30 分钟失败 Debug Log。

## 关联文件

- 样本清单：`data/asr_eval/reports/v0_5_8_long_audio_stability/long_audio_samples_manifest.md`
- 机器汇总：`data/asr_eval/reports/v0_5_8_long_audio_stability/long_audio_stability.md`
- Qwen3 分样本记录：`data/asr_eval/reports/v0_5_8_long_audio_stability/qwen3/qwen3_split_run.md`
