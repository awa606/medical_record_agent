# AI 生成式电子病历辅助系统期末报告

## 封面信息

| 项目 | 内容 |
| --- | --- |
| 课程名称 | Fundamentals of Artificial Intelligence |
| 项目名称 | AI 生成式电子病历辅助系统 |
| 小组成员：姓名、学号、分工 | 【请填写姓名、学号、分工】 |
| 指导老师 | 【请填写指导老师】 |
| 学院 / 专业 / 班级 | 【请填写学院、专业、班级】 |
| 日期 | 2026 年 6 月 |

## 摘  要

本项目面向门诊问诊后的电子病历整理场景，完成了一个 AI 生成式电子病历辅助系统课程 POC 原型。医生在真实工作中需要从自然语言问诊中整理主诉、现病史、伴随症状、既往史、过敏史、查体、候选诊断和处理建议等内容，人工整理存在耗时、遗漏和证据不清的问题。生成式 AI 可以辅助整理信息，但不能直接替代医生判断。本项目重点解决的问题不是“自动诊断”，而是“如何把 AI 放进可审核、可追踪、可降级的流程”。系统支持文本导入和预录音频输入，音频先由 ASR 转写为统一的 ASRResult，再进入病历 Agent 主流程。Agent 采用 Plan-and-Execute + Human-in-the-loop 模式，将任务拆成字段抽取、草稿生成、安全校验和医生审核。系统通过 doctor.html 展示医生端工作台，通过 debug.html 展示调试证据，通过 Agent Trace、Task Steps、audit_log 和运行日志保存过程证据。项目保留 MockLLM fallback，目的是保证课程演示稳定和工程鲁棒性，不把外部模型失败变成主流程失败。本报告只描述当前已经实现和能够展示的功能，不把系统描述为真实临床系统，也不声称完成临床验证或模型训练。

## 关键词

生成式电子病历；Plan-and-Execute；Human-in-the-loop；ASR；Agent Trace；MockLLM fallback

## 目  录

1. 项目背景与实际痛点
2. 项目目标与系统边界
3. 系统需求分析
4. 总体架构与程序设计思路
5. 智能体设计模式
6. 决策系统与 Prompt 链设计
7. 核心技术模块实现
8. 与评分细则的对应说明
9. 医生端工作台与演示流程
10. 测试验证与证据材料
11. 当前问题与建议补充测试内容
12. 安全伦理合规设计
13. 总结与后续计划
14. 修改说明

## 1. 项目背景与实际痛点

门诊问诊通常以自然语言对话进行。医生需要在有限时间内询问症状、病程、既往处理、伴随症状、既往史、过敏史和查体情况，并把这些信息整理成结构化电子病历。对于发热、胸痛、蛇咬伤等场景，病历中哪些信息已经明确、哪些信息还需要补问、哪些内容只能作为候选诊断，都需要被清楚记录。

人工整理病历的主要问题有三个。第一，整理过程耗时，医生需要一边沟通一边记录，容易影响问诊效率。第二，字段可能遗漏，例如过敏史、查体、既往处理等内容如果没有问到，就不能简单写成“无”。第三，证据来源不够清楚，后续复核时很难知道某个病历字段来自哪一句问诊对话。

生成式 AI 可以辅助把对话整理成草稿，但医疗场景不能让 AI 直接替代医生。模型可能理解错误、补充不存在的事实，或者把候选诊断写成最终诊断。因此，本项目的真实目标不是“让 AI 自动诊断”，而是把 AI 放进一个可审核、可追踪、可降级的程序流程中。系统的输出始终定位为病历草稿、候选诊断和安全提醒，最终字段确认和导出必须由医生完成。

图 1：系统入口页

【建议插入图：static/index.html 系统入口页截图】

图 1 系统入口页，展示医生端工作台和开发调试台两个入口。

## 2. 项目目标与系统边界

本项目是课程 POC 原型，不是真实临床系统。项目不接真实患者数据，不接真实医院 HIS/EMR，不提交真实 API Key，不使用真实患者身份信息，也不声明具备临床诊疗能力。

