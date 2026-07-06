# 版本演进记录

本文记录 Medical Record Agent 从课程原型到研究级 AI 工程系统的标准版本线。版本线以能力里程碑为准，每个里程碑必须能追溯到 Issue、日志和验证结果。

## 版本时间线

| 版本 | 阶段 | 说明 | 归档目录 |
| --- | --- | --- |
| v0.1 | Basic ASR pipeline | 建立音频上传、ASR 转写、ASRResult 结构和音频到病历入口。 | `versions/v0.1_basic_asr_pipeline/` |
| v0.2 | SSE streaming | 建立任务状态、步骤记录和 SSE 事件流，支持前端实时追踪。 | `versions/v0.2_sse_streaming/` |
| v0.2.1 | ASR session SSE | 新增 MP3/WAV ASR 会话接口，支持前端中间转写栏按 segment 实时显示。 | `versions/v0.2_sse_streaming/` |
| v0.3 | Role separation | 建立医生/患者角色分离、ASR 角色策略和人工校正提示。 | `versions/v0.3_role_separation/` |
| v0.4 | Medical reasoning | 建立病历字段抽取、草稿生成、安全校验、候选诊断和医生审核边界。 | `versions/v0.4_medical_reasoning/` |
| v1.0 | Deployable system | 建立可本地运行、可选本地模型、日志、版本、Issue 和 PR 工作流的可交接系统。 | `versions/v1.0_deployable_system/` |

## 当前状态

当前代码已覆盖 `v0.1` 到 `v0.4` 的主要工程能力，并在 `v0.2.1` 增加 ASR 会话级 SSE 文件流转写。`v1.0` 的重点是部署说明、版本证据、日志纪律、模型评测和协作流程。

## 版本管理规则

- 每个功能、修复、研究或重构任务必须先有 GitHub Issue。
- 每天至少维护一个 `/logs/daily/YYYY-MM-DD.md` 工作日志。
- Bug 修复必须在 `/logs/debug/` 下记录问题、根因、修复和验证。
- 每个里程碑必须在 `versions/` 下维护目录和 README。
- 版本目录 `versions/` 只归档关键阶段材料和证据索引，不存放大体积数据、模型权重或隐私数据。
