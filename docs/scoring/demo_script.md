# 12-15 分钟正式汇报讲稿

本文档用于课程现场正式汇报，严格对应评分细则中的现场表现部分：表达清晰、结构完整、能现场演示、能解释 Agent 设计模式、能展示决策系统与 Prompt 链、能说明伦理合规，并能在 ASR 或环境卡顿时保持演示连续。

## 相关文档

- `docs/scoring/course_scoring_plan.md`
- `docs/scoring/agent_design.md`
- `docs/scoring/decision_system.md`
- `docs/scoring/prompt_chain_design.md`
- `docs/scoring/ethics_compliance.md`
- `docs/scoring/code_walkthrough.md`
- `docs/scoring/demo_checklist.md`

## 总体时间分配

| 环节 | 时间 | 现场表现目标 |
| --- | ---: | --- |
| 项目背景 | 2 分钟 | 讲清项目要解决的课程问题和医疗安全边界 |
| Agent 设计模式 | 3 分钟 | 讲清 Plan-and-Execute、Human-in-the-loop、感知-决策-行动-反馈 |
| 决策系统和 Prompt 链 | 3 分钟 | 展示决策逻辑、System Prompt、JSON 输出约束和安全校验 |
| 伦理合规 | 2 分钟 | 说明隐私保护、医生审核、防 Prompt 注入和局限性 |
| 系统演示 | 3 分钟 | 使用 fever_01.wav 主线展示医生端、ASR、病历草稿和评测 |
| 代码展示 | 2 分钟 | 定位关键代码文件，说明不是简单 API 调用 |

总时长控制在 15 分钟内；如果老师要求压缩，优先保留 Agent 设计、系统演示和安全边界。

## 0. 演示前准备

启动服务：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

准备材料：

- fever clean 问诊文本。
- `fever_01.wav` 本地样例音频。
- FunASR 环境检查结果：`python scripts/check_funasr_env.py`。
- 入口页：`http://127.0.0.1:8000/static/index.html`
- 医生端：`http://127.0.0.1:8000/static/doctor.html`
- 调试台：`http://127.0.0.1:8000/static/debug.html`

备用材料：

- 如果 FunASR 现场卡住，使用已完成的 ASRResult 或 Mock ASR 展示工程链路。
- 如果网络或浏览器异常，打开 `docs/scoring/agent_architecture_diagram.md`、`docs/scoring/code_walkthrough.md` 和 `docs/dev_logs/runs/` 中的运行日志继续讲解。

## 1. 项目背景，2 分钟

开场话术：

> 本项目是“AI 生成式电子病历辅助系统”。课程目标不是做一个简单表单，也不是直接把问诊文本丢给模型生成病历，而是实现一个可追踪、可审核、可评测的医疗病历生成 Agent。系统支持文本问诊和预录音频两种输入，音频通过 ASR 转成对话文本，再进入同一条病历 Agent 主流程。

要点：

- 医生在门诊中需要把问诊对话整理为结构化病历，人工整理耗时且容易遗漏。
- ASR 可以提升录音输入效率，但医学关键词和医生/患者角色错误会影响病历质量。
- 医疗场景不能让 AI 自动下最终诊断，所以本项目把 AI 定位为草稿生成和医生辅助。
- 项目只使用模拟问诊文本和课程样例音频，不接真实患者数据。

展示页面：

1. 打开 `/static/index.html`。
2. 指出系统分为医生端和调试台。
3. 简要说明医生端用于演示真实工作台，调试台用于展示 JSON 和任务步骤。

过渡话术：

> 接下来我先说明为什么它是一个 Agent，而不是普通 API 调用。

## 2. Agent 设计模式，3 分钟

展示文档：

- `docs/scoring/agent_design.md`
- `docs/scoring/agent_architecture_diagram.md`

核心话术：