系统目标主要有四个。第一，展示文本和音频两类输入如何进入统一的病历 Agent 流程。第二，展示 Plan-and-Execute + Human-in-the-loop 的智能体设计模式。第三，展示字段抽取、草稿生成、安全校验、医生审核和运行日志之间的决策闭环。第四，展示一个可解释、可追踪、可复盘的课程演示证据链。

系统边界也很明确。ASR 只负责把音频转成文字，不负责诊断。LLM 或 MockLLM 只负责辅助字段抽取和草稿生成，不决定最终诊断。安全校验只用于发现明显风险，不能替代医生判断。医生审核前，系统不允许把 AI 草稿当成最终病历导出。这个边界在 Agent Trace 中体现为 `export_allowed=false`，原因是 `doctor_review_required`。

图 2：医生端无任务引导卡片

【建议插入图：doctor.html 无任务状态截图】

图 2 医生端无任务引导卡片，提示用户通过文本导入或上传音频开始一次病历生成。

## 3. 系统需求分析

从功能角度看，系统需要支持三条入口。第一条是文本导入，用户粘贴人工问诊文本，系统直接创建病历生成任务。第二条是上传预录音频测试转写，用户只测试 ASR 转写结果，不进入病历生成流程。第三条是上传预录音频生成病历，系统先完成 ASR 转写，再把 conversation_text 输入 Agent 主流程。

从程序处理角度看，文本输入和音频输入最终都要收敛为 conversation_text。这样做的好处是后续字段抽取、草稿生成和安全校验不需要关心输入最初来自文本还是音频，主流程保持稳定。音频链路多出来的工作只放在感知层，也就是 ASRResult 的生成和角色策略判断。

从展示角度看，系统需要两个不同页面。doctor.html 面向医生和评委演示，重点展示病历字段、对话转写、缺失提醒、候选诊断、安全校验和医生审核。debug.html 面向课程调试和评分证据，保留 ASRResult、Task、Steps、Safety、Agent Trace 等 JSON 信息。这样可以避免医生端页面被大量调试信息占满，同时又能保留过程证据。

从课程评分角度看，系统还需要展示工具调用、任务过程记录、决策系统、安全合规和演示证据。因此项目增加了 Agent Trace、Task Steps、audit_log、运行日志脚本和评分文档。这些内容不是额外装饰，而是为了说明系统不是单次 API 调用，而是一个可追踪的 Agent 原型。

## 4. 总体架构与程序设计思路

系统整体采用前后端分离但轻量化的设计。前端是静态页面，后端使用 FastAPI，数据记录使用 SQLite。本项目不接真实 HIS/EMR，因此数据库只用于保存课程演示任务、步骤日志和审计信息。

前端部分包括三个页面。index.html 是入口页，展示项目名称、课程 POC 边界和两个入口。doctor.html 是医生端工作台，提供文本导入、上传音频、三栏病历查看、医生审核和截图模式。debug.html 是开发调试台，用来展示 API 调试、ASRResult、Task JSON、Steps JSON、Safety JSON 和 Agent Trace。

后端 API 层负责接收请求。文本生成病历走 `/api/records/generate`；音频上传、ASR 转写、ASR 评测和音频生成病历走 `/api/audio/...`；任务状态、步骤日志、SSE 和导出动作走 `/api/tasks/...`；LLM 状态检查走 `/api/llm/status` 或 `/api/llm/test`。这些接口把页面操作转成后端任务。

ASR 层负责把音频转换成 ASRResult。ASRResult 中包含 text、conversation_text、segments、warnings、role_strategy 和 medical_keywords 等字段。这样 FunASR、Mock、Qwen3、Online ASR 的输出都能适配到同一个结构。

LLM 层负责把 conversation_text 转为结构化字段。当前系统支持 mock、online、ollama 三种 provider 思路。真实 provider 调用失败、超时、JSON 解析失败或字段不完整时，会 fallback 到 MockLLM。这个设计保证课程演示不会因为外部模型不稳定而中断。

