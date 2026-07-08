# 医生端可交付验收清单

本文用于验收 `v0.6.3` 到 `v0.6.4` 医生端闭环：输入、转写、角色校正、病历生成、医生审核和导出。

## 验收环境

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

访问：

```text
http://127.0.0.1:8001/static/doctor.html
```

## 验收场景

| 场景 | 操作 | 预期结果 | 结果 | 问题记录 | 截图位置 |
| --- | --- | --- | --- | --- | --- |
| 文本导入生成病历 | 点击“文本导入”，使用默认问诊文本生成病历 | 字段区、候选诊断、安全校验正常显示，下一步提示进入医生审核 | 通过 | 导出按钮在确认前保持禁用 | `docs/final_report/images/v0_6_4_acceptance/02_text_record_generated.png` |
| 短音频 Mock ASR | 通过 ASR session API 上传短 WAV，选择 `mock` | 中间栏出现 SSE 分段、角色标签、校正入口和“用校正文本生成病历”按钮 | 接口通过，前端文件选择需人工复测 | 浏览器自动化无法稳定驱动本地文件选择器，本轮用接口证据替代 | `docs/final_report/images/v0_6_4_acceptance/03_mock_asr_segments.png` |
| 中文短音频真实 ASR | 上传中文问诊音频，选择 `SenseVoice` 或 `FunASR` | 转写完成后可进入角色校正；失败时显示可理解错误 | 环境阻塞 | 当前 8001 服务运行在 Anaconda 环境，缺少 `funasr` 依赖；需用 `.venv-asr` 或 Docker ASR 环境复测 | `logs/debug/2026-07-08_v0_6_4_frontend_acceptance.md` |
| 角色校正 | 修改任一分段角色或文本，保存校正结果 | 状态变为已校正，后续病历生成使用校正文本 | 接口通过，前端文件选择需人工复测 | PATCH 结果显示 `reviewed_by_doctor=true`、`role_strategy=manual_reviewed` | `docs/final_report/images/v0_6_4_acceptance/04_role_correction_saved.png` |
| 16 分钟长音频 | 使用 16 分钟稳定性样本，选择 `SenseVoice` 或 `FunASR` | 中间栏显示切片进度，最终完成或给出明确失败原因 | 报告证据通过，前端需人工复测 | v0.5.9 切片评测已通过；本轮 8001 环境缺真实 ASR 依赖 | `docs/final_report/images/v0_6_4_acceptance/07_long_audio_chunking.png` |
| 30 分钟长音频 | 使用 30 分钟稳定性样本，选择 `SenseVoice` 或 `FunASR` | 中间栏显示当前切片、总切片、失败原因和重试提示 | 报告证据通过，前端需人工复测 | v0.5.9 报告显示 SenseVoice/FunASR 5 分钟切片均完成，Qwen3 不作为默认路线 | `docs/final_report/images/v0_6_4_acceptance/07_long_audio_chunking.png` |
| 未审核导出阻断 | 生成病历后不确认字段，检查导出状态 | 导出按钮不可用或被后端阻断 | 通过 | 修复 `setBusy(false)` 后导出按钮不会在未确认状态被重新启用 | `docs/final_report/images/v0_6_4_acceptance/02_text_record_generated.png` |
| 审核后导出 | 点击“保存草稿”“确认字段”“确认导出” | 生成 Markdown/Word 导出文件 | 通过 | 导出后下一步面板显示“导出已完成” | `docs/final_report/images/v0_6_4_acceptance/06_export_success.png` |

完整 `v0.6.4` 验收记录见：`docs/doctor_workbench_acceptance_v0_6_4.md`。

## v0.6.3 前端展示验收点

- 顶部流程条固定为 6 步：输入、实时转写、角色校正、生成病历、医生审核、导出。
- `下一步` 面板始终显示当前动作，例如上传音频、保存角色校正、生成病历、确认字段、确认导出。
- 转写区显示进度、分段、切片、文件名和角色校正状态。
- 失败时显示失败原因和重试建议，不要求医生打开调试页才能理解问题。
- 导出前必须经过医生确认，不能自动导出。

## 记录规则

- 每次验收后，把实际结果写入本表。
- 发现问题时，在 `logs/debug/` 新建 Debug Log。
- 每次前端改动后，至少执行：

```powershell
node --check static\doctor.js
$env:PYTHONPATH=(Get-Location).Path
pytest -q tests\test_asr_sessions_api.py tests\test_tasks_api.py tests\test_records_api.py
git diff --check
```
