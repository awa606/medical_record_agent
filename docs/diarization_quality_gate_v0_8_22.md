# v0.8.22 说话人分离质量门禁说明

## 目标

本轮不是继续优化 UI，而是补上说话人分离结果的质量门禁。核心原则是：**只有通过质量门禁的 diarization 结果，才允许进入自动医生/患者角色映射候选**。如果模型没有输出有效说话人段、依赖缺失、token 缺失、混合语句率过高或边界质量太差，系统必须明确记录为阻塞或拒绝，不能伪装成可用结果。

对应 GitHub Issue：[ #21 ](https://github.com/awa606/medical_record_agent/issues/21)

## 门禁指标

当前门禁先采用工程可解释阈值：

| 指标 | 阈值 | 用途 |
| --- | --- | --- |
| `mixed_utterance_rate` | `<= 0.30` | 控制一条转写里混入多个说话人的比例 |
| `boundary_f1` | `>= 0.50` | 判断说话人边界是否基本可用 |
| `speaker_count_error` | `<= 1` | 判断说话人数估计是否偏离过大 |

门禁结论分为：

- `candidate_for_role_mapping`：可作为后续自动角色映射候选。
- `reject_for_role_mapping`：已测但质量不达标，不能自动映射医生/患者。
- `blocked`：未测、依赖缺失、token 缺失或未生成有效结果。

## 当前实测结论

报告位置：

- `data/asr_eval/reports/v0_8_22_quality_gate/diarization_engine_compare_summary.md`
- `data/asr_eval/reports/v0_8_22_quality_gate_pyannote_env/diarization_engine_compare_summary.md`
- `data/asr_eval/reports/v0_8_22_alignment_quality_gate/alignment_summary.md`

当前结论：

- FunASR CAM++ 在 AliMeeting 三/多人样本上没有输出可评估 diarization turns，因此被 `blocked`。
- pyannote 在主环境中记录为未安装；在 `.venv-diarization` 中可进入依赖检查，但缺少 `HF_TOKEN`，因此仍被 `blocked`。
- 3D-Speaker 尚未配置 `THREED_SPEAKER_PYTHON`，因此被 `blocked`。
- 当前没有任何引擎通过 `candidate_for_role_mapping` 门禁，因此不能把自动分离结果作为可靠的医生/患者映射依据。

## 前端影响

本轮不改医生端 UI。前端展示继续沿用当前逻辑：

- 转写中仍可显示 `说话人 A/B/C` 或已有角色。
- 系统不能因为某个分离引擎返回 failed/skipped 就自动显示医生/患者。
- 后续正式生成病历前，仍需要人工或全局角色映射确认。

## 下一步

1. 配置 `HF_TOKEN` 后复测 pyannote。
2. 配置 3D-Speaker 独立运行环境后复测。
3. 若任一引擎通过质量门禁，再接入前端全局角色映射确认。
4. 若没有引擎通过门禁，则继续保留“说话人 A/B/C + 全局确认”的稳妥交付路线。