Orchestrator 是主流程编排模块。它负责创建任务、更新状态、执行字段抽取、生成草稿、安全校验，并把任务推进到 WAITING_DOCTOR_REVIEW。SQLite 中的 agent_task、agent_task_step 和 audit_log 负责保存状态、步骤和审计记录。Agent Trace 和 Run Log 则负责把这些过程整理成课程答辩可以展示的证据。

图 3：系统总体架构图

【建议插入图：Codex 生成的系统总体架构图】

图 3 系统总体架构图，展示前端、API、ASR、LLM、Orchestrator、SQLite 记录和医生审核之间的关系。

## 5. 智能体设计模式

本项目采用 Plan-and-Execute + Human-in-the-loop。这里的 Plan-and-Execute 不是抽象概念，而是体现在程序流程中：系统接收输入后不会直接输出最终病历，而是先判断输入类型，再拆成字段抽取、草稿生成、安全校验和医生审核等步骤执行。

如果输入是文本，系统直接创建文本任务。如果输入是音频，系统先调用 ASR 得到 ASRResult，再把 conversation_text 输入同一条病历生成链路。如果用户只是测试转写，系统只输出 ASRResult，不自动生成病历。这个输入分流体现了计划阶段。

执行阶段由 MedicalRecordOrchestrator 完成。它会把任务状态从 CREATED 推进到 EXTRACTING_FIELDS、GENERATING_DRAFT、SAFETY_CHECKING，最后进入 WAITING_DOCTOR_REVIEW。每一步都会记录到 task_step 中，包含步骤名称、状态、尝试次数、输入输出快照、耗时和错误。这样调试台可以查看系统到底执行到了哪一步。

Human-in-the-loop 体现在医生审核边界上。医疗病历不能由 AI 自动定稿。候选诊断必须由医生确认，缺失字段必须由医生补充或确认，医生审核前不允许导出最终病历。Agent Trace 中的 decision 会明确记录 `export_allowed=false`，原因是 `doctor_review_required`。这说明医生审核不是演示时临时加的按钮，而是 Agent 流程的一部分。

本项目与简单 API 调用的区别在于：简单 API 调用通常是“输入文本，调用模型，返回病历”。本项目则是“输入文本或音频，感知，计划，执行多个步骤，安全校验，等待医生审核，并记录过程”。这也是本项目作为智能体原型的主要价值。

图 4：Agent 执行流程图

【建议插入图：Codex 生成的 Plan-and-Execute + Human-in-the-loop 流程图】

图 4 Agent 执行流程图，展示从输入感知到医生审核的任务状态流转。

## 6. 决策系统与 Prompt 链设计

系统的决策不是单个 if 判断，而是由多个层次组成。第一层是输入分流：文本输入直接生成病历任务，音频生成病历需要先 ASR，音频测试转写只生成 ASRResult。这样可以避免所有入口混在一起，也能清楚说明每条链路的目的。

第二层是 ASR 决策。ASR 引擎可以选择 FunASR、Mock、Qwen3 或 Online。FunASR 是当前本地真实 ASR baseline，Mock 用于工程链路验证，Qwen3 和 Online 作为对比引擎。ASR 不负责诊断，只负责把音频转成文字。如果 ASR 返回的是单段长文本，系统会把 role_strategy 标记为 `single_segment_needs_review`，提示医生/患者角色需要人工校正。系统不会为了页面好看而强行猜测角色，因为角色错误会影响病历字段归属。

第三层是 LLM provider 决策。系统支持 mock、online、ollama 三种 provider 思路。默认使用 MockLLM，是为了保证课程演示稳定。如果配置 Online 或 Ollama，系统会先尝试真实模型字段抽取，但输出必须通过 JSON 解析和 Schema 校验。如果失败，系统会 fallback 到 MockLLM，并在 Agent Trace 中记录 fallback 状态和原因。

第四层是字段和安全决策。字段抽取后，每个字段都要说明 value、missing、hint、confidence 和 source_spans。未提及字段不能写成“无”或“正常”，而应该标记为 missing。候选诊断不能直接变成最终诊断。安全校验会检查草稿是否存在编造、候选诊断误用、导出风险和 Prompt 注入风险。

