# 系统架构

本文描述 Medical Record Agent 的工程结构和运行链路，用于课程汇报、开发交接和后续维护。

## 架构概览

Medical Record Agent 是一个面向医学问诊场景的 AI 生成式电子病历辅助系统。系统以 FastAPI 为后端入口，提供 ASR、SSE、医学对话结构化、医生/患者角色分离、医学知识推理、可选本地模型接入、医生审核和导出能力；前端通过静态页面调用 API；运行数据默认落在本地 SQLite 与 `data/` 目录。

```text
static/*.html
  -> FastAPI app.main
  -> app.api routers
  -> MedicalRecordOrchestrator
  -> LLM / ASR / Export services
  -> SQLite + local runtime files
```

## 后端分层

- `app/main.py`：创建 FastAPI 应用，挂载 `/static`，注册 API 路由，启动时初始化 SQLite。
- `app/api/`：HTTP 边界层，包含文本病历、音频、任务状态、LLM 状态等路由。
- `app/agents/medical_record_orchestrator.py`：Agent 编排层，负责字段抽取、病历草稿、安全校验、任务状态和审计日志。
- `app/services/`：业务服务层，包含 ASR 引擎、LLM 适配、病历导出、Mock 规则和重试工具。
- `app/db/`：SQLite 访问层，保存任务、步骤和审计记录。
- `app/schemas/`：Pydantic 数据结构，约束 API 输入输出和内部结果。

## 能力边界

| 能力 | 当前承载模块 |
| --- | --- |
| ASR pipeline | `app/api/audio.py`、`app/api/asr_sessions.py`、`app/services/asr/` |
| SSE streaming | `app/api/asr_sessions.py`、`app/api/tasks.py`、`static/doctor.js`、`static/main.js` |
| 医学对话结构化 | `app/agents/`、`app/schemas/medical_record.py` |
| 角色分离 | `app/services/asr/role_strategy.py` |
| 医学知识推理 | `app/services/mock_llm.py`、`app/prompts/` |
| 本地模型接入 | FunASR、Qwen3-ASR、Ollama provider |

## 核心数据流

文本链路：

```text
conversation_text
  -> POST /api/records/generate
  -> create_task
  -> extract_fields
  -> generate_draft
  -> safety_check
  -> doctor_review
  -> approve/export
```

音频链路：

```text
audio file
  -> POST /api/audio/upload
  -> POST /api/audio/{audio_id}/transcribe
  -> ASRResult
  -> optional evaluate
  -> POST /api/audio/{audio_id}/generate-record
  -> text record workflow
```

ASR 文件流链路：

```text
mp3/wav file
  -> POST /api/asr/sessions
  -> POST /api/asr/sessions/{session_id}/audio
  -> GET /api/asr/sessions/{session_id}/events
  -> segment events in doctor workbench
  -> completed ASRResult
  -> optional /api/audio/{audio_id}/generate-record
```

## 前端入口

- `/static/index.html`：系统入口页。
- `/static/doctor.html`：医生端工作台，面向演示和主流程验收。
- `/static/debug.html`：开发调试页，保留 JSON、SSE、任务步骤和 ASR 评测细节。

## 工程边界

- AI 输出只作为病历草稿和候选诊断，必须由医生审核确认。
- 不接入真实医院 HIS/EMR。
- 不提交真实患者数据、API Key、模型权重或大体积运行产物。
- 本文档只描述现有系统结构，不改变核心算法逻辑。
