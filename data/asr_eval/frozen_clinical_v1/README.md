# v1.5 冻结临床多说话人评测集

本目录用于 #44 的冻结评测资产。当前入库的是轻量模拟 fixture，不包含真实患者隐私数据，也不把大音频直接放入普通 Git。

## 文件

- `manifest.json`：冻结样本清单、split、hash、标注版本和场景类型。
- `annotations/`：逐样本标注，包含 transcript、RTTM/speaker turns、speaker-role 映射、医学关键词、核心病历字段和证据段。
- `fixtures/`：轻量文本 fixture，用于验证 manifest hash 和评测脚本可重复运行。

## 运行

```powershell
python scripts/evaluate_speaker_role_dataset.py --manifest data/asr_eval/frozen_clinical_v1/manifest.json --output data/asr_eval/reports/v1_5_frozen_clinical_baseline.json
```

后续真实或较大的模拟录音应使用外部位置和 hash 记录在 manifest 中，不直接提交到普通 Git。