Prompt 链的设计目的，是把模型输出限制在结构化、可校验、可审核的范围内。System Prompt 规定 AI 只能辅助医生，不能替代医生；字段抽取 Prompt 要求输出结构化 JSON；草稿生成 Prompt 要求只根据已有字段写草稿；安全校验 Prompt 用于检查导出前风险。JSON 和 Pydantic Schema 的意义，是把不稳定的自然语言输出变成程序可以检查的数据结构。

图 5：决策系统与 Prompt 链流程图

【建议插入图：Codex 生成的决策系统流程图】

图 5 决策系统与 Prompt 链流程图，展示输入分流、ASR 决策、LLM fallback、Schema 校验和安全校验之间的关系。

## 7. 核心技术模块实现

### 7.1 ASR 模块

ASR 模块的输入是预录音频，例如本地上传的 wav 文件。用户可以在页面选择 FunASR、Mock、Qwen3 或 Online ASR。FunASR 用于展示本地真实 ASR baseline，Mock 用于保证工程链路可跑，Qwen3 和 Online 作为对比方向。

处理过程是：后端接收音频文件，保存 audio_id，然后根据 engine 参数创建对应 ASR 引擎。引擎完成转写后，结果会被统一适配为 ASRResult。ASRResult 中包含 text、conversation_text、segments、duration、medical_keywords、warnings 和 role_strategy。

ASR 模块的输出不是病历，而是 ASRResult。这个模块只负责感知层转写，不负责字段抽取、诊断或安全判断。这样设计的原因是，ASR 质量会影响后续字段抽取，但不应该直接决定病历内容。通过统一 ASRResult，后续 Agent 主流程可以保持稳定，不需要关心具体 ASR 引擎是哪一个。

图 6：对话转写区域

【建议插入图：doctor.html 中栏对话转写截图】

图 6 对话转写区域，展示音频转写后进入病历 Agent 的 conversation_text。

### 7.2 LLM 模块

LLM 模块的输入是 conversation_text，也就是文本问诊内容或 ASR 转写后的对话文本。它的目标是把自由文本整理成结构化字段，而不是直接生成最终病历。

处理过程包括 Prompt 构造、Provider 调用、JSON 解析、Schema 校验和 fallback。Provider 可以是 MockLLM、Online LLM 或 Ollama。真实模型返回结果后，系统需要解析为 JSON，并校验是否满足 MedicalField、CandidateDiagnosis 和 SafetyCheckResult 等结构。如果接口失败、超时、JSON 无效或字段不完整，系统会使用 MockLLM fallback。

LLM 模块的输出包括 MedicalField、CandidateDiagnosis、病历草稿 Draft 和 SafetyCheckResult。MedicalField 用于表示字段值、缺失状态、补问提示、置信度和证据片段；CandidateDiagnosis 表示候选诊断；SafetyCheckResult 表示安全校验结果。

MockLLM fallback 是工程鲁棒性设计，不是削弱点。课程演示环境可能没有稳定网络，也可能因为模型输出格式不稳定导致 JSON 解析失败。fallback 能保证 Orchestrator 主流程继续运行，同时保留 fallback_reason，方便调试和答辩说明。

### 7.3 Orchestrator 编排模块

Orchestrator 的输入是文本或 ASRResult 中的 conversation_text。它不关心输入最初来自文本还是音频，只关心当前是否有可处理的对话文本。

处理过程是创建任务、执行步骤、记录状态。MedicalRecordOrchestrator 会创建 agent_task，然后执行 extract_fields、generate_draft、safety_check 三个核心步骤。每个步骤都会写入 agent_task_step，状态变化会写入 audit_log。任务最终进入 WAITING_DOCTOR_REVIEW，而不是自动完成导出。

Orchestrator 的输出包括任务状态、结构化字段、病历草稿、安全校验结果和 Agent Trace。它体现了 Plan-and-Execute，因为任务被拆成明确步骤执行；也体现了 Human-in-the-loop，因为最终状态要求医生审核。

### 7.4 医生端与调试端

