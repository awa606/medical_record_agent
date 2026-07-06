# 医生端右栏折叠与滚动小修

## 修改日期 / 时间

2026-06-11，时区：Asia/Shanghai

## 修改目标

对 `doctor.html` 医生端右侧“AI辅助与安全校验”区域做小范围交互优化：右栏内部滚动、展开面板内部滚动、长文本自动换行，并按风险等级控制折叠状态。

## 修改前问题

- 右侧栏信息较多时阅读压力较大。
- 正常项、候选项、缺失项和 Agent Trace 的展开状态没有按风险区分。
- 折叠后仍可能出现长内容看不全或撑开页面的问题，尤其是病历草稿、草稿保存说明、运行日志命令和 Agent Trace。

## 输入

- 用户要求只做医生端右侧栏小修。
- 现有 `doctor.js` 右栏 Tab 渲染逻辑和 `doctor.css` 卡片样式。

## 输出

- 右侧栏内容区明确内部滚动。
- 右侧栏外层容器和内部列表均使用 `max-height: calc(100vh - 260px)`、`overflow-y: auto` 和 `overscroll-behavior: contain`。
- 每个展开面板 body 设置 `max-height: 220px` 并可独立滚动。
- 病历草稿、保存说明、运行日志命令、Agent Trace 和 JSON 类长文本允许换行，不撑爆页面。
- 正常绿色项默认折叠。
- 红色缺失项、黄色候选诊断、错误风险默认展开。
- Agent Trace 默认折叠，仅在 fallback、error、blocked、missing 等风险存在时自动展开。

## 修改文件

- `static/doctor.js`
- `static/doctor.css`
- `static/doctor.html`
- `docs/dev_logs/2026-06-11_doctor_right_sidebar_collapse.md`

## 关键设计决策

- 继续保留已有右栏 Tab，不重构页面。
- 使用原生 `<details>` / `<summary>` 控制折叠，避免引入新依赖。
- 风险判断只在前端基于已有 `appState` 数据完成，不改变后端接口。
- 将“草稿保存说明”和“演示运行日志”也改为折叠面板，避免它们长期占用右栏空间。

## 验证步骤

1. 运行 `node --check static\doctor.js`。
2. 运行 `git diff --check -- static\doctor.js static\doctor.css static\doctor.html docs\dev_logs\2026-06-11_doctor_right_sidebar_collapse.md`。
3. 打开 `/static/doctor.html`，检查右栏整体滚动、面板内部滚动和长文本换行。

## 验证结果

- `node --check static\doctor.js`：通过。
- `git diff --check -- static\doctor.js static\doctor.css static\doctor.html docs\dev_logs\2026-06-11_doctor_right_sidebar_collapse.md`：通过。
- 浏览器烟测 `/static/doctor.html`：右侧栏外层 `max-height=460px`、`overflow-y=auto`、`overscroll-behavior=contain`；展开面板 body `max-height=220px`、`overflow-y=auto`；长文本换行生效；页面无横向溢出；Agent Trace 默认折叠。

## 未解决问题

- 未做新的真实音频上传演示。

## 下一步计划

- 使用 `fever_01.wav + FunASR` 演示时观察右栏展开状态是否符合现场讲解节奏。
