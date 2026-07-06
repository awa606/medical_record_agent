# Agent 设计模式说明

本项目定位为 `Plan-and-Execute + Human-in-the-loop` 医疗病历生成 Agent。它不是把用户输入直接交给一个接口生成文本，而是把文本或音频输入转成可追踪任务，按阶段执行字段抽取、草稿生成、安全校验和医生审核，并在每一步记录状态、输入输出快照和审计日志。

## 为什么是 Agent，而不是简单 API 调用

简单 API 调用通常是：

```text
输入文本 -> 调用模型 -> 返回病历
```

本项目的实际流程是：

```text
输入文本/音频
  -> 感知层解析
  -> Orchestrator 计划执行路径
  -> 字段抽取
  -> 病历草稿生成
  -> 安全校验
  -> 医生审核
  -> 任务步骤、SSE、审计日志反馈
```

Agent 特征体现在：

- 有状态：`agent_task.status` 记录 `CREATED`、`EXTRACTING_FIELDS`、`GENERATING_DRAFT`、`SAFETY_CHECKING`、`WAITING_DOCTOR_REVIEW` 等状态。
- 有计划：`MedicalRecordOrchestrator` 把病历生成拆成多个可追踪步骤，而不是一次性输出。
- 有工具/执行动作：ASR、字段抽取、草稿生成、安全校验、导出前校验分别承担不同动作。
- 有反馈：SSE 推送任务状态，`agent_task_step` 记录步骤输入输出，`audit_log` 记录状态变化。
- 有人机协作：AI 只生成草稿和候选诊断，最终必须由医生确认。

## 设计模式

### Plan-and-Execute

Plan-and-Execute 在本项目中的落点：

| 阶段 | 项目实现 | 可展示代码 |
| --- | --- | --- |
| Plan | 根据输入类型选择文本链路或音频链路；将任务拆成字段抽取、草稿生成、安全校验、医生审核 | `app/api/records.py`、`app/api/audio.py`、`app/agents/medical_record_orchestrator.py` |
| Execute | 按步骤执行 LLM Adapter/MockLLM 兜底、ASR 转写、ASR 评测、安全校验 | `app/services/llm/`、`app/services/mock_llm.py`、`app/services/asr/` |
| Observe | 记录每一步输入输出快照、错误、重试和降级状态 | `app/db/sqlite.py` |
| Feedback | SSE、医生端三栏工作台、调试台 JSON、医生审核按钮 | `app/api/tasks.py`、`static/doctor.html`、`static/debug.html` |

### Human-in-the-loop

医疗场景不能让 AI 自动完成最终诊断和导出，因此本项目把医生审核设计为流程边界：

- 候选诊断必须标记为“候选，待医生确认”。
- 字段未确认、候选诊断未确认或安全校验失败时，不应直接导出。
- `WAITING_DOCTOR_REVIEW` 是正常终态之一，表示 AI 任务完成但仍等待医生复核。
- 医生端工作台突出缺失项、证据片段、安全校验和确认操作。

## 感知层

感知层负责把外部输入转为 Agent 可处理的 `conversation_text`。

- 文本输入：医生或学生粘贴人工问诊文本，进入 `/api/records/generate`。
- 音频输入：上传 `wav/mp3/m4a/flac/ogg`，进入 `/api/audio/upload`。
- ASR 感知：`mock`、`funasr`、`qwen3`、`online` 引擎统一输出 `ASRResult`。
- 角色策略：如果 ASR 只能返回单段长文本，`role_strategy=single_segment_needs_review`，医生端提示需要人工校正医生/患者角色。

## 计划层

计划层由 `MedicalRecordOrchestrator` 和 API 入口共同完成。

- 文本生成病历：`conversation_text -> create_text_task -> run_existing_text_task`。
- 音频测试转写：`upload -> transcribe -> ASRResult`，不进入病历生成。
- 音频生成病历：`upload -> transcribe -> generate-record -> run_existing_text_task`。
- 调试链路：`debug.html` 可查看 Task、Steps、Safety JSON。

## 执行层

执行层包含可替换模块：

1. ASR 转写：音频转 `ASRResult`，用于对比不同引擎。
2. 字段抽取：抽取主诉、现病史、既往处理、伴随症状、既往史、过敏史、查体、候选诊断等字段。
3. 草稿生成：根据字段生成病历草稿，不补充未出现事实。
4. 安全校验：检查是否编造、是否把候选诊断写成最终诊断、是否跳过医生确认。
5. 导出前动作：医生确认字段后才能进入导出语义。

## 反馈层

反馈层让 Agent 可观察、可调试、可审计：

- SSE：`/api/tasks/{task_id}/events` 推送任务状态。
- 步骤表：`agent_task_step` 保存每一步状态、耗时、输入快照和输出快照。
- 审计表：`audit_log` 保存任务创建、状态变化、降级等事件。
- 医生端：展示字段证据、缺失提醒、候选诊断、安全校验。
- 调试台：展示 ASRResult、Task、Steps、Safety JSON。

## 一分钟汇报讲法

本项目采用 `Plan-and-Execute + Human-in-the-loop`。感知层接收文本或音频，音频先通过 ASR 统一成 `ASRResult`；计划层由 Orchestrator 根据输入类型选择路径，并把任务拆为字段抽取、草稿生成、安全校验和医生审核；执行层完成结构化字段、病历草稿和安全校验；反馈层通过 SSE、任务步骤表和审计日志记录过程。医疗安全上，AI 只生成草稿和候选诊断，最终导出前必须由医生审核确认。

## 相关文档

- 评分总表：`docs/scoring/course_scoring_plan.md`
- 架构图：`docs/scoring/agent_architecture_diagram.md`
- 决策系统：`docs/scoring/decision_system.md`
- Prompt 链：`docs/scoring/prompt_chain_design.md`
- 现场演示讲稿：`docs/scoring/demo_script.md`
- 代码展示路线：`docs/scoring/code_walkthrough.md`
