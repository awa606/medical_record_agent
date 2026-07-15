# executable_clinical_v1

`executable_clinical_v1` 是 #50 的可执行 speaker-role 评测集。它用于生产 Provider 基线和 #41 阈值校准前置验证，不修改生产阈值，也不代表已经发布 `v1.5.0`。

## 数据边界

- 23 条本地 synthetic WAV 样本，全部由 Windows 本地 TTS 从模拟问诊脚本生成。
- 不包含真实患者隐私数据。
- 音频位于 `audio/`，通过 Git LFS 跟踪；普通 Git 只保存 manifest、truth annotation、prediction artifact、脚本和报告。
- truth annotation 与 prediction artifact 完全分离，annotation 中禁止出现 `baseline_prediction`、`prediction`、`speaker_decisions`。

## 场景覆盖

- 10 条双人医生/患者问诊。
- 5 条医生/患者/家属三人问诊。
- 3 条单人朗读反例。
- 5 条噪声、打断、重叠或组合挑战样本。

当前 split 为 calibration 12 条、test 11 条。#41 只能使用 calibration 选择阈值，test 只用于最终验收。

## 文件

- `manifest.json`：样本 id、场景类型、split、音频路径、sha256、时长、speaker 数、标注路径和标注版本。
- `annotations/*.truth.json`：真实转写、RTTM/speaker turns、speaker-role 映射、医学关键词、核心病历字段、证据段和隐私声明。
- `predictions/<provider>/*.prediction.json`：由 Provider 生成或导出的独立预测结果。
- `data/asr_eval/reports/executable_clinical_v1_rules.json`：当前 rules Provider baseline。

## Provider Prediction Contract

每个 speaker 决策必须包含：

- `provider`
- `provider_version`
- `policy_version`
- `git_commit`
- `raw_confidence`
- `calibrated_confidence`
- `reason_code`
- `action`: `auto_accept | needs_review | blocked`

Mock 只能用于 smoke，不计入产品准确率。报告会用 `counts_as_product_accuracy=false` 标出。

## 运行

生成 rules prediction artifact 并输出报告：

```powershell
python scripts/evaluate_executable_speaker_role_dataset.py `
  --manifest data/asr_eval/executable_clinical_v1/manifest.json `
  --provider rules `
  --generate-predictions `
  --prediction-dir data/asr_eval/executable_clinical_v1/predictions/rules `
  --output data/asr_eval/reports/executable_clinical_v1_rules.json
```

只读取已有 Provider prediction artifact：

```powershell
python scripts/evaluate_executable_speaker_role_dataset.py `
  --manifest data/asr_eval/executable_clinical_v1/manifest.json `
  --provider rules `
  --prediction-dir data/asr_eval/executable_clinical_v1/predictions/rules `
  --output data/asr_eval/reports/executable_clinical_v1_rules.json
```

校准模式必须限定 calibration split：

```powershell
python scripts/evaluate_executable_speaker_role_dataset.py `
  --manifest data/asr_eval/executable_clinical_v1/manifest.json `
  --provider rules `
  --split calibration `
  --calibrate `
  --output data/asr_eval/reports/executable_clinical_v1_rules_calibration.json
```

## 当前口径

当前报告是 rules Provider 在 synthetic transcript/prediction artifact 上的可执行基线。它比 `frozen_clinical_v1` 更接近生产评测流程，但仍不能替代真实环境临床验证，也不能用于直接宣布默认阈值策略已经达标。#41 必须在本数据集合并后单独处理。
