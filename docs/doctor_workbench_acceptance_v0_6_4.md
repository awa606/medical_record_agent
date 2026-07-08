# v0.6.4 医生端真实前端手工验收记录

本记录对应 `v0.6.4`：真实打开医生端页面，按验收清单跑文本导入、审核、导出、Mock ASR 接口证据、角色校正接口证据和长音频切片报告证据。

## 验收环境

- 日期：2026-07-08
- 服务：`http://127.0.0.1:8001`
- 页面：`http://127.0.0.1:8001/static/doctor.html`
- 说明：`8000` 仍可能是旧 Docker 容器，本轮以 `8001` 最新代码为准。

## 验收结果

| 场景 | 结果 | 证据 | 备注 |
| --- | --- | --- | --- |
| 初始医生端页面 | 通过 | `docs/final_report/images/v0_6_4_acceptance/01_initial_next_action.png` | 流程条和“下一步”面板正常显示。 |
| 文本导入生成病历 | 通过 | `docs/final_report/images/v0_6_4_acceptance/02_text_record_generated.png` | 字段区生成，状态为待医生审核，导出按钮保持禁用。 |
| 短音频 Mock ASR | 接口证据通过 | `docs/final_report/images/v0_6_4_acceptance/03_mock_asr_segments.png` | 浏览器自动化未能稳定驱动系统文件选择器，使用真实 API 上传结果作为证据。 |
| 医生/患者角色校正 | 接口证据通过 | `docs/final_report/images/v0_6_4_acceptance/04_role_correction_saved.png` | 保存后 `reviewed_by_doctor=true`，`role_strategy=manual_reviewed`。 |
| 医生审核就绪 | 通过 | `docs/final_report/images/v0_6_4_acceptance/05_doctor_review_ready.png` | 保存草稿、确认字段后进入可导出状态。 |
| 审核后导出 | 通过 | `docs/final_report/images/v0_6_4_acceptance/06_export_success.png` | 生成 Markdown 和 Word 文件，页面显示“导出已完成”。 |
| 16/30 分钟长音频切片 | 报告证据通过，前端需人工复测 | `docs/final_report/images/v0_6_4_acceptance/07_long_audio_chunking.png` | v0.5.9 已验证切片策略；本轮 8001 环境缺真实 ASR 依赖。 |
| 失败提示 | 通过 | `docs/final_report/images/v0_6_4_acceptance/08_failure_or_retry_hint.png` | 未选择音频文件时 Toast 文本为“请选择音频文件”，页面状态不再被旧任务污染。 |

## 本轮发现并处理的问题

- 未审核状态下，`setBusy(false)` 会把所有按钮重新启用，导致导出按钮前端可点但后端阻断。已修复为恢复业务态渲染。
- 导出完成后，“下一步”面板仍显示“字段已确认，可以导出”。已修复为“导出已完成”。
- 空音频提交前先重置任务状态，导致页面出现旧任务残留状态。已修复为先校验文件，再重置流程。
- 真实 `SenseVoice/FunASR` 前端上传验收在当前 8001 运行环境中阻塞，原因是缺少 `funasr` 依赖；后续应使用 `.venv-asr` 或 Docker ASR 环境复测。

## 前端展示调整

- 导出完成后，`下一步` 面板显示“导出已完成”，并提供“重新导出 / 上传新音频 / 粘贴新文本”。
- 忙碌状态结束后重新渲染底部按钮和下一步面板，避免按钮状态和业务状态不一致。
- 未选择音频文件时不再重置当前任务，页面保留正确初始状态并显示错误提示。

## 怎么在前端测试

1. 打开 `http://127.0.0.1:8001/static/doctor.html`。
2. 点击“粘贴问诊文本”，使用默认文本生成病历。
3. 确认导出按钮在“确认字段”前不可用。
4. 点击“保存草稿”“确认字段”，检查下一步面板显示“字段已确认，可以导出”。
5. 点击“确认导出”，检查页面显示“导出已完成”。
6. 点击“上传新音频”，不选择文件直接提交，检查 Toast 显示“请选择音频文件”。
7. 真实音频和长音频场景需要在 `.venv-asr` 或 Docker ASR 环境启动后人工选择文件复测。

## 验证命令

```powershell
node --check static\doctor.js
$env:PYTHONPATH=(Get-Location).Path
pytest -q tests\test_asr_sessions_api.py tests\test_tasks_api.py tests\test_records_api.py
pytest -q
git diff --check
curl http://127.0.0.1:8001/health
```

## 验证结果

- `node --check static\doctor.js`：通过。
- `pytest -q tests\test_asr_sessions_api.py tests\test_tasks_api.py tests\test_records_api.py`：`15 passed, 1 warning`。
- `pytest -q`：`110 passed, 1 warning`。
- `git diff --check`：通过。
- `curl http://127.0.0.1:8001/health`：返回 `{"status":"ok"}`。
