# v0.4 Medical Reasoning

## 目标

将医学对话结构化为病历字段、草稿、安全校验和候选诊断，保留医生最终审核边界。

GitHub Issue：[#4](https://github.com/awa606/medical_record_agent/issues/4)

## 验收证据

- Agent：`app/agents/medical_record_orchestrator.py`
- 服务：`app/services/mock_llm.py`
- Prompt：`app/prompts/`
- 测试：`tests/test_orchestrator.py`、`tests/test_mock_llm_fever.py`

## 状态

已具备字段抽取、草稿生成、安全校验、候选诊断和医生审核流程。
