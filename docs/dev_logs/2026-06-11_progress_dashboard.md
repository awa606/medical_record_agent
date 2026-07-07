# 课程评分进度看板文档

## 修改日期 / 时间

2026-06-11 16:10，时区：Asia/Shanghai

## 修改目标

新增课程评分进度看板，用于集中展示当前项目主链路、功能完成度、评分细则对照、最稳演示路线和现场备用方案。

## 修改前问题

- 评分材料已经分散在 `course_scoring_plan.md`、`demo_script.md`、`demo_checklist.md` 等文档中，但缺少一个“当前做到哪里”的总览页。
- 汇报前需要快速判断各评分项的完成内容、可展示证据、待补充内容和风险。
- Online LLM、MockLLM fallback、FunASR 和运行日志之间的演示关系需要更直接地梳理。

## 输入

- 用户要求新增 `docs/scoring/项目进度与评分证据看板.md`。
- 现有评分材料：`docs/scoring/course_scoring_plan.md`、`docs/scoring/demo_checklist.md`。
- 当前主链路：`fever_01.wav -> FunASR -> Online LLM / MockLLM -> 字段抽取 -> 病历草稿 -> 安全校验 -> 医生审核 -> Agent Trace -> 运行日志`。

## 输出

- 新增 `docs/scoring/项目进度与评分证据看板.md`。
- 文档包含项目主链路、当前完成度表、评分细则对照表、最稳演示路线和现场备用方案。
- 本开发日志记录本次文档补充。

## 修改文件

- `docs/scoring/项目进度与评分证据看板.md`
- `docs/scoring/course_scoring_plan.md`
- `docs/scoring/demo_checklist.md`
- 本开发日志文件。

## 关键设计决策

- 将进度看板定位为汇报前总览，不替代已有评分细则文档。
- 对每个评分项同时列出“当前完成内容 / 可展示证据 / 仍需补充 / 预计得分风险”，方便现场准备。
- 将 Online LLM 作为增强能力展示，将 MockLLM fallback 作为稳定演示保障，避免现场网络或模型问题影响主线。
- 明确 FunASR 卡顿、doctor.html 异常、Online LLM 失败时的备用方案。

## 验证步骤

1. 检查 Markdown 文件是否存在。
2. 检查文档是否覆盖用户要求的 6 个部分。
3. 运行 `git diff --check`，检查本次文档变更的 Markdown 空白问题。

## 验证结果

- 文档已新增并覆盖主链路、完成度、评分对照、稳妥演示路线和备用方案。
- `git diff --check`：通过。
- `rg` 检查确认文档包含 fever_01、FunASR、Online LLM、MockLLM fallback、评分项、最稳演示路线和现场备用方案。

## 未解决问题

- 本次只补文档，没有生成新的实际运行日志。
- 具体 `fever_01_demo` 运行日志仍需在演示前用实际 `task_id` 和 `audio_id` 按需生成。

## 下一步计划

- 汇报前根据本看板逐项检查演示链路。
- 如现场需要证据沉淀，生成并提交脱敏后的 `docs/dev_logs/runs/YYYY-MM-DD_fever_01_demo.md`。
