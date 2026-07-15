# v1.5 冻结临床多说话人评测集基线报告

- 数据版本：`frozen_clinical_v1`
- Schema 版本：`speaker_role_eval_manifest_v1`
- 样本数：6
- calibration/test：3 / 3

## 指标

- 角色准确率：1.0
- 自动通过覆盖率：0.75
- 高置信错误数：0
- 人工确认率：0.25
- speaker 数量准确率：1.0
- 混合语句率：0.05
- 医学关键词召回率：1.0

## 场景覆盖

- `interruption`：1
- `noisy_background`：1
- `overlap`：1
- `single_reader_counterexample`：1
- `three_party_family`：1
- `two_party_clean`：1
