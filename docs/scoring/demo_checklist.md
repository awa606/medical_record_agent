# 演示验收清单

本文档用于汇报前自检，确保现场演示材料、代码、样例和安全边界准备完整。

## 环境检查

- [ ] 已进入项目目录 `medical_record_agent`。
- [ ] 已安装基础依赖：`pip install -r requirements.txt`。
- [ ] 如需 FunASR，已安装：`pip install -r requirements-asr.txt`。
- [ ] 已运行：`python scripts/check_funasr_env.py`。
- [ ] 已启动服务：`python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`。
- [ ] 可打开 `/health`。

## 页面检查

- [ ] `/static/index.html` 可进入医生端和调试台。
- [ ] `/static/doctor.html` 显示三栏医生工作台。
- [ ] `/static/debug.html` 保留 JSON 调试能力。
- [ ] 医生端主页面不直接展示大段 JSON。
- [ ] 医生端显示当前 `task_id`、`audio_id` 和运行日志命令。
- [ ] 右栏可切换“AI辅助 / 证据与评测 / Agent Trace / 安全校验”分区。

## 文本链路检查

- [ ] 点击“文本导入”。
- [ ] 粘贴 fever clean 问诊文本。
- [ ] 能生成病历字段。
- [ ] 能看到候选诊断。
- [ ] 能看到安全校验。
- [ ] 能看到 Agent 决策轨迹，且导出决策为 `export_allowed=false`、`reason=doctor_review_required`。
- [ ] 能看到 LLM Provider / model / fallback 状态；默认应为 `mock`，真实 LLM 卡住时应自动 fallback。
- [ ] 能说明“保存草稿到SQLite”保存当前字段到 Task `result_json`，不生成导出文件。
- [ ] 任务状态进入 `WAITING_DOCTOR_REVIEW`。

## 音频链路检查

- [ ] 点击“上传转写”或“上传生成病历”。
- [ ] 上传 `fever_01.wav`。
- [ ] ASR 引擎默认选择 FunASR。
- [ ] 能生成 `ASRResult.text` 和 `conversation_text`。
- [ ] 能从音频生成病历。
- [ ] 如出现 `single_segment_needs_review`，右栏显示医生/患者角色需人工校正。

## ASR 评测检查

- [ ] 打开 ASR 评测抽屉。
- [ ] 输入人工标注文本。
- [ ] 输入关键词。
- [ ] 能看到 CER。
- [ ] 能看到 keyword_recall。
- [ ] 能看到 recognized 和 missing。

## 调试与审计检查

- [ ] 调试台能展示 ASRResult JSON。
- [ ] 调试台能展示 Agent Trace JSON。
- [ ] 调试台能展示 Task JSON。
- [ ] 调试台能展示 Steps JSON。
- [ ] 调试台能展示 Safety JSON。
- [ ] 调试台能展示运行日志命令和草稿保存说明。
- [ ] 能说明 `agent_task`、`agent_task_step`、`audit_log` 的用途。

## 运行日志检查

- [ ] 已记录本次演示的 `task_id`。
- [ ] 已记录本次演示的 `audio_id`。
- [ ] 已通过医生端或调试台复制运行日志命令。
- [ ] 可运行：

```powershell
python scripts/save_run_log.py --task-id 19 --audio-id xxx --title fever_01_demo
```

- [ ] 已生成 `docs/dev_logs/runs/YYYY-MM-DD_fever_01_demo.md`。

## 评分材料检查

- [ ] `docs/scoring/项目进度与评分证据看板.md`
- [ ] `docs/scoring/course_scoring_plan.md`
- [ ] `docs/scoring/agent_design.md`
- [ ] `docs/scoring/agent_architecture_diagram.md`
- [ ] `docs/scoring/prompt_chain_design.md`
- [ ] `docs/scoring/decision_system.md`
- [ ] `docs/scoring/ethics_compliance.md`
- [ ] `docs/scoring/demo_script.md`
- [ ] `docs/scoring/code_walkthrough.md`
- [ ] `docs/scoring/demo_checklist.md`

## 安全边界检查

- [ ] 不展示真实患者数据。
- [ ] 不提交真实 API Key。
- [ ] 不上传 `data/uploads/` 中的本地音频。
- [ ] 不上传 `data/medical_record_agent.sqlite3`。
- [ ] 不上传 `.venv/`、模型权重、模型缓存或大体积视频。
- [ ] 汇报中明确说明 AI 只生成草稿，最终由医生确认。

## 相关文档

- 项目进度看板：`docs/scoring/项目进度与评分证据看板.md`
- 评分总表：`docs/scoring/course_scoring_plan.md`
- 现场演示讲稿：`docs/scoring/demo_script.md`
- 代码展示路线：`docs/scoring/code_walkthrough.md`
- Agent 设计：`docs/scoring/agent_design.md`
- 决策系统：`docs/scoring/decision_system.md`
- Prompt 链：`docs/scoring/prompt_chain_design.md`
- 伦理合规：`docs/scoring/ethics_compliance.md`
