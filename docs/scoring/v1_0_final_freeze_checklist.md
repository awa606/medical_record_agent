# v1.0 终答辩冻结清单

冻结日期：2026-07-11  
冻结范围：报告、PPT/讲稿、runbook、验收文档、表单、证据矩阵、版本记录、RTTM 评测证据。  

## 可提交文件

- `README.md`
- `docs/版本演进记录.md`
- `docs/四周迭代执行计划.md`
- `docs/能力证据追踪矩阵.md`
- `docs/asr_streaming_player_diarization_v0_8_5.md`
- `docs/doctor_workbench_acceptance_v1_0.md`
- `docs/final_report/AI生成式电子病历辅助系统_期末报告_正式版.md`
- `docs/final_report/AI生成式电子病历辅助系统_期末报告_正式版.docx`
- `docs/final_report/images/v1_0_frontend_acceptance/`
- `docs/scoring/v1_0_final_defense_ppt_outline.md`
- `docs/scoring/v1_0_final_defense_talk_track.md`
- `docs/scoring/v1_0_final_demo_runbook.md`
- `docs/scoring/v1_0_final_freeze_checklist.md`
- `data/asr_eval/diarization_ground_truth/fever_01.rttm`
- `data/asr_eval/diarization_ground_truth/chest_pain_01.rttm`
- `data/asr_eval/reports/v0_8_8_diarization/diarization_summary.md`
- `data/asr_eval/reports/v0_8_8_diarization/diarization_summary.json`
- `homework/` 与 `report/appendix_form_templates/` 下由脚本生成的课程表单。

## 不可提交文件

- 真实患者病历、真实患者音频、真实身份证明材料。
- API Key、Token、`.env` 私密配置。
- 模型权重、模型缓存、`data/asr_model_cache/`。
- Docker 运行时缓存、`data/docker_runtime/`。
- `.venv/`、`.venv-asr/`、`__pycache__/`。
- 原始课程手册大文件或未脱敏外部资料。
- 未经确认的大体积新增音频、视频录屏和临时调试文件。

## 验证命令

```powershell
py -3.11 -m pytest -q tests/test_diarization_evaluator.py tests/test_summarize_diarization_results.py tests/test_speaker_profiles.py tests/test_speaker_role_classifier.py tests/test_asr_sessions_api.py tests/test_funasr_streaming_engine.py tests/test_records_api.py tests/test_speaker_diarization.py
node --check static/doctor.js
py -3.11 -m py_compile scripts/evaluate_diarization.py scripts/check_diarization_dependencies.py scripts/summarize_diarization_results.py scripts/update_homework_forms.py
docker compose up -d --build medical-record-agent
Invoke-RestMethod http://127.0.0.1:2601/health
.\.venv\Scripts\python.exe scripts\update_homework_forms.py
.\.venv\Scripts\python.exe scripts\export_final_report_docx.py
git status --short
```

## 已知边界

- 本轮只发布两说话人 diarization 评测：`fever_01`、`chest_pain_01`。
- 三说话人样本为 `pending_sample`，不得展示或填写伪三说话人成绩。
- `snakebite_01` 是单人朗读样本，只能用于 ASR/前端流程复测。
- DER/JER 因本机缺少 `pyannote.metrics` 记录为 `not_available`，不得留空或编造。
- `pyannote`、`3D-Speaker` 当前为 `skipped`，原因是依赖/运行区未配置。
- FunASR 首次冷启动可能触发模型下载和长时间等待，答辩前必须预热。
- AI 只生成病历草稿、候选诊断和安全提醒，导出前必须由医生确认。

## 演示顺序

1. 打开 2601 医生端，展示首页、三栏工作台和医生审核边界。
2. 走文本生成主链路，展示病历字段、候选诊断、证据和安全校验。
3. 切换 Mock ASR，展示 SSE 分段追加和说话人/角色校正抽屉。
4. 展示已预热 FunASR 短音频 session，说明播放器、Range、CAM++ 校准和单说话人边界。
5. 展示两说话人 RTTM 评测汇总，只引用 `fever_01` 与 `chest_pain_01`。
6. 展示冻结清单、能力证据矩阵、版本记录和课程表单。
