# 运行日志目录

本目录用于保存课程演示或关键验收时生成的运行日志。

运行日志由脚本生成：

```powershell
python scripts/save_run_log.py --task-id 19 --audio-id xxx --title fever_01_demo
```

医生端 `/static/doctor.html` 和调试台 `/static/debug.html` 会显示当前 `task_id`、`audio_id`，并提供“复制运行日志命令”按钮。完成 `fever_01.wav + FunASR` 演示后，可直接复制页面中的命令生成本次运行日志。

默认输出格式：

```text
docs/dev_logs/runs/YYYY-MM-DD_fever_01_demo.md
```

日志会汇总：

- 运行时间
- 输入音频
- ASR engine
- ASRResult 摘要
- CER / keyword_recall
- role_strategy / warnings
- LLM provider / model / latency / fallback
- 任务状态
- 步骤日志摘要
- 病历草稿摘要
- 安全校验摘要

## 草稿与输出查看位置

- 医生端左侧字段卡片：查看当前病历字段草稿。
- 调试台 Task JSON / `result_json`：查看 SQLite 中当前任务保存的字段、草稿和安全校验结果。
- `docs/dev_logs/runs/`：查看按需生成并提交的课程演示运行日志。
- `data/outputs/`：仅在点击“确认导出”后生成导出文件。

“保存草稿到SQLite”只保存当前任务审核结果和字段，不生成 Markdown/JSON 导出文件；ASRResult 在转写完成时保存在 `data/uploads/{audio_id}.transcript.json`，Agent Trace 由 `/api/tasks/{task_id}/trace` 动态组装。

提交规则：

- 课程汇报需要留存的具体运行日志可以按需提交。
- 含真实患者数据、真实 API Key、个人身份信息或大体积音视频的日志不得提交。
- 本地调试临时日志可以保留在本目录但不提交。
