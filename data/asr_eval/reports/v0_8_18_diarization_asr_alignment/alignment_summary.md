# v0.8.18 Diarization 与 ASR 对齐报告

- 状态：`skipped`
- 引擎：`funasr_campp`
- ASRResult：`C:\Users\AWA007\Desktop\开题报告\病历\medical_record_agent\data\asr_eval\reports\v0_8_13_three_speaker_measured\three_speaker_alimeeting_01_funasr_raw_asr_result.json`
- turns 报告：`data\asr_eval\reports\v0_8_17_true_diarization_compare\funasr_campp_three_speaker_alimeeting_01.json`
- reason: `turns report has no hypothesis_turns; no external diarization boundary to apply`
- source_status: `failed`
- source_reason: `engine returned no diarization turns for a non-empty RTTM reference`

说明：本报告只验证外部 diarization 边界能否降低 ASR 混合语句，不代表 AliMeeting 会议样本的医疗问诊效果。
