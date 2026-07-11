# v0.8.8 两说话人 Diarization 评测汇总

> 本报告只覆盖 `fever_01` 与 `chest_pain_01` 两条两说话人课程样本；三说话人样本保持待补，不输出伪成绩。

## 样本状态

- 总样本项：3
- 已标注两说话人样本：2 / 2
- 已测结果数：2
- DER/JER 状态：not_available

| 样本 | 状态 | 说明 |
| --- | --- | --- |
| `chest_pain_01` | `annotated` | 已有人工 RTTM，并参与本轮评测 |
| `fever_01` | `annotated` | 已有人工 RTTM，并参与本轮评测 |
| `three_speaker_course_sample` | `pending_sample` | 用户选择本轮只做两说话人样本；不合成三说话人样本。 |

## 单样本结果

| 样本 | 引擎 | 状态 | speaker_count_error | boundary_f1 | mixed_utterance_rate | role_consistency | DER | JER | RTF | 报告 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |
| chest_pain_01 | `funasr_campp` | `measured` | 1 | 0.2944 | 0.3282 | 0.9078 | not_available | not_available | 0.0002 | `chest_pain_01_funasr_campp.json` |
| fever_01 | `funasr_campp` | `measured` | 0 | 0.4472 | 0.3258 | 0.8931 | not_available | not_available | 0.0004 | `fever_01_funasr_campp.json` |

## 依赖状态

| 引擎 | 状态 | 说明 |
| --- | --- | --- |
| `pyannote` | `skipped` | pyannote.audio is not installed |
| `three_d_speaker` | `skipped` | THREED_SPEAKER_PYTHON is not configured |
| `funasr_campp` | `measured_in_docker` | FunASR VAD + punctuation + CAM++ is the current production baseline. |

## 结论

- 本轮只引用 fever_01 与 chest_pain_01 两条两说话人课程样本。
- 两说话人样本平均 boundary_f1 为 0.3708，平均 role_consistency 为 0.9004。
- 三说话人样本仍为 pending_sample；不能把本轮结果扩展解释为三说话人成绩。
- pyannote 和 3D-Speaker 的缺依赖状态只说明本机未配置，不代表模型效果差。
