# 2026-06-10 课程演示材料最后整理

## 修改日期 / 时间

2026-06-10，时区：Asia/Shanghai

## 修改目标

整理课程正式汇报材料，不新增业务功能，不改后端、前端或 ASR。将现场演示讲稿从 5-8 分钟版本改为 12-15 分钟正式汇报版本，并补齐评分文档之间的引用。

## 修改前问题

- `docs/scoring/demo_script.md` 仍是短演示版本，不适合 12-15 分钟正式汇报。
- 部分评分文档之间缺少统一的相关文档导航。
- `docs/dev_logs/runs/` 缺少 README，运行日志生成方式没有目录级说明。

## 输入

- 用户要求：不要新增业务功能，只做课程演示材料最后整理。
- 评分相关文档：`docs/scoring/course_scoring_plan.md`、`agent_design.md`、`decision_system.md`、`prompt_chain_design.md`、`ethics_compliance.md`、`code_walkthrough.md`、`demo_checklist.md`。
- 运行日志脚本：`scripts/save_run_log.py`。

## 输出

- `docs/scoring/demo_script.md` 更新为 12-15 分钟正式汇报讲稿。
- 评分文档增加相关文档导航。
- 新增 `docs/dev_logs/runs/README.md`。
- 新增本次开发日志。

## 修改文件

- `docs/scoring/demo_script.md`
- `docs/scoring/course_scoring_plan.md`
- `docs/scoring/agent_design.md`
- `docs/scoring/decision_system.md`
- `docs/scoring/prompt_chain_design.md`
- `docs/scoring/ethics_compliance.md`
- `docs/scoring/code_walkthrough.md`
- `docs/scoring/demo_checklist.md`
- `docs/dev_logs/runs/README.md`
- `docs/dev_logs/2026-06-10_final_demo_materials.md`

## 关键设计决策

- 只修改课程汇报文档，不改任何业务代码。
- 时间分配严格覆盖项目背景、Agent 设计、决策系统和 Prompt 链、伦理合规、系统演示、代码展示。
- 保留 `fever_01.wav` 主线，同时加入 ASR 卡顿备用话术，降低现场演示风险。
- 运行日志目录说明强调具体日志可按需提交，不能提交真实患者数据或敏感信息。

## 验证步骤

1. 使用 `rg --files docs/scoring docs/dev_logs` 检查文档存在。
2. 使用 `rg "相关文档|12-15|fever_01.wav|ASR 卡顿|代码展示" docs/scoring docs/dev_logs/runs/README.md` 检查关键内容。
3. 使用 `git status --short -- docs/scoring docs/dev_logs` 检查本次修改范围。

## 验证结果

- `rg --files docs/scoring docs/dev_logs` 可检出评分文档、开发日志模板、回顾日志和 `docs/dev_logs/runs/README.md`。
- `rg "12-15|fever_01.wav|ASR 卡顿|代码展示" docs/scoring/demo_script.md` 可检出正式汇报时间、主线、备用方案和代码展示话术。
- `rg "相关文档" docs/scoring` 可检出评分文档之间的互引导航。
- `git status --short -- docs/scoring docs/dev_logs` 确认本次修改范围仅限课程文档和开发日志。

## 未解决问题

- 本次没有生成具体运行日志；实际汇报前可用 `scripts/save_run_log.py` 按需生成。

## 下一步计划

- 汇报前按 `docs/scoring/demo_checklist.md` 做一次完整演示自检。