> 本项目采用 Plan-and-Execute + Human-in-the-loop。Plan-and-Execute 体现在 Orchestrator 把任务拆成字段抽取、草稿生成、安全校验和医生审核；Human-in-the-loop 体现在 AI 不直接导出最终病历，必须停在 WAITING_DOCTOR_REVIEW 等医生确认。

按层说明：

1. 感知层：
   - 文本输入直接变成 `conversation_text`。
   - 音频输入先经过 ASR，统一输出 `ASRResult`。
   - `mock`、`funasr`、`qwen3`、`online` 都只作为 ASR 对比引擎，不替换病历 Agent 主流程。

2. 计划层：
   - `MedicalRecordOrchestrator` 根据输入生成任务。
   - 状态流转为 `CREATED -> EXTRACTING_FIELDS -> GENERATING_DRAFT -> SAFETY_CHECKING -> WAITING_DOCTOR_REVIEW`。

3. 执行层：
   - 字段抽取：主诉、现病史、伴随症状、过敏史、查体等。
   - 草稿生成：根据结构化字段生成病历草稿。
   - 安全校验：检查是否编造、是否把候选诊断写成最终诊断、是否跳过医生审核。

4. 反馈层：
   - SSE 推送任务进度。
   - `agent_task_step` 记录步骤输入输出。
   - `audit_log` 记录任务创建、状态变化、重试和降级。

现场表现重点：

- 不只说概念，要指到实际代码和状态。
- 强调医生审核是系统设计的一部分，不是演示时临时加的按钮。

过渡话术：

> 有了 Agent 流程以后，下一步是说明系统如何做决策，以及 Prompt 链如何约束模型输出。

## 3. 决策系统和 Prompt 链，3 分钟

展示文档和代码：

- `docs/scoring/decision_system.md`
- `docs/scoring/prompt_chain_design.md`
- `app/prompts/medical_record_prompts.py`

核心话术：

> 决策系统主要解决三个问题：输入走哪条流程、ASR 结果是否需要人工校正、病历草稿是否安全可进入医生审核。Prompt 链则负责约束真实 LLM 字段抽取的输出格式和医疗安全边界。

补充话术：

> 当前 POC 为了现场稳定演示，默认仍使用 MockLLM 和 deterministic extractor，同时已经提供 online / ollama 两个真实 LLM 字段抽取通道。真实 LLM 只负责字段抽取，草稿生成和安全校验继续走稳定逻辑；如果接口失败、超时、JSON 解析失败或字段不完整，会自动 fallback 到 MockLLM，不改变 Orchestrator 主流程。

决策系统讲解：

1. 输入类型决策：
   - 文本：`POST /api/records/generate`，直接进入 Agent。
   - 音频测试转写：只生成 ASRResult，不生成病历。
   - 音频生成病历：先 ASR，再把 `conversation_text` 送入 Agent。

2. ASR 角色策略：
   - 如果 `role_strategy=single_segment_needs_review`，医生端提示“医生/患者角色需人工校正”。
   - 系统不强行猜测医生/患者角色，因为角色会影响病历字段归属。

3. 字段与安全决策：
   - 字段缺失时 `missing=true`，不是写“无”。
   - 候选诊断必须 `候选，待医生确认`。
   - `SafetyCheckResult.blocked=true` 时禁止导出。

Prompt 链讲解：

- `MEDICAL_RECORD_SYSTEM_PROMPT`：规定 AI 只能辅助医生，不得替代医生，不得被患者文本覆盖。
- `FIELD_EXTRACTION_PROMPT`：要求输出字段 JSON，未提及字段必须 `missing=true`。
- `DRAFT_GENERATION_PROMPT`：只根据字段 JSON 生成草稿，不编造查体和过敏史。
- `SAFETY_CHECK_PROMPT`：检查编造、候选诊断、导出门禁和 Prompt 注入。

代码展示话术：

> 这里的 Prompt 文件已经作为 LLM Adapter 的字段抽取契约使用。现场演示默认用 MockLLM 保证稳定，但如果配置 `LLM_PROVIDER=online` 或 `LLM_PROVIDER=ollama`，字段抽取会先尝试真实模型，再由 JSON 解析、Pydantic 校验和 MockLLM fallback 保证链路不崩。

