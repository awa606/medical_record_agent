# v0.2 SSE Streaming

## 目标

建立任务状态流式输出能力，让前端可追踪 Agent 执行阶段、步骤和错误状态。

`v0.2.1` 在此基础上新增 ASR 会话级文件流：MP3/WAV 上传后，前端通过 SSE 接收 `segment` 事件并在中间转写栏实时追加。

GitHub Issue：[#2](https://github.com/awa606/medical_record_agent/issues/2)

## 验收证据

- API：`GET /api/tasks/{task_id}/events`
- API：`GET /api/tasks/{task_id}/steps`
- API：`POST /api/asr/sessions`
- API：`POST /api/asr/sessions/{session_id}/audio`
- API：`GET /api/asr/sessions/{session_id}/events`
- API：`GET /api/asr/sessions/{session_id}/result`
- 前端：`static/doctor.html`、`static/debug.html`
- 测试：`tests/test_tasks_api.py`、`tests/test_asr_sessions_api.py`
- 文档：`docs/asr_sse_file_stream.md`

## 状态

已具备任务状态、步骤记录、ASR 文件流分段转写和 SSE 调试入口。
