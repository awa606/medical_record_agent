# 本地模型实验

语义 LoRA 实验只学习“转写文本 → 可由输入支持的事实与字段状态”，不训练诊断或治疗建议。数据由 `field_disease_pack_v1` 的 60 个合成病例派生，固定使用 1–30 训练、31–40 验证、41–60 冻结测试。

```powershell
python scripts/prepare_semantic_lora_dataset.py `
  --output-dir .artifacts/training/semantic_lora_v1 `
  --manifest-output .artifacts/training/semantic_lora_v1/dataset_manifest.json

python scripts/run_semantic_lora_smoke.py `
  --dataset-dir .artifacts/training/semantic_lora_v1 `
  --dataset-manifest .artifacts/training/semantic_lora_v1/dataset_manifest.json `
  --output-dir .artifacts/training/semantic_lora_v1/run `
  --report-json .artifacts/training/semantic_lora_v1/run/report.json `
  --report-markdown .artifacts/training/semantic_lora_v1/run/report.md
```

首次准备 `Qwen/Qwen2.5-0.5B-Instruct` 时显式加入 `--allow-model-download`。模型缓存、LoRA适配器、JSONL和生成文本不进入Git；Git只保存脚本、数据清单哈希与聚合指标。
