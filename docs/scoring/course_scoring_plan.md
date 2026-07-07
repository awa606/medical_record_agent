# 课程评分对照总表

本文档是课程评分材料的总入口。它把项目能力映射到可展示证据，便于答辩时说明本项目不是普通表单或简单 API 调用，而是带有 Agent 编排、决策约束、医生复核和伦理边界的医疗病历生成辅助系统。

## 评分证据总览

| 评分点 | 可展示证据 | 主要文件 |
| --- | --- | --- |
| 智能体设计模式 | Plan-and-Execute + Human-in-the-loop；感知-决策-行动-反馈闭环；Agent Trace；SSE 反馈和任务步骤日志 | `docs/scoring/agent_design.md`、`docs/scoring/agent_architecture_diagram.md`、`app/services/agent_trace.py`、`app/agents/medical_record_orchestrator.py` |
| 决策系统设计 | 输入路径选择、ASR 角色策略、LLM provider 选择与 fallback、字段缺失判断、安全校验、医生确认前不得导出 | `docs/scoring/decision_system.md`、`docs/scoring/prompt_chain_design.md`、`app/prompts/medical_record_prompts.py`、`app/services/llm/` |
| 伦理合规设计 | 模拟数据、隐私保护、API Key 不入库不入代码、防 Prompt 注入、AI 草稿边界、审计追踪 | `docs/scoring/ethics_compliance.md`、`app/db/sqlite.py`、`docs/dev_logs/DEVELOPMENT_RULES.md` |
| 现场演示 | 医生端工作台、调试台、文本生成病历、FunASR 音频生成病历、ASR 评测 | `static/index.html`、`static/doctor.html`、`static/debug.html` |
| 代码展示 | Orchestrator、Prompt 示例、Pydantic Schema、ASR factory、任务表和步骤表 | `app/agents/`、`app/prompts/`、`app/schemas/`、`app/services/asr/`、`app/db/sqlite.py` |
| 迭代过程 | GitHub issue、开发日志、验证命令和未解决问题 | `docs/dev_logs/` |

## 智能体设计模式如何拿分

答辩关键词：`Plan-and-Execute`、`Human-in-the-loop`、`感知-决策-行动-反馈`。

展示路径：

1. 打开 `docs/scoring/agent_architecture_diagram.md`，先讲系统闭环。
2. 打开 `app/agents/medical_record_orchestrator.py`，展示 `EXTRACTING_FIELDS -> GENERATING_DRAFT -> SAFETY_CHECKING -> WAITING_DOCTOR_REVIEW`。
3. 打开 `/static/doctor.html`，说明医生端只呈现工作台；打开 `/static/debug.html`，说明任务步骤和 JSON 可追踪。

得分论证：

- 感知层处理文本输入和 ASRResult。
- 计划层根据输入来源选择文本链路或音频链路。
- 执行层依次完成字段抽取、草稿生成和安全校验。
- 反馈层通过 SSE、任务步骤和审计日志记录状态。
- 医生审核是最终闭环，AI 不直接替代医生。

## 决策系统设计如何拿分

展示路径：

1. 打开 `docs/scoring/decision_system.md`，展示决策表。
2. 打开 `app/prompts/medical_record_prompts.py`，展示 System Prompt 与 JSON 输出约束。
3. 在医生端演示 fever clean 文本或 `fever_01.wav`，观察缺失字段、安全校验和候选诊断状态。

得分论证：

- 输入类型决定流程：文本直接进 Agent；音频先 ASR，再生成病历。
- ASR 角色策略决定是否提示“医生/患者角色需人工校正”。
- 字段 missing、confidence、source_spans 支撑可解释抽取。
- safety_check 决定是否阻止导出。
- 候选诊断必须医生确认，不能自动变成最终诊断。

## 伦理合规设计如何拿分

展示路径：

1. 打开 `docs/scoring/ethics_compliance.md`，展示隐私、安全、防注入、公平性和局限性。
2. 展示 README 中“不接真实患者数据、不提交真实 API Key”的边界。
3. 展示 `app/db/sqlite.py` 的 `agent_task`、`agent_task_step`、`audit_log`，说明审计追踪。

得分论证：

- 项目只使用模拟问诊文本和课程样例音频，不接真实患者身份信息。
- Online ASR 的 URL 和 Key 只能从环境变量读取。
- 患者输入不能覆盖 System Prompt；Prompt 明确禁止编造和越权导出。
- AI 输出定位为草稿、候选诊断和提醒，最终由医生确认。
- 不根据性别、年龄、职业做无依据判断。

## 现场演示如何拿分

建议演示顺序：

1. 打开 `/static/index.html`，说明入口页只进入医生端或调试台。
2. 打开 `/static/doctor.html`，点击“文本导入”，粘贴 fever clean 问诊文本并生成病历。
3. 展示左栏字段、证据、候选诊断和右栏安全校验。
4. 上传 `fever_01.wav`，选择 FunASR，生成 ASRResult 和病历。
5. 打开 ASR 评测，展示 CER、keyword_recall、recognized、missing。
6. 打开 `/static/debug.html`，展示 Task、Steps、Safety JSON，证明过程可追踪。

## 代码展示如何拿分

建议展示 5 个代码点：

1. `app/agents/medical_record_orchestrator.py`：Agent 编排和状态机。
2. `app/schemas/medical_record.py`：字段、候选诊断、安全校验结构。
3. `app/prompts/medical_record_prompts.py`：Prompt 链和 JSON 输出约束示例。
4. `app/services/llm/factory.py`：Mock/Online/Ollama LLM provider 选择与兜底。
5. `app/services/asr/factory.py`：Mock/FunASR/SenseVoice/Whisper/Qwen3/Online ASR 对比引擎。
6. `app/services/agent_trace.py`：Agent 决策轨迹组装。
7. `app/db/sqlite.py`：任务表、步骤表、审计日志。

## 与开发日志的关系

每个评分点都应能回到 `docs/dev_logs/` 中的迭代记录。汇报时可以用以下结构：

```text
Issue #29/#30/#31
  -> docs/dev_logs/ 对应开发日志
  -> docs/scoring/ 对应评分文档
  -> 代码或页面演示
  -> 评分细则得分点
```

## 相关文档

- 项目进度看板：`docs/scoring/项目进度与评分证据看板.md`
- 现场演示讲稿：`docs/scoring/demo_script.md`
- 代码展示路线：`docs/scoring/code_walkthrough.md`
- 演示验收清单：`docs/scoring/demo_checklist.md`
- Agent 设计：`docs/scoring/agent_design.md`
- 决策系统：`docs/scoring/decision_system.md`
- Prompt 链：`docs/scoring/prompt_chain_design.md`
- 伦理合规：`docs/scoring/ethics_compliance.md`
