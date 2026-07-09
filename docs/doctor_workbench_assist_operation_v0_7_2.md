# v0.7.2 医生端 AI 辅助区与操作区重排验收记录

## 本次完成

- 将医生模式右侧 `AI辅助与安全校验` 从 tab 展示改为固定四块卡片：
  - 候选诊断
  - 治疗方案推荐
  - 判断证据
  - 安全校验结果
- 将原底部 `当前任务` 操作条移入右侧栏，改为 `操作区`。
- 操作区保留原有按钮和接口行为：
  - 重新生成
  - 保存草稿
  - 确认字段
  - 确认导出
- 保留 Debug 模式下的 Agent Trace、ASR 评测、运行日志等调试信息。
- 同步收束上一轮未提交的医生端控件调整：顶部 ASR Engine 下拉选择、`输入方式` 菜单和录音生成预留提示。

## 前端展示调整

- 右栏更接近参考图中的“AI辅助与安全校验 + 操作区”结构。
- 候选诊断只作为候选信息展示，继续标注 `待医生确认`。
- 治疗方案推荐只展示建议检查、用药提示和处理建议，不自动处方。
- 判断证据展示诊断触发原因和来源转写片段。
- 安全校验结果展示字段缺失、风险提示和导出阻断状态。
- 页面底部不再出现横向 `当前任务` 操作条，减少底部留白。

## 怎么测试

```powershell
docker compose up -d --build
curl http://127.0.0.1:2601/health
curl -I http://127.0.0.1:2601/static/doctor.html
node --check static\doctor.js
$env:PYTHONPATH=(Get-Location).Path
pytest -q tests\test_asr_sessions_api.py tests\test_tasks_api.py tests\test_records_api.py
pytest -q
git diff --check
```

前端手工验收：

1. 打开 `http://127.0.0.1:2601/static/doctor.html`。
2. 点击 `输入方式`，选择 `文本生成`。
3. 粘贴或使用蛇咬伤问诊样例生成病历。
4. 检查右侧是否出现 `候选诊断`、`治疗方案推荐`、`判断证据`、`安全校验结果` 四块。
5. 未确认字段前，`确认导出` 应为禁用状态。
6. 点击 `保存草稿`、`确认字段` 后，`确认导出` 应变为可用。
7. 点击 `确认导出`，确认导出流程仍正常。

## 截图证据

- `docs/final_report/images/v0_7_2_assist_operation/01_initial_assist_operation.png`
- `docs/final_report/images/v0_7_2_assist_operation/02_text_generated_assist_cards.png`
- `docs/final_report/images/v0_7_2_assist_operation/03_operation_export_ready.png`
- `docs/final_report/images/v0_7_2_assist_operation/04_exported_operation_panel.png`
- `docs/final_report/images/v0_7_2_assist_operation/05_assist_cards_scrolled.png`

## 验收结果

- Docker `2601` 页面可访问。
- 文本生成后右侧四块卡片均已渲染。
- 操作区已进入右侧栏，页面底部不再保留独立操作条。
- 未审核时导出按钮禁用，确认字段后导出按钮可用。
- 导出流程保持可用，生成 Markdown 和 Word 文件。
- 未修改后端 API、ASRResult、SSE 协议、医生审核和导出接口。
