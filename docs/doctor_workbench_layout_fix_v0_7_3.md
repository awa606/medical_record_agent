# v0.7.3 医生端布局遮挡与重叠修复验收记录

## 本次完成

- 修复右上角 `输入方式` 下拉菜单被顶部栏裁剪的问题。
- 修复右侧 `AI辅助与安全校验` 内容区与 `操作区` 视觉重叠的问题。
- 将右侧栏稳定为三段式布局：
  - 标题区
  - 可滚动 AI 内容区
  - 固定操作区
- 保留原有前端按钮 ID、事件绑定、后端 API 和导出流程。

## 前端展示调整

- `输入方式` 菜单展开后完整显示 `录音生成 / 音频生成 / 文本生成`。
- 右侧 AI 内容区单独滚动，操作区固定在右侧栏底部。
- AI 内容区和操作区之间保留 8px 间距。
- 1280 宽度下无横向溢出。

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
2. 点击右上角 `输入方式`，确认下拉菜单未被裁剪。
3. 选择 `文本生成`，生成一条病历。
4. 检查右侧 AI 卡片可滚动查看，且不覆盖操作区。
5. 保存草稿并确认字段，检查 `确认导出` 从禁用变为可用。

## 截图证据

- `docs/final_report/images/v0_7_3_layout_fix/01_input_menu_visible.png`
- `docs/final_report/images/v0_7_3_layout_fix/02_assist_operation_no_overlap.png`
- `docs/final_report/images/v0_7_3_layout_fix/03_operation_export_ready.png`

## 验收结果

- 菜单 `topbar overflow` 为 `visible`，下拉菜单未被裁剪。
- 右侧栏 `AI 内容区` 和 `操作区` 不重叠，实际间距为 8px。
- `#assistPanels` 单独滚动，`.assist-column` 外层不滚动。
- 确认字段后 `确认导出` 按钮可用。
- 未修改后端 API、ASRResult、SSE 协议、医生审核和导出接口。