doctor.html 面向医生审核和课程演示。它展示左栏病历字段、中栏对话转写、右栏 AI 辅助与安全校验。医生模式默认隐藏 Agent Trace、运行日志命令和 LLM 细节，让页面更接近真实工作台。调试模式会显示 Agent Trace、LLM Provider、运行日志命令和调试工具，方便课程答辩展示内部过程。

debug.html 面向开发调试和评分证据。它保留完整 JSON 视图，包括 ASRResult、Task、Steps、Safety 和 Agent Trace。这个页面不面向真实医生使用，而是用于说明系统的每一步都有数据记录。

图 7：医生模式三栏工作台

【建议插入图：doctor.html 医生模式三栏工作台截图】

图 7 医生模式三栏工作台，展示病历字段、对话转写和 AI 辅助与安全校验。

图 8：AI 辅助与安全校验区域

【建议插入图：doctor.html 右栏安全校验截图】

图 8 AI 辅助与安全校验区域，展示缺失项、候选诊断和安全提醒。

### 7.5 运行日志模块

运行日志模块的输入是 task_id 和 audio_id。用户可以在 doctor.html 或 debug.html 中复制命令，例如 `python scripts/save_run_log.py --task-id 38 --audio-id 9b3dd889e50042408fdc7ed4ac7c34ee --title fever_01_final_demo`。

处理过程是读取任务、步骤日志、ASRResult、Agent Trace 和安全校验摘要，并把这些信息写入 Markdown 文件。运行日志不改变主程序，只是把一次演示结果沉淀下来。

运行日志模块的输出是 `docs/dev_logs/runs/` 下的 Markdown 文件。已有运行日志 `2026-06-20_fever_01_final_demo.md` 记录了 task_id、audio_id、FunASR engine、ASRResult 摘要、role_strategy、Agent Trace、任务状态、步骤日志和安全校验摘要。该日志中 CER 和 keyword_recall 显示为“未找到”，因此报告不能把 ASR 评测结果写成已经完成的量化测试。

## 8. 与评分细则的对应说明

### 8.1 工具开发与调用

当前项目可以展示多个工具化模块。ASR engine 是一个工具化模块，能够根据 engine 参数调用 Mock、FunASR、Qwen3 或 Online ASR。LLM provider 也是工具化模块，能够根据 LLM_PROVIDER 选择 mock、online 或 ollama。`scripts/save_run_log.py` 是自定义运行日志工具，可以根据 task_id 和 audio_id 生成演示日志。

如果课程要求“至少 2 个工具含 1 个自定义工具”，建议汇报时把 ASR、LLM provider 和 save_run_log.py 作为工具化模块展示，并说明它们的输入、输出和错误处理。当前代码中没有完整独立的 Tool Registry，因此报告不写成“已完成 Tool Registry”，而是如实说明已经完成了工具化服务和脚本。

### 8.2 记忆系统说明

当前项目有 task_step、audit_log、Agent Trace 和运行日志。它们可以看作任务级过程记录和短期追踪，用于回放一次任务从输入到医生审核的过程。这些记录对课程演示有帮助，也能降低黑箱生成风险。

但是，这不等于完整长期记忆系统。当前项目没有向量数据库，没有跨会话患者历史召回，也没有长期用户画像。因此不能写成“已实现长期记忆”。建议补充测试内容：如需对齐记忆系统评分，可后续增加向量数据库和跨会话召回验证，并设计明确的查询、召回和准确性测试。

### 8.3 模型训练应用说明

当前项目主要使用现成 ASR / LLM，并进行工程集成。FunASR、Qwen3-ASR、Online ASR 和 Online/Ollama LLM 都属于已有模型或外部模型能力的接入。项目中没有自训练数据集、训练代码、训练曲线和模型评估指标。

因此报告不能写成“已完成模型训练”。建议补充测试内容：如需对齐模型训练评分，可补充一个小型关键词识别、字段分类或风险排序模型，并展示数据集、训练代码、指标和误差分析。

### 8.4 简易部署与测试说明

