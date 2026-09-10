# Hardware Sources

## 已确认事实

- POC 没有自研专用硬件整机；可在普通电脑或服务器、现代浏览器、麦克风或已有音频文件条件下运行。
- 现有本地部署和硬件基线材料位于 [普通医院 Windows 电脑配置基线](../../docs/普通医院Windows电脑配置基线.md)、[本地模型边缘评测](../../docs/local_model_edge_benchmark.md) 和 [Docker 部署说明](../../docs/docker_local_deploy.md)。
- 输入层的 USB 麦克风、预录音频与文本兜底路径记录在 [POC 答辩材料](../00_Project_Overview/Sources/Concept/MediListen_AI生成式电子病历辅助系统_20260730.pptx)。

## EVT 待验证

- 边缘设备的离线运行、模型缓存、连续录音、散热、噪声条件和备份。
- 麦克风阵列或其他专用终端是否必要。
- 目标硬件 BOM、成本上限、性能指标和验收证据。

在这些验证完成前，不应将“边缘计算”或“硬件终端”表述为已完成产品能力。
