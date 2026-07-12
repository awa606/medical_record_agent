# v0.8.17 真实多说话人分离引擎实测

## 目标

本轮目标是把公开真实多说话人音频接入统一评测流程，比较 FunASR CAM++、pyannote 和 3D-Speaker 的可用状态，并输出真实的 measured、skipped 或 failed 结论。

## 样本边界

- 样本：`three_speaker_alimeeting_01`
- 来源：AliMeeting Eval，CC BY-SA 4.0
- 场景：公开中文会议音频
- 用途：仅用于多说话人分离工程评测，不代表中文医患问诊准确率
- 人工 RTTM：`data/asr_eval/diarization_ground_truth/three_speaker_alimeeting_01.rttm`
- 人工 RTTM speaker 数：4
- 人工 RTTM turn 数：60

## 实测结果

| 引擎 | 状态 | 说明 |
| --- | --- | --- |
| FunASR CAM++ | failed | 当前 ASRResult 没有返回可对齐的 diarization turns，非空 RTTM 下不能计算有效分离指标。 |
| pyannote community-1 | skipped | 当前环境未安装 `pyannote.audio`。 |
| 3D-Speaker | skipped | 当前环境未配置 `THREED_SPEAKER_PYTHON` 和 `THREED_SPEAKER_SCRIPT`。 |

## 证据文件

- `data/asr_eval/reports/v0_8_17_true_diarization_compare/diarization_engine_compare_summary.md`
- `data/asr_eval/reports/v0_8_17_true_diarization_compare/dependency_status.md`
- `scripts/run_diarization_engine_compare.py`
- `scripts/check_diarization_dependencies.py`
- `tests/test_run_diarization_engine_compare.py`

## 结论

本轮没有把缺依赖或失败伪装成模型效果。真实结论是：当前本机环境还没有可 measured 的独立多说话人分离引擎；FunASR CAM++ 路线在该 AliMeeting 样本上没有输出可用 speaker turn。下一步必须安装 pyannote 或配置 3D-Speaker，再重新跑同口径评测。
