# API 能力契约：v1.2

本文档记录 `v1.2` 新增的接口化能力。目标是让当前医疗问诊原型中的核心能力可以被其他页面、脚本或未来其他领域项目复用，而不强制进入医生端完整任务流。

## 设计原则

- 不改变现有医生端流程、ASR 流程、审核流程和导出流程。
- 新接口默认无副作用：不创建 Task、不写入最终病历、不允许直接导出。
- 所有诊断和治疗建议仍是候选提示，必须医生确认。
- 不返回 API Key、模型缓存路径、真实患者数据或运行数据库内容。

## 能力发现

`GET /api/capabilities`

用途：返回当前系统可复用能力清单，包括接口路径、方法、是否依赖模型和迁移说明。

典型用途：
- 外部系统启动时发现可用能力。
- 课程汇报时说明系统不是单一页面，而是可复用 API 服务。
- 后续迁移到其他领域时确认哪些模块可复用、哪些模块需要替换。

## 字段抽取

`POST /api/records/extract-fields`

输入：
- `conversation_text`：问诊文本或其他领域的对话文本。
- `source`：来源标记，默认 `external_api`。
- `segments`：可选转写段，用于证据定位。

输出：
- `fields`：结构化字段。
- `candidate_diagnoses`：候选诊断。
- `treatment_plan`：建议检查、用药边界、风险提醒和补问建议。
- `diagnosis_evidence` / `evidence_links`：证据文本与可定位片段。
- `quality_report`：字段完整度、证据覆盖、医生确认要求。

边界：不创建任务、不进入审核、不允许导出。

## 草稿生成

`POST /api/records/build-draft`

输入：
- `fields`：结构化字段。
- `allow_export`：默认 `false`，仅用于安全校验边界检查。

输出：
- `draft`：病历草稿文本。
- `safety_check`：安全校验结果。
- `quality_report`：质量评估。

边界：不保存草稿到 SQLite，不创建导出文件。

## 质量评估

`POST /api/records/quality`

输入：
- `fields`：结构化字段。
- `draft`：可选草稿文本。
- `safety_check`：可选安全校验结果。

输出：
- `quality_report`：字段质量、缺失项、证据不足项、候选诊断质量、治疗建议安全边界和下一步建议。

用途：其他领域迁移时，可以替换字段抽取模型，但继续复用质量报告的接口形态。

## 领域迁移说明

可直接复用：
- FastAPI 路由结构。
- ASR/SSE 会话模式。
- Task 审核和导出保护。
- 无副作用预览与质量评估接口模式。
- Docker 本地运行和 GitHub 版本管理流程。

需要替换：
- 字段 schema。
- 领域知识库和规则。
- Prompt 模板。
- 前端字段标签和展示文案。
- 质量规则中的必填项和风险边界。
