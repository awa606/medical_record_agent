# 追踪矩阵

本文用于把 Medical Record Agent 的核心能力、GitHub Issue、版本里程碑、代码入口、测试和文档证据对应起来。后续新增功能时必须更新本矩阵或在对应 Issue 中补充链接。

## 核心能力追踪

| 能力 | GitHub Issue | 版本目录 | 代码入口 | 测试证据 | 文档证据 |
| --- | --- | --- | --- | --- | --- |
| speech-to-text (ASR) | [#1](https://github.com/awa606/medical_record_agent/issues/1) | `versions/v0.1_basic_asr_pipeline/` | `app/api/audio.py`、`app/services/asr/` | `tests/test_asr_mock.py`、`tests/test_audio_api.py`、`tests/test_asr_factory.py` | `docs/asr_v0_3.md`、`docs/architecture.md` |
| real-time streaming (SSE) | [#2](https://github.com/awa606/medical_record_agent/issues/2) | `versions/v0.2_sse_streaming/` | `app/api/tasks.py`、`static/doctor.js`、`static/main.js` | `tests/test_tasks_api.py` | `docs/flow_v0_2.md`、`docs/architecture.md` |
| ASR session SSE file streaming | [#2](https://github.com/awa606/medical_record_agent/issues/2) | `versions/v0.2_sse_streaming/` | `app/api/asr_sessions.py`、`static/doctor.js` | `tests/test_asr_sessions_api.py` | `docs/asr_sse_file_stream.md`、`docs/four_week_iteration_plan.md` |
| role separation and correction (doctor/patient) | [#3](https://github.com/awa606/medical_record_agent/issues/3) | `versions/v0.3_role_separation/` | `app/services/asr/role_strategy.py`、`app/api/asr_sessions.py`、`static/doctor.js` | `tests/test_asr_role_strategy.py`、`tests/test_asr_sessions_api.py` | `docs/asr_role_correction.md`、`docs/asr_model_route.md`、`versions/v0.3_role_separation/README.md` |
| medical dialogue structuring | [#4](https://github.com/awa606/medical_record_agent/issues/4) | `versions/v0.4_medical_reasoning/` | `app/agents/medical_record_orchestrator.py`、`app/schemas/medical_record.py` | `tests/test_orchestrator.py`、`tests/test_records_api.py` | `docs/architecture.md`、`docs/scoring/agent_design.md` |
| medical knowledge reasoning | [#4](https://github.com/awa606/medical_record_agent/issues/4) | `versions/v0.4_medical_reasoning/` | `app/services/mock_llm.py`、`app/prompts/` | `tests/test_mock_llm_fever.py`、`tests/test_prompts_and_mock_llm.py` | `docs/scoring/decision_system.md`、`docs/scoring/prompt_chain_design.md` |
| local model deployment | [#5](https://github.com/awa606/medical_record_agent/issues/5) | `versions/v1.0_deployable_system/` | `requirements-asr.txt`、`requirements-qwen3-asr.txt`、`app/services/llm/ollama_provider.py` | `tests/test_check_funasr_env.py`、`tests/test_llm_adapter.py` | `docs/online_asr.md`、`docs/qwen3_asr.md`、`docs/online_llm.md` |

## 工程治理追踪

| 规则 | 证据 |
| --- | --- |
| `/docs` 是文档层 | `docs/architecture.md`、`docs/engineering_rules.md`、`docs/version_log.md` |
| `/logs` 是调试和每日追踪层 | `logs/template.md`、`logs/daily/2026-07-06.md`、`logs/debug/.gitkeep` |
| `/versions` 是里程碑快照层 | `versions/README.md` 和五个版本目录 |
| `/.github` 是 Issue 和 PR 工作流 | `.github/ISSUE_TEMPLATE/*.md`、`.github/PULL_REQUEST_TEMPLATE.md` |
| Bug 必须有调试日志 | `docs/debug_guide.md`、`logs/template.md` |
| 提交必须遵守约定 | `docs/engineering_rules.md`、`.github/PULL_REQUEST_TEMPLATE.md` |

## 验证命令

```powershell
git diff --check
$env:PYTHONPATH = (Get-Location).Path
pytest -q
```
