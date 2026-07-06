# 2026-06-09 自动运行日志脚本

## 修改日期 / 时间

2026-06-09，时区：Asia/Shanghai

## 修改目标

新增 `scripts/save_run_log.py`，根据 `task_id` 和 `audio_id` 自动生成一次演示运行日志，方便课程汇报保存 fever_01 等样例的可追踪证据。

## 修改前问题

- 医生端和调试台可以展示 ASRResult、任务状态和安全校验，但一次演示后的证据需要人工复制整理。
- ASRResult、任务步骤和病历草稿分散在上传目录和 SQLite 任务表中，不利于形成稳定汇报材料。

## 输入

- 用户命令示例：`python scripts/save_run_log.py --task-id 19 --audio-id xxx --title fever_01_demo`
- SQLite 表：`agent_task`、`agent_task_step`
- 上传目录：`data/uploads/{audio_id}.record.json`、`{audio_id}.transcript.json`
- 可选评测结果：`{audio_id}.evaluation.json` 或 `data/asr_eval/*.csv`

## 输出

- 新增自动运行日志脚本。
- 新增 `docs/dev_logs/runs/` 占位目录。
- 新增脚本单元测试。
- 运行日志内容覆盖运行时间、输入音频、ASR engine、ASRResult 摘要、CER、keyword_recall、role_strategy、warnings、任务状态、步骤日志、病历草稿和安全校验。

## 修改文件

- `scripts/save_run_log.py`
- `tests/test_save_run_log.py`
- `docs/dev_logs/runs/.gitkeep`
- `docs/dev_logs/2026-06-09_save_run_log_script.md`
- `README.md`

## 关键设计决策

- 脚本独立运行，不接入 FastAPI 主程序，不改变后端业务逻辑。
- 任务数据从现有 SQLite 读取，音频与转写数据从现有上传目录读取。
- 评测结果当前 API 不持久化，因此脚本采用兼容读取策略；找不到时在日志中写明“未找到”。
- 输出 Markdown 存入 `docs/dev_logs/runs/`，可直接用于课程汇报和 GitHub 证据留存。

## 验证步骤

1. 运行 `python -m py_compile scripts/save_run_log.py`。
2. 运行 `python -m pytest tests/test_save_run_log.py`。
3. 运行 `python -m pytest`。

## 验证结果

- `python -m py_compile scripts/save_run_log.py` 通过。
- `python -m pytest tests/test_save_run_log.py` 通过，结果：1 passed。
- `python -m pytest` 通过，结果：57 passed。

## 未解决问题

- 如果医生端只调用 `/api/audio/{audio_id}/evaluate`，评测结果不会自动保存；后续可在调试流程中另存 evaluation JSON，或继续保持脚本的“未找到”提示。

## 下一步计划

- 汇报时运行脚本生成 fever_01_demo 日志，并将生成的 Markdown 与医生端截图配套展示。
