# System Architecture Sources

## 软件架构

- [当前架构说明](../../docs/architecture.md)：`static/*.html → FastAPI → API routers → MedicalRecordOrchestrator → LLM/ASR/Export → SQLite/local files`。
- [ASR 文件流](../../docs/asr_sse_file_stream.md)：ASR Session、上传和 SSE 事件。
- [角色校正](../../docs/asr_role_correction.md)：说话人与医患角色校正。
- [说话人角色策略](../../docs/speaker_diarization_role_strategy.md)：角色质量与策略边界。
- [API 能力契约](../../docs/api_capability_contract.md)：接口层能力与约束。

## 架构与流程图

- [产品开发生命周期 Draw.io](Sources/MediListen_Product_Development_Lifecycle.drawio)：可编辑的产品阶段流程图。
- [POC 四层架构答辩材料](../00_Project_Overview/Sources/Concept/MediListen_AI生成式电子病历辅助系统_20260730.pptx)：输入、AI 处理、应用和输出层的原始图示。

## 结构边界

当前前端是静态 Web 页面，并非 Flutter 客户端；AI 结果只能进入医生审核前的草稿和候选参考链路。真实 HIS/EMR、医院身份系统和专用硬件集成没有现有实施材料，保留为 TODO。
