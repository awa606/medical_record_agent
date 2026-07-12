# v0.8.17 真实多说话人 Diarization 引擎对比

- 样本：`three_speaker_alimeeting_01`
- 来源：AliMeeting Eval, CC BY-SA 4.0
- 边界：AliMeeting is a public meeting sample; it is used only to test multi-speaker diarization.
- 人工 RTTM speaker 数：`4`
- 人工 RTTM turn 数：`60`

| 引擎 | 状态 | turn 数 | speaker_count_error | boundary_f1 | mixed_utterance_rate | role_consistency | DER | JER | RTF | RSS 峰值 MB | 说明 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| pyannote_community_1 | `skipped` | - | - | - | - | - | - | - | - | - | HF_TOKEN is required for pyannote Community-1 |

## 结论

- 当前没有 measured 引擎；缺依赖或失败只说明本机环境未完成，不代表模型效果差。
- 会议样本只用于多说话人分离评测，不能作为中文医患问诊准确率结论。
