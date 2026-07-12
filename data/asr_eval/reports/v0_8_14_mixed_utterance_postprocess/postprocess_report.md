# v0.8.14 混合语句后处理报告

## 结论

本轮已经在 `enhance_speaker_diarization()` 中加入“按 diarization turn 拆分跨说话人 ASR segment”的后处理能力，并用单元测试验证：

- 一个 ASR segment 如果覆盖两个不同 speaker turn，会拆成多条稳定 utterance。
- 拆分后保留原始文本来源 `original_text`，并给新 segment 增加稳定 `segment_id`。
- 如果没有 diarization turn，不会凭空拆分或伪造说话人边界。

## AliMeeting 实测结果

样本：`three_speaker_alimeeting_01.wav`  
来源：AliMeeting Eval，CC BY-SA 4.0。  
用途：公开会议场景的多说话人分离工程评测，不代表医疗问诊效果。

当前 FunASR ASRResult 实测只返回：

- `raw_segments = 1`
- `raw_speaker_count = 1`
- `diarization_turns = 0`

因此 `scripts/evaluate_diarization.py` 对 RTTM 标注的评测结果为：

- `status = failed`
- `reason = engine returned no diarization turns for a non-empty RTTM reference`

这说明本轮后处理能力已经具备，但当前 FunASR 输出没有提供可用于拆分的说话人时间边界。后续需要切换或补充专门 diarization 管线，例如 pyannote 或 3D-Speaker，再将其 turn 送入该后处理。

## 对产品的影响

- 不再把没有边界证据的长 ASR 段强行拆成医生/患者。
- 前端应先显示“说话人 A/B/C”，完成全局映射后再统一显示医生、患者、其他。
- 病历预览只能消费稳定 utterance，不能消费混合临时文本。