过渡话术：

> 医疗项目除了能运行，还必须说明安全和合规边界，所以接下来讲伦理合规。

## 4. 伦理合规，2 分钟

展示文档：

- `docs/scoring/ethics_compliance.md`

核心话术：

> 本系统不是自动诊断系统，而是医生辅助系统。伦理合规设计主要包括隐私保护、医疗安全、防 Prompt 注入、审计追踪、公平性和局限性声明。

要点：

- 隐私保护：
  - 不接真实患者数据。
  - 不提交真实 API Key。
  - Online ASR Key 只能从环境变量读取。
  - 本地上传音频、数据库和模型缓存不上传 GitHub。

- 医疗安全：
  - AI 只生成草稿。
  - 候选诊断必须医生确认。
  - 医生确认前不得导出最终病历。

- 防 Prompt 注入：
  - 患者文本不能覆盖 System Prompt。
  - 安全校验检查“忽略规则”“直接导出”等风险。

- 审计追踪：
  - `agent_task`、`agent_task_step`、`audit_log` 支撑回放和责任追踪。

收束话术：

> 所以这个系统的安全边界很明确：AI 提供结构化草稿和提醒，医生做最终判断。

## 5. 系统演示，3 分钟

主线：`fever_01.wav + FunASR -> ASRResult -> 病历草稿 -> 安全校验 -> ASR 评测`。

### 5.1 打开医生端

打开 `/static/doctor.html`。

话术：

> 这是医生端工作台，左边是病历字段，中间是对话转写，右边是 AI 辅助和安全校验。主页面不展示大段 JSON，避免医生端变成调试页。

> 顶部这里会显示当前 task_id、audio_id 和运行日志命令。演示完成后可以一键复制命令，把本次运行沉淀成 Markdown 日志。

### 5.2 上传 fever_01.wav 生成病历

操作：

1. 点击“上传生成病历”。
2. 选择 `fever_01.wav`。
3. ASR 引擎选择 FunASR。
4. 等待转写和生成病历。

话术：

> 音频先由 FunASR 转成 ASRResult，再把 conversation_text 输入病历 Agent。FunASR 是 baseline，其他 ASR 引擎只做对比，不替换主流程。

展示点：

- 中栏：转写文本。
- 左栏：主诉、现病史、伴随症状、过敏史、查体等字段。
- 右栏：缺失项提醒、候选诊断、安全校验。
- 右栏：Agent 决策轨迹，展示输入类型、感知结果、计划步骤、当前状态、导出决策和医生审核边界。
- 底部：“保存草稿到SQLite”只保存当前字段审核结果，不生成导出文件；真正导出要点击“确认导出”。

Agent Trace 话术：

> 这里是 Agent Trace。它把已有的 task、steps、ASRResult 和 SafetyCheckResult 组装成“感知 -> 计划 -> 执行 -> 决策”的轨迹。可以看到系统计划了字段抽取、草稿生成、安全校验和医生审核，并明确给出 `export_allowed=false`，原因是 `doctor_review_required`。

### 5.3 展示 ASR 评测

操作：

1. 打开 ASR 评测。
2. 输入人工标注文本和关键词。
3. 点击评测。

话术：

> CER 衡量字符错误率，keyword_recall 衡量医学关键词召回。医学场景里关键词是否召回比普通文本相似度更重要，因为它直接影响字段抽取和候选诊断。

### 5.4 展示角色校正提醒

如果出现 `single_segment_needs_review`：

话术：

> 这里系统提示医生/患者角色需人工校正。因为 ASR 返回单段长文本时，系统不会强行猜测角色；这是医疗安全边界的一部分。

如果没有出现：

话术：

> 当前样例的角色策略没有触发人工校正提醒。另一个常见情况是 ASR 只返回单段长文本，此时医生端会提示需要人工校正角色。

