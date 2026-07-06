# v0.3 Role Separation

## 目标

区分医生与患者对话角色，支持逐段人工校正，提升问诊文本结构化、病历生成和 ASR 评测可解释性。

GitHub Issue：[#3](https://github.com/awa606/medical_record_agent/issues/3)

## 验收证据

- 服务：`app/services/asr/role_strategy.py`
- API：`PATCH /api/asr/sessions/{session_id}/result`
- Schema：`ASRSegment`
- 前端：`static/doctor.html`、`static/doctor.js`
- 测试：`tests/test_asr_role_strategy.py`、`tests/test_asr_sessions_api.py`
- 文档：`docs/asr_role_correction.md`、`docs/asr_model_route.md`

## 状态

已具备角色策略、样例配置、待校正标记、逐段角色/文本校正和校正后病历生成能力。
