# 2026-10-19 已审核病历导出格式修复

## 结论

已修复 DOCX 直接展示 Markdown 标记、重复插入 AI 提示，以及审核后的字段仍显示通用待办的问题。修改仅涉及导出呈现及定向回归，未改变模型、数据库、审核、Revision 或脱敏门禁。本文不代表该代码已经部署，也不代表模型质量或 WBS 5.1 通过。

## 复现与原因

- 原实现先生成 Markdown，再将每一行原样放入 Word，因此 `#`、`##`、`>` 被当作正文；DOCX 还额外插入一次与 Markdown 相同的提示。
- 字段说明只读 `status`，没有区分医生确认内容、确认未询问与接受本次缺失，导致审核后仍出现“部分完成，仍需补充：待医生补充”。
- 导出 API 已有当前审批及 Revision 检查，结果中存在真实 `approved` 和字段审核状态，无需增加接口字段或推断批准。

在修改生产代码前增加 6 项回归，旧版结果为 **5 项失败、1 项通过**。失败分别覆盖原生标题、通用待办残留、具体缺项呈现、缺失审核状态，以及未审核状态与患者原始符号保留。

## 修复范围

- Markdown 和 DOCX 从同一份带段落类型的内容生成。DOCX 使用居中标题、加粗章节标题、中文字体及正常正文，不把结构标记写入 Word。
- AI 提示保留一次，审核状态使用已有的批准标记；候选诊断仍是候选，不改成确诊。
- 医生已确认的内容显示“内容已核对”。仅移除通用的“待医生补充／待补充信息”待办，具体缺项仍显示“记录仍缺：……”。
- 未询问和接受缺失分别显示，后者明确不代表否认或正常。不修改字段值、缺项或历史审核数据。
- 患者正文中原本存在的 `#`、`##`、`>`、`&`、`<` 等字符照常保留，不进行全局删除。

## 验证

```powershell
python -m pytest tests/test_exporter_review_format.py tests/test_tasks_api.py tests/test_task_persistence_after_restart.py tests/test_local_closed_loop_safety.py -q
python -m compileall -q app/services/exporter.py tests/test_exporter_review_format.py
git diff --check
```

结果：**85 passed**；编译与差异检查通过。现有测试覆盖未批准导出、任务权限、审批后修改、版本持久化及脱敏。唯一警告为现有 FastAPI TestClient 的依赖弃用提示。

匿名发热样例通过 `python-docx` 重新读取，并由本机 Microsoft Word 实际打开、导出 PDF。逐页检查共 1 页：标题居中、章节加粗、无 Markdown 结构标记、无重复通知，真实具体缺项仍可见。Python COM 环境缺少 `pywintypes`，改用系统 PowerShell COM 完成 Word 渲染；未修改 Python 环境或生产依赖。

本地附件（不纳入 Git）：

- `.artifacts/export-review-20261019/task_19019_medical_record.docx`
- `.artifacts/export-review-20261019/task_19019_medical_record.md`
- `.artifacts/export-review-20261019/reviewed_record_sample.pdf`
- `.artifacts/export-review-20261019/page-1.png`

## 边界与下一步

这次修复改善已审核病历的输出表达，不解决本地模型漏提、错引或主体混淆。具体缺项仍需医生处理；运行候选需在合并后的精确 SHA 上重新导出核验。最终部署、完整回归、项目同步由主任务统一完成。