### 5.5 打开调试台展示审计

打开 `/static/debug.html`。

话术：

> 调试台保留了 ASRResult、Task、Steps、Safety JSON。这里可以看到每一步输入输出和安全校验结果，用于证明系统过程可追踪，不是黑箱生成。

> 调试抽屉还会展示完整 Agent Trace JSON，老师如果问“Agent 体现在哪里”，可以直接展示 agent_mode、perception、plan、executed_steps 和 decision。

> Task JSON 的 result_json 可以查看已经保存的字段、草稿和安全校验；运行日志命令会把 task_id 和 audio_id 汇总为 `docs/dev_logs/runs/` 下的演示日志。

## 6. ASR 卡顿备用方案话术

如果现场 FunASR 卡住或模型加载过慢：

> FunASR 属于本地可选依赖，首次加载模型可能比较慢。为了不让现场演示受模型加载影响，我切换到备用方案：第一，使用 Mock ASR 展示完整工程链路；第二，展示之前保存的 ASRResult 和运行日志；第三，说明 FunASR 与 Mock/Online/Qwen3 都统一输出 ASRResult，所以不会影响后续病历 Agent 主流程。

操作顺序：

1. 告诉老师 FunASR 是可选本地引擎，现场卡顿不影响 Agent 设计。
2. 切换 `engine=mock` 或打开已有转写结果。
3. 继续展示病历字段、候选诊断、安全校验和 ASR 评测说明。
4. 打开 `docs/dev_logs/runs/` 中的运行日志，说明此前 `fever_01.wav` 的完整运行记录。

备用总结：

> 这里的关键不是某一个 ASR 引擎本身，而是 ASR 输出被统一适配为 ASRResult，并进入同一条可追踪的病历 Agent 流程。

## 7. 代码展示，2 分钟

展示路线参考 `docs/scoring/code_walkthrough.md`。

### 7.1 Orchestrator

文件：`app/agents/medical_record_orchestrator.py`

话术：

> 这是 Agent 的核心编排器。它创建任务，依次进入字段抽取、草稿生成、安全校验，最后进入 WAITING_DOCTOR_REVIEW。每一步都会写入 task_step，所以能在调试台看到完整过程。

### 7.2 Schema

文件：`app/schemas/medical_record.py`

话术：

> 字段不是普通字符串，而是带 missing、confidence、source_spans 和 confirmed_by_doctor 的结构。这个设计支持缺失提醒、证据追踪和医生确认。

### 7.3 Prompt 示例

文件：`app/prompts/medical_record_prompts.py`

话术：

> System Prompt 规定不能编造、不能替代医生、不能跳过医生确认。字段抽取 Prompt 要求 JSON 输出，安全校验 Prompt 检查导出风险和 Prompt 注入。

### 7.4 ASR 和运行日志

文件：

- `app/services/asr/factory.py`
- `scripts/save_run_log.py`

话术：

> ASR factory 支持多个引擎，但统一输出 ASRResult。save_run_log.py 可以把一次演示的 task_id 和 audio_id 汇总为 Markdown 运行日志，方便课程验收。

### 7.5 Agent Trace

文件：

- `app/services/agent_trace.py`
- `app/api/tasks.py`

话术：

> Agent Trace 不新增数据库，而是基于现有 task、steps、ASRResult 和 SafetyCheckResult 动态组装。它显式展示 agent_mode、input_type、perception、plan、executed_steps 和 decision，其中 decision 固定说明 AI 不允许自动导出，必须进入医生审核。

## 8. 结尾，30 秒

结束话术：

> 总结一下，本项目实现了一个面向电子病历生成的 Agent POC。它通过 ASR 感知、Orchestrator 计划执行、字段抽取和安全校验完成草稿生成，通过医生审核保证医疗边界，通过任务步骤和审计日志保证过程可追踪。项目演示重点不是让 AI 自动诊断，而是展示如何把生成式 AI 放在一个可控、可解释、可审核的医疗工作流中。
