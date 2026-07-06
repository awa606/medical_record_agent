# 2026-06-10 Issue #35 LLM 双通道接入与 MockLLM 兜底

## 修改日期 / 时间

2026-06-10，时区：Asia/Shanghai

## 修改目标

完成 GitHub Issue #35：在不破坏 `fever_01.wav` 稳定演示链路的前提下，新增真实 LLM 字段抽取能力，优先支持 OpenAI-compatible online provider，再支持 Ollama provider，并保留 MockLLM 作为默认兜底。

## 修改前问题

- 系统已有 Prompt 契约和 MockLLM，但没有统一 LLM Provider Adapter。
- Agent Trace 已能展示任务、步骤和导出决策，但缺少 LLM provider、model、latency、fallback 状态。
- 运行日志没有记录 LLM 调用和 fallback 摘要。

## 输入

- Issue #35 要求的环境变量：`LLM_PROVIDER`、`ONLINE_LLM_API_BASE`、`ONLINE_LLM_API_KEY`、`ONLINE_LLM_MODEL`、`OLLAMA_BASE_URL`、`OLLAMA_MODEL`、`LLM_TIMEOUT_SECONDS`、`LLM_MAX_RETRIES`。
- 现有 `MockLLM`、`MedicalRecordOrchestrator`、`MedicalRecordFields` schema、`app/prompts/medical_record_prompts.py`。
- 现有 Agent Trace、doctor/debug 前端和运行日志脚本。

## 输出

- 新增 `app/services/llm/` Adapter 目录，包含 mock、online、ollama、factory、json repair 和 record generator。
- Orchestrator 默认使用 `create_llm_record_generator()`，第一阶段只让真实 LLM 做字段抽取。
- 字段抽取失败、超时、JSON 解析失败或字段不完整时 fallback 到 MockLLM。
- Agent Trace 和运行日志记录 LLM provider、model、latency、fallback 和 fallback_reason。
- 医生端 Agent 决策轨迹展示 LLM Provider 和 fallback 状态。

## 修改文件

- `app/services/llm/base.py`
- `app/services/llm/mock_provider.py`
- `app/services/llm/online_provider.py`
- `app/services/llm/ollama_provider.py`
- `app/services/llm/factory.py`
- `app/services/llm/json_repair.py`
- `app/services/llm/llm_record_generator.py`
- `app/services/llm/__init__.py`
- `app/agents/medical_record_orchestrator.py`
- `app/services/__init__.py`
- `app/services/agent_trace.py`
- `app/prompts/medical_record_prompts.py`
- `scripts/save_run_log.py`
- `static/doctor.html`
- `static/doctor.js`
- `static/debug.html`
- `static/main.js`
- `tests/test_llm_adapter.py`
- `tests/test_tasks_api.py`
- `tests/test_save_run_log.py`
- `docs/scoring/prompt_chain_design.md`
- `docs/scoring/course_scoring_plan.md`
- `docs/scoring/decision_system.md`
- `docs/scoring/demo_script.md`
- `docs/scoring/demo_checklist.md`
- `docs/scoring/code_walkthrough.md`
- `docs/scoring/agent_design.md`
- `docs/dev_logs/runs/README.md`
- `docs/dev_logs/2026-06-10_llm_integration.md`

## 关键设计决策

- `mock` 永远是默认 provider 和兜底 provider，确保 `fever_01.wav` 演示稳定。
- 第一阶段真实 LLM 只接字段抽取；草稿生成和安全校验继续使用 MockLLM 稳定逻辑。
- 不新增数据库字段，LLM Trace 写入现有 `result_json.llm_trace`，Agent Trace 动态读取。
- online provider 使用 OpenAI-compatible `/v1/chat/completions`，ollama provider 使用 `/api/chat`，均不新增第三方依赖。
- 不把 API Key 写入代码、日志、README 或测试；错误和 fallback_reason 只记录配置项名称或接口错误摘要。

## 验证步骤

1. 运行 `python -m py_compile app/services/llm/*.py app/agents/medical_record_orchestrator.py scripts/save_run_log.py`。
2. 运行 `node --check static/doctor.js` 和 `node --check static/main.js`。
3. 运行 `python -m pytest tests/test_llm_adapter.py tests/test_tasks_api.py tests/test_save_run_log.py`。
4. 运行 `python -m pytest`。
5. 浏览器打开 `/static/doctor.html`，检查 Agent 决策轨迹中的 LLM Provider 和 fallback 状态。

## 验证结果

- `python -m py_compile app/services/llm/*.py app/agents/medical_record_orchestrator.py scripts/save_run_log.py`：通过。
- `node --check static/doctor.js`、`node --check static/main.js`：通过。
- `python -m pytest tests/test_llm_adapter.py tests/test_tasks_api.py tests/test_save_run_log.py`：13 passed。
- `python -m pytest`：64 passed。
- `git diff --check -- app static scripts tests docs`：通过。
- 浏览器烟测：`/static/doctor.html` 能看到 LLM Provider、LLM Fallback 和 `mock-deterministic-extractor`；`/static/debug.html` 能看到 Agent Trace JSON；控制台无 error。

## 未解决问题

- 本次没有配置或调用真实 online / ollama 模型，测试通过 fake provider 验证 JSON 解析、schema 校验和 fallback。
- 草稿生成和安全校验仍走 MockLLM；后续如需真实 LLM 参与，应继续保留 schema 校验、安全门禁和医生审核边界。

## 下一步

- 汇报前如需展示真实 LLM，可在本地临时设置环境变量运行，不提交 API Key、不上传截图中的敏感信息。
