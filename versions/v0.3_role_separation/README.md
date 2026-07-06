# v0.3 Role Separation

## 目标

区分医生与患者对话角色，提升问诊文本结构化和 ASR 评测可解释性。

GitHub Issue：[#3](https://github.com/awa606/medical_record_agent/issues/3)

## 验收证据

- 服务：`app/services/asr/role_strategy.py`
- Schema：`ASRSegment`
- 测试：`tests/test_asr_role_strategy.py`

## 状态

已具备角色策略、样例配置和人工校正提示能力。