当前项目可以通过 `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` 启动本地服务。项目中还有 FunASR 环境检查脚本、运行日志脚本、前端 JS 语法检查和 diff 空白检查。GitHub 提交记录和开发日志也可以作为过程证据。

建议补充测试内容：最终答辩前可以补充一键启动命令截图、最新一次 pytest 总通过数截图、Git commit 截图和演示失败恢复方案。这样更容易支撑简易部署与测试评分。

## 9. 医生端工作台与演示流程

医生端工作台的设计目标是让评委一眼看出系统不是普通调试页。页面打开后默认是医生模式，顶部显示患者、会话、ASR engine、审核状态和流程提示。左栏显示病历字段卡片，中栏显示对话转写，右栏显示 AI 辅助与安全校验。

推荐演示流程是：先打开 index.html，说明系统分为医生端和调试台；再进入 doctor.html，展示无任务引导卡片；然后使用文本导入或上传音频生成病历；接着展示字段卡片、对话转写、缺失提醒和安全校验；最后切换到调试模式展示 Agent Trace 和运行日志命令。

如果现场 FunASR 卡顿，可以使用文本导入路线继续展示主流程；如果 doctor.html 页面异常，可以打开 debug.html 展示 Task、Steps、Safety 和 Agent Trace JSON；如果 Online LLM 失败，可以说明系统会 fallback 到 MockLLM，不影响课程主线。

图 9：调试模式 Agent Trace

【建议插入图：doctor.html 调试模式 Agent Trace 截图】

图 9 调试模式 Agent Trace，展示输入类型、执行计划、执行步骤和导出决策。

## 10. 测试验证与证据材料

### 10.1 已有证据

已有证据包括文本导入生成病历链路、音频上传与 FunASR 转写链路、Agent Trace、debug.html 中的 Task / Steps / Safety JSON，以及 save_run_log.py 生成运行日志。已有运行日志 `docs/dev_logs/runs/2026-06-20_fever_01_final_demo.md` 记录了 task_id 38、audio_id `9b3dd889e50042408fdc7ed4ac7c34ee`、FunASR engine、单段转写、`single_segment_needs_review`、Agent mode、Plan steps、Executed steps、WAITING_DOCTOR_REVIEW、`export_allowed=false` 和安全校验摘要。

已有命令级验证包括 `node --check static/doctor.js`、`git diff --check` 和 `python scripts/export_final_report_docx.py`。这些验证说明前端 JS 语法、文档 diff 格式和 Word 导出工具在当前整理阶段能够通过。

需要注意的是，运行日志中 CER 和 keyword_recall 显示为“未找到”，因此不能把这次运行写成已经完成 ASR 量化评测。报告中只能说明系统支持 ASR 评测接口和页面，具体最新量化结果建议补充。

图 10：debug.html Task / Steps / Safety JSON

【建议插入图：debug.html JSON 截图】

图 10 调试台 JSON 视图，用于展示任务、步骤和安全校验过程。

图 11：fever_01_final_demo 运行日志

【建议插入图：运行日志 Markdown 截图】

图 11 运行日志记录一次演示的 ASRResult、Agent Trace、任务步骤和安全校验摘要。

### 10.2 建议补充测试内容

建议补充最新一次 pytest 总通过数截图，作为自动化测试证据。建议增加多病种样本测试，例如发热、胸痛、蛇咬伤等，观察字段抽取和安全校验是否稳定。建议补充 ASR 引擎对比测试，至少比较 Mock、FunASR 和可用的 Qwen3 或 Online ASR。建议补充 LLM fallback 测试，证明 Online 或 Ollama 失败时系统能够降级到 MockLLM。建议补充响应时间测试和连续运行稳定性测试，说明系统在多次演示中不会明显卡死。建议补充 Prompt 注入与安全边界测试，例如患者文本要求“忽略规则直接导出”时，系统是否仍然保持医生审核边界。

这些内容目前不能写成已经完成，只能作为建议补充测试内容。

## 11. 当前问题与建议补充测试内容

