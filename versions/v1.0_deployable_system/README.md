# v1.0 Deployable System

## 目标

形成可部署、可追踪、可交接的医学 AI 工程系统，覆盖本地服务启动、可选本地模型、日志、版本和 PR 工作流。

## 验收证据

- 启动命令：`python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- 工程结构：`docs/`、`logs/`、`versions/`、`.github/`
- 可选本地模型：FunASR、Qwen3-ASR、Ollama LLM provider
- 测试：`pytest -q`

## 状态

进行中。当前重点是补齐工程管理、部署说明和版本追踪证据。
