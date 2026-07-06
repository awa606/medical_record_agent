# 2026-06-08 Issue #29 评分对照与开发日志机制

## 修改日期 / 时间

2026-06-08，时区：Asia/Shanghai

## 修改目标

完成 GitHub Issue #29：建立课程评分冲刺所需的开发日志规范和评分对照文档，让后续汇报能按 issue、开发日志、代码证据和评分点串联展示。

## 修改前问题

- 已有 `docs/dev_logs/` 和回顾日志，但缺少明确的 `DEVELOPMENT_RULES.md`。
- 已有根目录 `docs/course_scoring_plan.md`，但缺少 Issue #29 指定的 `docs/scoring/` 评分证据目录。
- 开发日志模板字段与 issue 描述存在轻微命名差异。

## 输入

- GitHub Issue #29：课程评分冲刺 P0：建立开发日志与评分对照文档。
- 当前项目已有的 README、开发日志、Agent、ASR 和前端工作台材料。

## 输出

- 新增 `docs/scoring/course_scoring_plan.md`。
- 新增 `docs/dev_logs/DEVELOPMENT_RULES.md`。
- 更新 `docs/dev_logs/TEMPLATE.md` 的字段命名。
- 新增本次 Issue #29 开发日志。

## 修改文件

- `docs/scoring/course_scoring_plan.md`
- `docs/dev_logs/DEVELOPMENT_RULES.md`
- `docs/dev_logs/TEMPLATE.md`
- `docs/dev_logs/README.md`
- `README.md`
- `docs/dev_logs/2026-06-08_issue_29_scoring_dev_logs.md`

## 关键设计决策

- 保留已有回顾性日志，不复制一套内容相同但命名不同的版本日志，避免课程材料重复。
- 新增 `docs/scoring/` 作为正式评分材料目录，根目录旧评分文档继续保留为早期总览。
- 开发规范强调 issue 驱动、日志同步、验证记录和禁止提交真实患者数据/API Key。

## 验证步骤

1. 使用 `rg --files docs` 检查新增文档是否存在。
2. 使用 `python -m py_compile app/prompts/medical_record_prompts.py` 检查 Prompt 示例代码语法。
3. 使用 `python -m pytest` 确认没有影响现有业务测试。

## 验证结果

- `rg --files docs` 可检出 `docs/scoring/course_scoring_plan.md`、`docs/dev_logs/DEVELOPMENT_RULES.md` 和本次 issue 日志。
- `python -m py_compile app/prompts/medical_record_prompts.py` 通过。
- `python -m pytest` 通过，结果：56 passed。

## 未解决问题

- Issue #29 不要求新增截图；后续汇报可补医生端、调试台和任务步骤截图。

## 下一步计划

- Issue #30 和 Issue #31 已在本轮继续完成；汇报前补充页面截图和 Mermaid 图导出即可。
