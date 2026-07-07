# 评分进度看板与期末报告初稿整理

## 修改日期 / 时间

2026-06-20，时区：Asia/Shanghai

## 修改目标

根据当前项目代码、评分细则、开发日志和 `docs/scoring/` 已有文档，整理课程汇报最后阶段材料：

- 更新 `docs/scoring/项目进度与评分证据看板.md`，形成评分细则与当前完成内容的对照看板。
- 新增 `docs/scoring/final_report_draft.md`，形成期末报告完整初稿。

## 修改前问题

- 进度看板已有主链路和完成度信息，但与“智能体设计模式、决策系统设计、伦理合规设计、演示流畅度、表达与逻辑、代码展示”六个评分项的逐项对应还不够集中。
- 项目已有多个评分支撑文档，但缺少一份可以直接扩写成期末报告的完整初稿。
- 需要在报告中明确项目是课程 POC 原型，避免夸大为真实临床系统。

## 输入

- 用户指令：生成 `docs/scoring/项目进度与评分证据看板.md` 和 `docs/scoring/final_report_draft.md`。
- 现有评分文档：`course_scoring_plan.md`、`agent_design.md`、`decision_system.md`、`prompt_chain_design.md`、`ethics_compliance.md`、`code_walkthrough.md`、`demo_script.md`。
- 现有开发日志：`docs/dev_logs/`。
- 当前代码：Orchestrator、ASR factory、LLM provider、Agent Trace、Schema、医生端和调试台。

## 输出

- 评分进度看板：按六个评分项列出满分要求、当前完成内容、可展示证据、风险、下一步。
- 期末报告初稿：覆盖项目背景、需求分析、系统架构、Agent 设计、决策系统、ASR/LLM、医生端、安全伦理、核心代码、测试验证、开发日志、总结与后续计划。
- 明确强调 `Plan-and-Execute + Human-in-the-loop`、AI 只生成草稿、医生最终审核、MockLLM fallback 的工程意义。

## 修改文件

- `docs/scoring/项目进度与评分证据看板.md`
- `docs/scoring/final_report_draft.md`
- `docs/dev_logs/2026-06-20_scoring_final_report_materials.md`

## 关键设计决策

- 报告中不把系统描述为真实临床产品，而是明确为课程 POC。
- 评分看板直接按评分项组织，方便汇报前快速查证。
- 报告初稿保留技术证据文件路径，便于后续扩写和现场代码展示。
- 保留 MockLLM fallback 的正向解释：它不是削弱能力，而是保证演示稳定、异常可控和 Orchestrator 不被外部模型波动破坏。

## 验证步骤

1. 检查新增与更新的 Markdown 文件是否存在。
2. 检查文档中关键评分项、章节标题和项目边界是否齐全。
3. 运行 `git diff --check` 检查空白错误。

## 验证结果

- `git diff --check -- docs/scoring/项目进度与评分证据看板.md docs/scoring/final_report_draft.md docs/dev_logs/2026-06-20_scoring_final_report_materials.md` 通过。
- 已确认三个文件均存在。
- 已用 `rg` 检查评分项关键词：智能体设计模式、决策系统设计、伦理合规设计、演示流畅度、表达与逻辑、代码展示均已出现在进度看板中。
- 已用 `rg` 检查报告章节：项目背景与目标、需求分析、系统总体架构、智能体设计模式、决策系统与 Prompt 链、ASR 与 LLM 模块、医生端工作台、安全伦理合规、核心代码实现、测试验证、开发日志、总结与后续计划均已覆盖。

## 未解决问题

- 报告仍是初稿，后续可以根据课程模板补充封面、摘要、参考资料和截图。
- 本次只整理文档，不重新运行 `fever_01.wav` 演示链路。

## 下一步计划

- 汇报前把 `final_report_draft.md` 扩写为正式提交版。
- 根据演示当天实际 `task_id` 和 `audio_id` 生成一份运行日志，作为报告附录证据。
