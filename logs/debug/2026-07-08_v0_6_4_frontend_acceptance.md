# Debug Log：v0.6.4 医生端前端验收问题记录

## Problem

按医生端验收清单真实打开 `http://127.0.0.1:8001/static/doctor.html` 后，发现三类前端状态问题和一个环境阻塞：

- 未确认字段时，导出按钮曾被 `setBusy(false)` 重新启用，点击后由后端阻断。
- 导出成功后，`下一步` 面板仍显示“字段已确认，可以导出”，不够明确。
- 未选择音频文件直接提交时，页面先重置任务状态，导致旧任务 ID 和状态残留。
- 当前 8001 服务运行环境缺少 `funasr` 依赖，真实 `SenseVoice/FunASR` 前端上传验收阻塞。

## Steps to reproduce

1. 打开医生端页面。
2. 使用文本导入生成病历。
3. 在未确认字段前检查导出按钮状态。
4. 保存草稿、确认字段、导出。
5. 点击上传音频但不选择文件，直接提交。
6. 使用当前 8001 环境尝试 `SenseVoice/FunASR` 真实 ASR。

## Expected vs actual

- 预期：未确认字段前导出按钮不可用；实际：修复前按钮可能被忙碌状态恢复逻辑启用。
- 预期：导出后下一步面板显示导出完成；实际：修复前仍提示可导出。
- 预期：空音频提交只提示“请选择音频文件”；实际：修复前先重置流程，页面出现旧任务残留状态。
- 预期：真实 ASR 可以完成或显示明确依赖错误；实际：当前环境返回缺少 `funasr` 依赖，属于环境阻塞。

## Root cause

- `setBusy(false)` 对所有按钮做统一启用，没有在忙碌结束后重新应用业务规则。
- `nextActionState()` 先判断 `isApprovedForExport()`，导致 `EXPORTED` 状态被“字段已确认，可以导出”分支覆盖。
- `submitAudio()` 在校验文件前调用 `closeDrawer()` 和 `resetTaskState()`。
- 当前 8001 服务不是 `.venv-asr` / Docker ASR 运行环境，缺少真实 ASR 模型依赖。

## Fix

- `setBusy(false)` 结束时调用 `renderFooter()` 和 `renderNextActionPanel()`，恢复按钮和下一步业务状态。
- 在 `nextActionState()` 中优先处理 `EXPORTED/exported`，显示“导出已完成”。
- `resetTaskState()` 清理旧任务 ID 和任务状态；`submitAudio()` 先校验文件，再关闭抽屉和重置流程。
- 真实 ASR 环境阻塞暂不在本轮代码中修复，记录为后续 `.venv-asr` 或 Docker ASR 环境人工复测项。

## Verification

- 文本导入生成病历后，导出按钮在确认字段前保持禁用。
- 保存草稿、确认字段后，下一步面板显示“字段已确认，可以导出”。
- 导出成功后，下一步面板显示“导出已完成”。
- 空音频提交后，Toast 文本为“请选择音频文件”，页面保持初始下一步状态。
- 截图证据位于 `docs/final_report/images/v0_6_4_acceptance/`。

## Follow-up

- 使用 `.venv-asr` 或 Docker ASR 环境启动服务后，人工选择中文短音频和 16/30 分钟长音频，复测真实前端转写和切片状态。
- 若仍存在真实模型失败，应按模型或切片编号新增独立 Debug Log。
