<!-- project-engineering-design-review:start -->
## Project Management / Research / Engineering Design Routing

项目管理、方案研究与工程设计按意图和门禁顺序分流。以下路径为当前用户级Skill；适用时必须实际读取，不能只输出激活标记。

- **PROJECT MANAGEMENT**：项目状态、今天做什么、既有任务/WBS维护、延期、甘特、看板、依赖、关键路径、里程碑、风险、Verification、Evidence、周报、复盘和阶段Exit判断，优先使用 `C:\Users\AWA007\.agents\skills\obsidian-project-manager\SKILL.md`。第一条状态包含 **老公｜Obsidian Project Manager Skill 已启用**，先读取项目首页、WBS、Tasks、Gate、风险、验证和对应Git状态，执行SYNC → ASSESS → UPDATE → PRIORITIZE → REPORT。
- **RESEARCH FIRST**：非平凡工作涉及模型、Library、Framework、硬件、基础设施、算法、存储或集成方案取舍时，使用 `C:\Users\AWA007\.agents\skills\research-first-engineering\SKILL.md`。第一条状态包含 **老公｜Research First Engineering Skill 已启用**，先查内部资产，再查官方与成熟方案，比较候选并为决策关键Unknown设计最小Spike。必要Spike未执行时Gate为NEEDS MORE EVIDENCE，不能填写REUSE/ADAPT/BUILD。
- **ENGINEERING DESIGN**：新项目、复杂Feature、系统设计、架构、新模块、模块拆分、接口设计、重大重构和新工程工作的WBS设计，优先使用 `C:\Users\AWA007\.agents\skills\project-engineering-design-review\SKILL.md`。存在方案取舍时必须先有Research PASS，并将Research Decision Record作为设计输入；第一条适用状态包含 **老公｜Engineering Design Review Skill 已启用**。
- **MIXED**：按PM → Research → Design Review顺序推进。请求一开始同时包含状态检查和方案研究时，首条包含PM与Research标记；Design标记只在Research PASS后出现。已Research PASS或明确无需Research的状态加设计请求可在首条包含PM与Design标记。中途切换时输出新标记并真实加载，不追溯声称此前已启用。
- **SMALL CHANGE**：文字、简单配置、明确局部Bug无需完整15步，仍执行Hypothesis → Minimal Test → Fix → Verification。纯日常管理不因跨多个笔记升级为工程设计。

普通状态查询允许在授权内同步有事实依据的管理变更；无新事实不写文件。只读、Plan和dry-run不修改Vault、Skill、规则或业务文件，不能借Obsidian IPC/API写入绕过模式。设计/方案请求即使Gate PASS也停在业务编码前。代码完成先VERIFY，只有交付物、全部验收、真实Evidence及核验人/时间齐备才能DONE；任务完成不替代阶段Gate。

Project OS继续使用六态`backlog / ready / in_progress / blocked / verify / done`。Research与Design使用独立门禁字段；当前策略任务只有Research与Design均PASS或明确不适用后才能进入READY/IN PROGRESS。`pre_policy`保留既有执行状态并显示研究债务，不得借此扩展任务范围。

执行环境已位于Git工作树时，该命令工作目录是本轮当前代码事实来源；其他同名仓库或历史checkout仅作比较，除非用户明确指定切换。不得检查多个仓库后静默用另一个路径的分支、HEAD或工作树状态作为“当前”。

PM的正式任务删除、Phase迁移、Gate标准修改、大规模WBS调整、同一请求累计超过5个不同任务日期调整、阶段范围/Roadmap变化、Evidence删除，须先给具体前后变更摘要并等待确认；不拆批规避，已批准具体摘要不重复询问。日常增量维护必须保留现有人工更新；写入门禁和阈值细则读取PM Skill及操作参考。

信息不足先查现有资料，记录编号Assumption并继续独立工作；仅真正阻塞或重大不可逆选择才询问。Skill缺失先查其他位置，仍缺失则说明，不能假装已加载。不因“长期助手”创建未请求的后台自动化。
<!-- project-engineering-design-review:end -->

<!-- medical-record-agent-project-os:start -->
## Medical Record Agent：当前计划与代码事实

本项目日常计划以 Obsidian Project OS Markdown 为准。开展 Alpha 设计评审、任务选择、WBS、依赖、排期、风险和验收工作时，先读取：

- [项目首页](C:/Users/AWA007/Desktop/Data/开题报告/PAMI_ProjectLab/obsidian/PAMI_Project_Vault/Projects/Medical_Record_Agent/00_Project_Home.md)
- 任务事实目录：`C:\Users\AWA007\Desktop\Data\开题报告\PAMI_ProjectLab\obsidian\PAMI_Project_Vault\Projects\Medical_Record_Agent\Tasks`

当前批准追赶基线是15个正式叶子任务、87h、2026-09-07至2026-10-01（课程周次从W03连续计算）、单人工作日每天最多6h；负责人李国毅。M1–M4日期依次为2026-09-17、09-21、09-25、10-01。正式日期、任务状态、依赖及实际证据以该目录的最新Markdown为准，更新前检查下游及容量。本段用于识别迁移后的基线，不能覆盖后续经授权的计划调整。

仓库 `docs/project_plan/alpha`、历史Canonical中的120h或旧5.5缓冲仅作为历史比较，不得用于覆盖当前15任务计划或增加可用容量。仓库当前工作树、Git历史和真实测试用于核实实现事实；代码存在不代表任务验收通过。评审应引用当前Vault任务并说明与历史计划或代码基线的差异，避免另建一套独立WBS。
<!-- medical-record-agent-project-os:end -->
