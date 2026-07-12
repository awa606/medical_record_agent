# v0.8.18 ASR 与 Diarization 对齐验证

## 目标

本轮目标是验证：当外部 diarization engine 能输出 speaker turn 时，系统能否用这些边界切分 FunASR 的长 ASR segment，降低医生和患者语句混在同一行的问题。

## 当前输入

- ASRResult：`data/asr_eval/reports/v0_8_13_three_speaker_measured/three_speaker_alimeeting_01_funasr_raw_asr_result.json`
- diarization turns report：`data/asr_eval/reports/v0_8_17_true_diarization_compare/funasr_campp_three_speaker_alimeeting_01.json`
- RTTM：`data/asr_eval/diarization_ground_truth/three_speaker_alimeeting_01.rttm`

## 实测结果

| 项目 | 结果 |
| --- | --- |
| 对齐状态 | skipped |
| 使用引擎 | funasr_campp |
| 跳过原因 | turns report has no hypothesis_turns; no external diarization boundary to apply |
| 上游状态 | failed |
| 上游原因 | engine returned no diarization turns for a non-empty RTTM reference |

## 证据文件

- `data/asr_eval/reports/v0_8_18_diarization_asr_alignment/alignment_summary.md`
- `scripts/apply_diarization_turns_to_asr_result.py`
- `tests/test_apply_diarization_turns_to_asr_result.py`

## 结论

对齐脚本和单元测试已经补齐：只要外部分离引擎能输出 speaker turn，系统可以按说话人边界拆分跨说话人 ASR segment。当前真实样本没有可用 turn，因此本轮按 skipped 记录，不生成伪造的对齐结果。

下一步是先补齐 pyannote 或 3D-Speaker 的可用环境，再把 measured 的 speaker turn 接入该对齐脚本复测 mixed utterance rate。
