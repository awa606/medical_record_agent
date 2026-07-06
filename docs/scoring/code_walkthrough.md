# 代码讲解路线

本文档用于课程代码展示环节，按“入口 -> Agent 编排 -> Schema 约束 -> Prompt 示例 -> ASR 对比 -> 审计追踪”的顺序讲解。

## 1. 前端入口

展示文件：

- `static/index.html`
- `static/doctor.html`
- `static/debug.html`
- `static/doctor.js`

讲解要点：

- `index.html` 只做入口，避免调试信息干扰医生端。
- `doctor.html` 是三栏医生工作台，展示字段、转写、安全校验。
- `debug.html` 保留 JSON 调试和任务日志，服务开发和课程验收。
- `doctor.js` 接入现有 API，不改变后端接口。

## 2. API 入口

展示文件：

- `app/api/records.py`
- `app/api/audio.py`
- `app/api/tasks.py`

讲解要点：

- `/api/records/generate`：文本生成病历。
- `/api/audio/upload`：上传音频。
- `/api/audio/{audio_id}/transcribe`：选择 ASR 引擎转写。
- `/api/audio/{audio_id}/generate-record`：音频转写后生成病历。
- `/api/tasks/{task_id}/events`：SSE 推送任务进度。

## 3. Agent 编排

展示文件：

- `app/agents/medical_record_orchestrator.py`

讲解要点：

- 状态流转：`CREATED -> EXTRACTING_FIELDS -> GENERATING_DRAFT -> SAFETY_CHECKING -> WAITING_DOCTOR_REVIEW`。
- 每一步通过 `agent_task_step` 保存输入快照、输出快照、状态、耗时和错误。
- LLM 步骤失败时有重试和降级逻辑。
- `WAITING_DOCTOR_REVIEW` 体现 Human-in-the-loop。

## 4. Schema 约束

展示文件：

- `app/schemas/medical_record.py`
- `app/schemas/asr.py`
- `app/schemas/task.py`

讲解要点：

- `MedicalField` 包含 `value`、`missing`、`hint`、`confidence`、`source_spans`、`confirmed_by_doctor`。
- `CandidateDiagnosis` 必须是候选状态，并由医生确认。
- `SafetyCheckResult` 使用 `passed`、`blocked`、`errors`、`warnings` 表达导出风险。
- `ASRResult` 统一不同 ASR 引擎输出。

## 5. Prompt 链示例

展示文件：

- `app/prompts/medical_record_prompts.py`
- `docs/scoring/prompt_chain_design.md`

讲解要点：

- System Prompt 规定不得编造、不得替代医生、不得跳过医生确认。
- 字段抽取 Prompt 要求输出 JSON，并对未提及字段设置 `missing=true`。
- 草稿生成 Prompt 不允许把候选诊断写成最终诊断。
- 安全校验 Prompt 检查编造、导出门禁和 Prompt 注入。
- 当前默认 `MockLLM` 是 POC 阶段稳定兜底；`app/services/llm/` 已提供 online / ollama 字段抽取 Adapter，Prompt 文件作为真实 LLM 接入契约。

## 6. ASR 对比与评测

展示文件：

- `app/services/asr/factory.py`
- `app/services/asr/funasr_engine.py`
- `app/services/asr/qwen3_engine.py`
- `app/services/asr/online_engine.py`
- `app/services/asr/evaluator.py`
- `scripts/save_run_log.py`

讲解要点：

- ASR 引擎包括 `mock`、`funasr`、`qwen3`、`online`。
- FunASR 保持 baseline，不被替换。
- CER 和 keyword_recall 用于对比 ASR 输出质量。
- `save_run_log.py` 可把一次演示结果保存为 Markdown 运行日志。

## 7. 审计追踪

展示文件：

- `app/db/sqlite.py`
- `app/services/agent_trace.py`
- `docs/scoring/ethics_compliance.md`

讲解要点：

- `agent_task` 记录任务总体状态。
- `agent_task_step` 记录每个执行步骤。
- `audit_log` 记录任务创建、状态变化、重试和降级。
- `agent_trace.py` 基于现有 task、steps、ASRResult 和 SafetyCheckResult 动态组装 Agent Trace，不新增数据库结构。
- 审计追踪支撑医疗安全和课程评分中的过程可解释性。

## 代码展示收束

最后回到 `docs/scoring/course_scoring_plan.md`，把代码点映射到评分点：

- 智能体设计模式：Orchestrator、SSE、Human-in-the-loop。
- 决策系统设计：Prompt 链、Schema、SafetyCheck、ASR role_strategy。
- 伦理合规设计：模拟数据、隐私保护、防注入、审计日志、医生确认。

## 相关文档

- 评分总表：`docs/scoring/course_scoring_plan.md`
- 现场演示讲稿：`docs/scoring/demo_script.md`
- 演示验收清单：`docs/scoring/demo_checklist.md`
- Agent 设计：`docs/scoring/agent_design.md`
- 决策系统：`docs/scoring/decision_system.md`
- Prompt 链：`docs/scoring/prompt_chain_design.md`
- 伦理合规：`docs/scoring/ethics_compliance.md`
