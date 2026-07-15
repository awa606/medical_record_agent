# frozen_clinical_v1

`frozen_clinical_v1` 是 #44 / PR #49 引入的最小回归数据集。它用于 CI、schema 校验、hash 校验和评测脚本 smoke test，不作为生产 speaker-role 自动识别准确率证据。

当前目录只有 6 条轻量文本 fixture：

- 覆盖双人、三人、单人朗读、噪声、打断和重叠场景。
- `audio_ref` 指向 `.txt` fixture，不是真实音频输入。
- 旧评测脚本读取 annotation 中的 `baseline_prediction`，只能验证 fixture 与预置预测的一致性。

因此，报告中的 `role_accuracy=1.0` 不能写成系统真实性能结论。

## 文件

- `manifest.json`：最小回归样本清单、split、hash、标注版本和场景类型。
- `annotations/`：逐样本标注，包含 transcript、RTTM/speaker turns、speaker-role 映射、医学关键词、核心病历字段和证据段。
- `fixtures/`：轻量文本 fixture，用于验证 manifest hash 和脚本可重复运行。

## 运行

```powershell
python scripts/evaluate_speaker_role_dataset.py --manifest data/asr_eval/frozen_clinical_v1/manifest.json --output data/asr_eval/reports/v1_5_frozen_clinical_baseline.json
```

生产 Provider 基线、真实 synthetic WAV/FLAC、truth/prediction 分离和统计置信区间由 `data/asr_eval/executable_clinical_v1/` 承接。
