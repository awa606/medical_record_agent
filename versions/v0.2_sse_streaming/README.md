# v0.2 SSE Streaming

## 目标

建立任务状态流式输出能力，让前端可追踪 Agent 执行阶段、步骤和错误状态。

GitHub Issue：[#2](https://github.com/awa606/medical_record_agent/issues/2)

## 验收证据

- API：`GET /api/tasks/{task_id}/events`
- API：`GET /api/tasks/{task_id}/steps`
- 前端：`static/doctor.html`、`static/debug.html`
- 测试：`tests/test_tasks_api.py`

## 状态

已具备任务状态、步骤记录和 SSE 调试入口。
