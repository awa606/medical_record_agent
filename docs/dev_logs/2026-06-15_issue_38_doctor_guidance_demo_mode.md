# Issue #38 医生端引导、栏目说明与演示模式优化

## 修改日期 / 时间

2026-06-15，时区：Asia/Shanghai

## 修改目标

完成 Issue #38：让 `doctor.html` 更面向医生和课程评委，减少默认调试感，增加开始引导、当前步骤提示、栏目用途说明，并提供医生模式 / 调试模式切换。

## 修改前问题

- 医生端功能完整，但默认展示运行日志、LLM 细节、ASR 评测和 Agent Trace，观感偏调试端。
- 无任务时缺少明确的“从哪里开始”的引导。
- 三栏用途说明偏短，评委第一次看页面时不容易理解每栏作用。
- 顶部按钮过多，主操作和调试操作混在一起。

## 输入

- Issue #38 用户需求。
- 现有医生端三栏工作台：`static/doctor.html`、`static/doctor.css`、`static/doctor.js`。
- 现有后端接口、ASR/LLM 配置和 `fever_01.wav` 演示链路。

## 输出

- 新增“开始一次病历生成”引导卡片，无任务时显示。
- 新增“当前步骤提示条”，根据任务状态和风险状态显示人话提示。
- 三栏标题下补充用途说明。
- 新增医生模式 / 调试模式切换，默认医生模式。
- 医生模式隐藏 Agent Trace、运行日志命令、ASR 评测、LLM 细节和调试页入口。
- 调试模式显示 Agent Trace、LLM provider、运行日志命令、ASR 评测、LLM 自检和调试页入口。
- 顶部主操作只保留“上传音频”和“文本导入”，调试功能放入“调试工具”。
- 继续保留右栏风险项折叠和滚动逻辑。

## 修改文件

- `static/doctor.html`
- `static/doctor.css`
- `static/doctor.js`
- `docs/dev_logs/2026-06-15_issue_38_doctor_guidance_demo_mode.md`

## 关键设计决策

- 不改后端接口，不新增 ASR / LLM，只通过前端状态控制展示。
- 默认医生模式，避免课程演示一打开就出现过多调试信息。
- 调试能力不删除，只折叠到调试模式和“调试工具”区域，便于答辩时按需展示。
- 右栏蓝色辅助信息和绿色通过项默认折叠；红色风险和黄色待确认项默认展开。

## 验证步骤

1. 运行 `node --check static\doctor.js`。
2. 运行 `git diff --check -- static\doctor.html static\doctor.css static\doctor.js docs\dev_logs\2026-06-15_issue_38_doctor_guidance_demo_mode.md`。
3. 打开 `/static/doctor.html`，检查默认医生模式、开始引导、步骤提示、调试模式切换和调试工具显示。

## 验证结果

- `node --check static\doctor.js` 通过。
- `git diff --check -- static\doctor.html static\doctor.css static\doctor.js docs\dev_logs\2026-06-15_issue_38_doctor_guidance_demo_mode.md` 通过。
- 本地启动 `uvicorn app.main:app --host 127.0.0.1 --port 8010`，`/health` 返回 `{"status":"ok"}`。
- 浏览器打开 `/static/doctor.html` 后默认进入医生模式：开始引导卡片可见，当前步骤提示为“请上传问诊音频或粘贴问诊文本开始。”，Agent Trace、LLM 细节、运行日志命令、ASR 评测和调试工具默认隐藏。
- 切换到调试模式后：LLM Provider、运行日志命令、调试工具和 Agent Trace Tab 可见；页面无横向滚动条。

## 未解决问题

- 本次只做医生端引导和展示层优化，没有重新执行真实 `fever_01.wav` 上传生成病历；既有 fever_01 演示链路未改动。

## 下一步计划

- 演示前使用 fever clean 文本和 `fever_01.wav + FunASR` 各跑一次，确认医生模式展示节奏。
