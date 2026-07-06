# 2026-06-10 Issue #33 Agent 能力可见化与决策闭环

## 修改日期 / 时间

2026-06-10，时区：Asia/Shanghai

## 修改目标

完成 GitHub Issue #33：让当前系统中的 Agent 能力在页面、日志和文档中显性化，补强“感知 -> 计划 -> 执行 -> 安全校验 -> 医生审核 -> 反馈日志”的决策闭环。

## 修改前问题

- 医生端和调试端能看到任务、步骤和安全校验，但没有统一的 Agent Trace。
- 运行日志缺少 Agent mode、Plan steps、Decision summary、Human-in-the-loop 和导出决策。
- 课程文档对 MockLLM / deterministic extractor 与真实 LLM 接入契约的解释还不够显性。

## 输入

- GitHub Issue #33：课程评分冲刺 P4：让 Agent 能力可见化并补强决策闭环。
- 现有 `agent_task`、`agent_task_step`、`ASRResult`、`SafetyCheckResult`。
- 现有医生端 `doctor.html` / `doctor.js` 和调试端 `debug.html` / `main.js`。
- 运行日志脚本 `scripts/save_run_log.py`。

## 输出

- 新增 Agent Trace 组装服务和只读 API。
- 医生端右栏展示 Agent 决策轨迹摘要。
- 医生端和调试端调试抽屉展示完整 Agent Trace JSON。
- 运行日志增加 Agent Trace / Decision Loop。
- 文档补充 MockLLM / deterministic extractor、Prompt 契约和未来 LLM adapter 替换方式。

## 修改文件

- `app/services/agent_trace.py`
- `app/api/tasks.py`
- `static/doctor.html`
- `static/doctor.js`
- `static/debug.html`
- `static/main.js`
- `scripts/save_run_log.py`
- `tests/test_tasks_api.py`
- `tests/test_save_run_log.py`
- `docs/scoring/course_scoring_plan.md`
- `docs/scoring/code_walkthrough.md`
- `docs/scoring/demo_checklist.md`
- `docs/scoring/demo_script.md`
- `docs/scoring/prompt_chain_design.md`
- `docs/dev_logs/2026-06-10_issue_33_agent_trace.md`

## 关键设计决策

- 不改数据库结构，Agent Trace 基于现有 task、steps、ASRResult 和 SafetyCheckResult 动态组装。
- `decision.export_allowed` 固定为 `false`，`decision.reason` 固定为 `doctor_review_required`，强调 AI 不允许自动导出最终病历。
- 不新增 ASR，不接真实 LLM，不接真实患者数据，不影响 `fever_01.wav` 演示主线。
- 真实 LLM 后续通过 adapter 替换 MockLLM，不改变 Orchestrator 主流程。

## 验证步骤

1. 运行 `python -m py_compile app/services/agent_trace.py scripts/save_run_log.py`。
2. 运行 `node --check static/doctor.js`。
3. 运行 `node --check static/main.js`。
4. 运行 `python -m pytest tests/test_tasks_api.py tests/test_save_run_log.py`。
5. 运行 `python -m pytest`。
6. 手动打开医生端或调试端，检查 Agent 决策轨迹和 Agent Trace JSON。

## 验证结果

- `python -m py_compile app/services/agent_trace.py scripts/save_run_log.py`：通过。
- `node --check static/doctor.js`：通过。
- `node --check static/main.js`：通过。
- `python -m pytest tests/test_tasks_api.py tests/test_save_run_log.py`：7 passed。
- `python -m pytest`：58 passed。
- 浏览器烟测：`/static/doctor.html` 能看到 Agent 决策轨迹、导出决策、医生审核边界；`/static/debug.html` 能看到 Agent Trace JSON 容器；控制台无 error。
- 正式汇报前仍建议用 `fever_01.wav` 做一次完整端到端人工验收并保存运行日志。

## 未解决问题

- 未新增真实 LLM adapter 代码；当前通过 Prompt 契约和文档说明未来替换方式。
- 未生成新的具体运行日志；实际汇报时可用 `scripts/save_run_log.py` 按需生成。

## 下一步计划

- 汇报前用 `fever_01.wav` 完整跑一次医生端演示，并保存运行日志。
