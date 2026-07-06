# Issue #37 医生端结果保存、右栏分区优化与演示样本沉淀

## 修改日期 / 时间

2026-06-11 15:05，时区：Asia/Shanghai

## 修改目标

完成 Issue #37：明确医生端“保存草稿”的真实行为，补充 `task_id` / `audio_id` / 运行日志命令展示，优化右栏信息密度，并让 `fever_01.wav + FunASR` 演示结果可以沉淀为运行日志。

## 修改前问题

- 医生端按钮写作“保存草稿”，但页面没有说明它是否写 SQLite、是否保存 ASRResult、是否保存 Agent Trace、是否生成文件。
- 医生端右栏将缺失项、诊断、证据、评测、Agent Trace 和安全校验堆叠展示，演示时信息过于拥挤。
- 用户跑通 `fever_01.wav + FunASR` 后，需要手工查找 `task_id`、`audio_id` 才能生成运行日志。
- 调试台可以看 JSON，但没有直接展示运行日志生成命令。

## 输入

- Issue #37 用户需求。
- 现有接口：`POST /api/tasks/{task_id}/review`、`POST /api/tasks/{task_id}/export`、`GET /api/tasks/{task_id}/trace`。
- 现有运行日志脚本：`scripts/save_run_log.py`。
- 现有医生端与调试台：`static/doctor.html`、`static/debug.html`。

## 输出

- 医生端新增当前 `task_id`、`audio_id` 和运行日志命令状态条。
- 医生端新增“复制运行日志命令”按钮。
- “保存草稿”改名为“保存草稿到SQLite”，并在右栏说明保存边界。
- 右栏拆成四个 Tab：AI辅助、证据与评测、Agent Trace、安全校验。
- 调试台顶部显示当前 `task_id`、`audio_id`，工具栏增加“复制运行日志命令”。
- 调试抽屉新增运行日志命令和草稿保存说明。
- 文档补充运行日志生成方式、草稿查看位置和演示验收项。

## 修改文件

- `static/doctor.html`
- `static/doctor.css`
- `static/doctor.js`
- `static/debug.html`
- `static/main.js`
- `static/style.css`
- `docs/dev_logs/runs/README.md`
- `docs/scoring/demo_checklist.md`
- `docs/scoring/demo_script.md`
- `docs/dev_logs/2026-06-11_issue_37_save_draft_run_context.md`

## 关键设计决策

- 不改后端保存语义：继续使用现有 `review_task` 接口，将医生端字段保存到 SQLite 的 Task `result_json`，避免破坏稳定演示链路。
- 不把 ASRResult 和 Agent Trace 混入“保存草稿”按钮：ASRResult 仍由转写流程保存到上传目录，Agent Trace 继续动态组装。
- 运行日志不自动生成文件：页面只提供命令，是否生成和提交具体运行日志由演示者按需执行，避免误提交敏感或临时数据。
- 右栏使用 Tab 而不是继续堆叠卡片：保留全部信息，但降低医生端首屏拥挤度。

## 验证步骤

1. 运行 `node --check static\doctor.js`。
2. 运行 `node --check static\main.js`。
3. 运行 `git diff --check -- static docs scripts app tests`。
4. 运行 `python -m pytest`。
5. 启动 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8010`。
6. 打开 `/static/doctor.html`，检查 task/audio、复制命令、SQLite 保存按钮和右栏 Tab。
7. 打开 `/static/debug.html`，检查 task/audio、复制命令、调试抽屉运行日志命令和保存说明。

## 验证结果

- `node --check static\doctor.js`：通过。
- `node --check static\main.js`：通过。
- `git diff --check -- static docs scripts app tests`：通过。
- `python -m pytest`：70 passed。
- 浏览器烟测 `/static/doctor.html`：能看到当前 `task_id`、`audio_id`、运行日志命令、复制按钮、“保存草稿到SQLite”和四个右栏 Tab。
- 浏览器烟测 `/static/debug.html`：能看到顶部 `task_id` / `audio_id`、复制运行日志命令按钮，调试抽屉能看到运行日志命令和草稿保存说明。

## 未解决问题

- 本次没有真实执行 `fever_01.wav` 上传和日志生成，只验证页面能力和现有测试链路。
- 运行日志具体 Markdown 文件仍按需生成，不默认提交。

## 下一步计划

- 演示前用 `fever_01.wav + FunASR` 完整跑一次，复制页面命令生成 `docs/dev_logs/runs/YYYY-MM-DD_fever_01_demo.md`。
- 如课程要求留存演示结果，再选择性提交脱敏后的运行日志。
