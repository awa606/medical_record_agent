# v0.8.13 三说话人 ASRResult 实测摘要

- 样本：`three_speaker_alimeeting_01.wav`
- 来源：AliMeeting Eval，CC BY-SA 4.0
- 场景边界：公开会议音频，只用于多说话人分离工程评测，不代表医疗问诊效果。
- 状态：`measured`
- 引擎：`funasr-paraformer-zh`
- audio_duration_seconds: `240.0`
- elapsed_seconds: `26.152`
- rtf: `0.109`
- rss_peak_mb: `4237.45`
- cpu_process_percent: `358.72`
- raw_segments: `1`
- enhanced_segments: `1`
- raw_speaker_count: `1`
- enhanced_speaker_count: `1`
- Raw ASRResult：`data\asr_eval\reports\v0_8_13_three_speaker_measured\three_speaker_alimeeting_01_funasr_raw_asr_result.json`
- Enhanced ASRResult：`data\asr_eval\reports\v0_8_13_three_speaker_measured\three_speaker_alimeeting_01_funasr_enhanced_asr_result.json`
- Diarization 评测：当前 ASRResult 未返回可对齐的 `diarization_turns`，因此三说话人 RTTM 对齐评测记录为 `failed`，失败原因见 `funasr_campp_raw_metrics.json`。