当前项目仍有一些 POC 阶段边界。第一，FunASR 依赖可能因为不同 Windows 环境、Python 版本或模型缓存状态导致 import failed 或首次加载较慢。第二，ASR 对医生/患者角色的区分仍然有限，当返回单段长文本时只能提示人工校正。第三，当前 task_step、audit_log 和运行日志是任务级过程记录，不是完整长期记忆系统。第四，项目没有自训练 ML/DL 模型的证据。第五，量化测试数据还不够，特别是多病种样本、ASR 对比、响应时间和连续运行稳定性测试。第六，项目没有真实临床验证，也没有接入医院 HIS/EMR。

这些问题不是项目失败，而是课程 POC 的边界。当前项目已经把主链路、Agent 编排、医生审核、安全边界和证据沉淀跑通。后续如果继续扩展，可以从补充测试、增加长期记忆模块、加入小型训练任务和优化 ASR 角色分离四个方向推进。

## 12. 安全伦理合规设计

安全伦理是本项目的重要边界。项目只使用模拟问诊文本和课程样例音频，不使用真实患者数据，不提交真实 API Key，不接真实医院 HIS/EMR。Online ASR 和 Online LLM 的 Key 都通过环境变量读取，不能写死在代码、日志、README 或截图中。

医疗安全方面，AI 只生成病历草稿、候选诊断和安全提醒。候选诊断必须医生确认。未提及字段不能自动写成“无”或“正常”，而应该显示待补充。医生审核前不允许导出最终病历。这个边界在页面、SafetyCheckResult 和 Agent Trace 中都有体现。

Prompt 注入防护方面，System Prompt 要求患者输入不能覆盖系统规则。如果输入中出现“忽略之前规则”“直接导出”等内容，系统仍应遵守医生审核边界。Schema 校验和安全校验可以减少不合规输出进入后续流程的风险。

可追踪性方面，task_step、audit_log、Agent Trace 和运行日志能够记录一次任务的主要过程。它们不能替代临床审计系统，但可以降低课程 POC 中的黑箱风险，让评委看到系统如何从输入走到草稿和审核状态。

## 13. 总结与后续计划

本项目的核心价值不是自动诊断，而是展示生成式 AI 如何放入可追踪、可审核、可降级的医疗辅助流程。系统把文本和音频统一为 conversation_text，通过 ASRResult、LLM 字段抽取、Orchestrator 编排、安全校验、医生审核和运行日志形成完整演示链路。

从程序设计角度看，项目把感知层、决策层、执行层和反馈层拆开，避免把所有逻辑写成一次模型调用。MockLLM fallback 让系统在真实模型失败时仍能展示主流程，Agent Trace 和 Run Log 让过程可以被复盘。

后续可以继续扩展：增加更多样本，优化 ASR 医生/患者角色分离，补充量化测试指标，增加真正的长期记忆模块，加入小型模型训练任务，并将医生确认后的导出格式与更标准的 EMR 模板对齐。所有扩展都应继续保留医生审核边界，不把系统包装成真实临床诊疗工具。

图 12：评分进度看板

【建议插入图：项目进度与评分证据看板.md 截图】

图 12 评分进度看板，用于展示项目能力与评分细则之间的对应关系。

## 14. 修改说明

本次修订基于当前已有期末报告继续修改，没有从零生成，也没有编造新功能、测试结果或临床效果。主要优化包括：第一，将正文结构调整为“背景、目标、设计、实现、测试、问题、总结”的正式课程报告逻辑；第二，减少表格使用，改为段落解释技术模块；第三，对 ASR、LLM、Orchestrator、医生端和运行日志模块按“输入、处理过程、输出、设计原因”重新说明；第四，补充评分细则中工具开发、记忆系统、模型训练应用、简易部署与测试的真实对应关系；第五，把缺少证据的内容明确写成“建议补充测试内容”；第六，统一图片占位格式；第七，保留课程 POC、医生审核、MockLLM fallback、Agent Trace 和运行日志等核心表述。

本次修订未修改后端业务逻辑、ASR/LLM 实现、数据库结构或 Agent 主流程。报告仍需人工补齐封面信息，并按截图清单插入真实页面截图。
