# 语义 LoRA 实验证据（2026-09-14）

本次在开发机 RTX 5070 Laptop GPU 上，对 `Qwen/Qwen2.5-0.5B-Instruct` 执行了 12 个 LoRA 优化步。数据严格按病例编号划分为 30 条训练、10 条验证、20 条冻结测试，监督目标只含可支持事实和字段状态。

结果显示：验证损失从 2.229292 降至 0.462052，冻结集 Schema 完整率从 0% 提升至 100%，事实召回从 0% 提升至 55%，字段状态准确率从 0% 提升至 39.17%。LoRA 输出仍有 16 个无依据事实，因此候选门禁为 `NEEDS_VALIDATION`，没有替换生产模型。

- `dataset_manifest.json`：60 个源病例的路径、SHA256与固定划分，未复制病例正文。
- `semantic_lora_smoke.json` / `.md`：训练环境、损失、冻结集逐例指标和聚合结果。
- `adapter_artifacts.json`：本地适配器文件大小与SHA256；权重本身未提交。

执行对应 Git SHA：`5c790a93bffd66ffe96cee6bee6886710662992a`。
