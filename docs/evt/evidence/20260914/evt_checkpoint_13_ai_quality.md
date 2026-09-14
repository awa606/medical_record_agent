# EVT考核点一：13项测试真实基线

- 生成时间：2026-09-14T13:27:24+08:00
- Git：`codex/evt-ai-quality-integration@a48aeff5ff8a65559c911d604f2ec57d90bad7e3`
- Python：`3.11.6`
- 数据：`.artifacts\evt\20260914\clinical_e2e_60.json`（SHA256 `5cd18dea53eb77eb98977ec1b9e1c2b3b8913bb702a9fb2dece0fe13a06714c6`）
- 边界：这是开发机检查点证据；`PARTIAL` 不等于 EVT PASS，`HARDWARE BLOCKED` 不等于失败。

| ID | 测试项 | 一票否决 | 当前结果 | 实测事实 | 尚未证明 |
|---|---|---:|---|---|---|
| T01 | 病历生成完整性 | 否 | **PARTIAL** | `{"sample_count":20,"required_field_schema_complete":20,"required_field_schema_rate":1.0,"missing_fields":{},"unsupported_content_count":0,"forbidden_candidate_count":0,"confirmed_diagnosis_phrase_count":0,"provider_mode":"demo_mock_default","audio_pipeline_evaluated":false,"semantic_lora_schema_complete_rate":1.0}` | 结构Schema已验证；LoRA仅为候选实验，仍需真实ASR与被安全门禁接受的本地LLM生成20例。 |
| T02 | AI幻觉检测 | 是 | **PARTIAL** | `{"unsupported_content_count":0,"forbidden_candidate_count":0,"confirmed_diagnosis_phrase_count":0,"provider_mode":"demo_mock_default","rejected_lora_unsupported_fact_count":16}` | 确定性基线无无依据内容；LoRA候选仍产生无依据事实，已拒绝接入，真实本地模型尚未通过。 |
| T03 | 医学术语规范 | 否 | **NOT TESTED** | `{}` | 尚未冻结20个术语样本和人工真值。 |
| T04 | 编辑与人工确认 | 否 | **PARTIAL** | `{"workflow_gate":"PASS"}` | 自动化接口/事务门禁已通过；仍需10种浏览器场景逐项留证。 |
| T05 | 脱敏与合规 | 是 | **NOT TESTED** | `{}` | 尚未建立带人工真值的脱敏样本和外发检查。 |
| T06 | 操作留痕 | 否 | **PARTIAL** | `{"workflow_gate":"PASS"}` | 审计链路测试通过；尚未形成10种操作的课程证据清单。 |
| T07 | 生成时延 | 否 | **BLOCKED** | `{"real_asr_runtime_available":false}` | 真实ASR/LLM运行时未冻结，无法测P95。 |
| T08 | 双环境一致性 | 否 | **HARDWARE BLOCKED** | `{"development_device":{"available":true,"device_count":1,"devices":["NVIDIA GeForce RTX 5070 Laptop GPU"]},"jetson_available":false}` | Jetson未到货，当前只有开发机证据。 |
| T09 | ASR质量 | 否 | **FAIL** | `{"audio_minutes":15.3,"engines":[{"engine":"funasr-paraformer-zh","macro_cer":0.195247,"macro_keyword_recall":0.766667,"max_rtf":0.195058,"gate":"FAIL"},{"engine":"sensevoice-small","macro_cer":0.166945,"macro_keyword_recall":0.733333,"max_rtf":0.161033,"gate":"FAIL"},{"engine":"qwen3-asr-0.6b","macro_cer":0.550381,"macro_keyword_recall":0.588889,"max_rtf":0.55412,"gate":"FAIL"}]}` | 三模型均满足RTF≤1，但尚无模型同时达到CER和关键词召回阈值；训练数据也不足60分钟。 |
| T10 | 角色判断 | 否 | **PARTIAL** | `{"role_gate":"PASS"}` | 策略与低置信度门禁测试通过；仍需真实音频人工标注集计算准确率。 |
| T11 | 知识检索 | 否 | **PARTIAL** | `{"query_count":20,"recall_at_5":0.95,"citation_completeness":1.0,"source_less_citation_count":0,"retrieval_modes":["hybrid_v1"]}` | 20条开发查询已跑通；最终仍需120条复核查询及40条冻结测试集的片段级标签。 |
| T12 | 离线E2E | 否 | **BLOCKED** | `{"real_asr_runtime_available":false}` | 真实ASR和真实本地LLM未就绪。 |
| T13 | 异常恢复 | 否 | **PARTIAL** | `{"recovery":"PASS"}` | 自动化恢复测试通过；仍需按课程10场景进行真实运行和留证。 |

## 工程检查

| 检查组 | 结果 | 耗时(s) | 命令 |
|---|---|---:|---|
| workflow_gate | PASS | 39.834 | `C:\Program Files\Python311\python.exe -m pytest -q tests/test_encounter_workflow.py tests/test_tasks_api.py tests/test_review_revision_transaction.py tests/test_local_patient_encounter_doctor_isolation.py` |
| role_gate | PASS | 7.549 | `C:\Program Files\Python311\python.exe -m pytest -q tests/test_speaker_role_provider_policy.py tests/test_speaker_role_quality_policy.py tests/test_audio_api.py` |
| recovery | PASS | 9.236 | `C:\Program Files\Python311\python.exe -m pytest -q tests/test_task_persistence_after_restart.py tests/test_runtime_hardening.py tests/test_funasr_reliability.py` |
| knowledge_demo | PASS | 9.013 | `C:\Program Files\Python311\python.exe -m pytest -q tests/test_demo_knowledge_api.py tests/test_fever_respiratory_pack.py` |

## 当前考核判断

- PASS：0；PARTIAL：7；NOT TESTED：2；BLOCKED：2；HARDWARE BLOCKED：1；FAIL：1。
- 一票否决项尚无最终PASS，因此本次检查点不能宣称产品通过。
- 下一验证：扩展至120条知识查询冻结集，并针对课程音频进行规范化、分段、热词和模型误差改进。
