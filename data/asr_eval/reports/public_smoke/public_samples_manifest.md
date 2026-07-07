# 中文优先公开 ASR 冒烟测试样本记录

> 本记录用于 v0.5.4。音频和标注文本只保存在本地忽略目录，不提交 GitHub。

## 评测分层

| 分层 | 用途 | 是否进入中文医患主结论 |
| --- | --- | --- |
| `course_medical_cn` | 三条课程中文医患样本，作为本项目 ASR 主评测。 | 是 |
| `public_cn_smoke` | 中文公开样本，只验证中文 ASR 可用性。 | 只作为辅助证据 |
| `public_en_smoke` | 英文公开样本，只验证多语种/Whisper/ffmpeg 冒烟链路。 | 否 |

## 样本清单

| 样本 | 语言 | 分层 | 优先级 | 是否有标注 | 是否医疗 | 角色结论 | 来源 | 许可证/说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen_asr_zh | zh | public_cn_smoke | 中文公开冒烟样本 | 否 | none | 不用于医生/患者角色正确性结论 | Qwen3-ASR official repository sample | Sample distributed by Qwen3-ASR project for model usage examples; use as smoke-test reference only. |
| qwen_asr_en | en | public_en_smoke | 可选多语种冒烟样本 | 否 | none | 不进入中文医患主结论 | Qwen3-ASR official repository sample | Sample distributed by Qwen3-ASR project for model usage examples; use as smoke-test reference only. |
| mini_librispeech_5694-64038-0000 | en | public_en_smoke | 可选多语种冒烟样本 | 是 | none | 不进入中文医患主结论 | Mini LibriSpeech dev-clean-2, OpenSLR SLR31 | CC BY 4.0 |
| mini_librispeech_5694-64038-0001 | en | public_en_smoke | 可选多语种冒烟样本 | 是 | none | 不进入中文医患主结论 | Mini LibriSpeech dev-clean-2, OpenSLR SLR31 | CC BY 4.0 |
| mini_librispeech_5694-64038-0002 | en | public_en_smoke | 可选多语种冒烟样本 | 是 | none | 不进入中文医患主结论 | Mini LibriSpeech dev-clean-2, OpenSLR SLR31 | CC BY 4.0 |

## 边界

- 中文医患课程样本才是本项目 ASR 主评测对象。
- 非医疗公开样本只用于 ASR 可用性、耗时和通用转写冒烟测试。
- 英文公开样本只保留为可选多语种 smoke，不进入中文医患效果结论。
- 非医疗样本不用于医学诊断、医学关键词召回或医生/患者角色正确性结论。
