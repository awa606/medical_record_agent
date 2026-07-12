# v0.8.17-v0.8.18 能力证据追踪补充

| 版本 | Issue | 能力 | 代码入口 | 测试证据 | 报告证据 | 当前结论 |
| --- | --- | --- | --- | --- | --- | --- |
| v0.8.17 | [#16](https://github.com/awa606/medical_record_agent/issues/16) | 真实多说话人分离引擎对比 | `scripts/run_diarization_engine_compare.py`、`scripts/evaluate_diarization.py`、`scripts/check_diarization_dependencies.py` | `tests/test_run_diarization_engine_compare.py`、`tests/test_diarization_evaluator.py`、`tests/test_speaker_diarization.py` | `data/asr_eval/reports/v0_8_17_true_diarization_compare/` | FunASR CAM++ failed；pyannote/3D-Speaker skipped；未伪造 measured 结果。 |
| v0.8.18 | [#17](https://github.com/awa606/medical_record_agent/issues/17) | ASR 与 diarization turn 对齐 | `scripts/apply_diarization_turns_to_asr_result.py` | `tests/test_apply_diarization_turns_to_asr_result.py` | `data/asr_eval/reports/v0_8_18_diarization_asr_alignment/` | 对齐能力已具备；当前因无 hypothesis_turns 真实跳过。 |

## 前端验收口径

- 上传真实音频后，稳定转写优先展示 `说话人 A/B/C`。
- 不再把跨说话人的长句直接强行标成医生或患者。
- 角色映射应在整位 speaker 级别统一确认，再同步替换为医生、患者、其他。
- SSE 断连恢复能力沿用 v0.8.11 的事件日志和 `Last-Event-ID` 验收结论。

## 后续动作

1. 安装并复测 pyannote，必要时配置 `HF_TOKEN`。
2. 配置 3D-Speaker 独立运行脚本。
3. 对 AliMeeting 样本重新输出 DER、JER、boundary F1、mixed utterance rate、RTF 和 RSS。
4. 将 measured speaker turns 接入 `apply_diarization_turns_to_asr_result.py`，复测混合语句率。
