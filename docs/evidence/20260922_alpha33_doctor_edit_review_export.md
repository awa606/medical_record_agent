# WBS 3.3 医生修改、审核与导出证据

## 结论

WBS 3.3 的 Alpha 验收项已在匿名合成任务上通过：整页编辑保存后可以重载；未审核导出由 HTTP 400 业务门禁拒绝；重新审核后导出的 DOCX 包含医生修改内容。

该结果证明医生修改、Revision、审核和导出工程闭环，不证明真实医院部署、临床有效性或多角色权限体系完成。

## 环境

- 分支：`codex/alpha33-doctor-edit-review-export`
- 基线：`main@b5cc5369ae9503f28910feca6b1d402add408671`
- 数据：匿名合成发热任务，临时 SQLite 和输出目录。
- Provider：浏览器工作流测试使用确定性测试 Provider；真实本地 Qwen 的字段生成事实沿用已完成的 WBS 3.2 Evidence，本轮不重复声称模型评测。
- 原始数据库、DOCX 和运行日志：本地 `.artifacts/alpha33-e2e/`，不提交 Git。

## 垂直闭环结果

| 检查 | 实测 |
|---|---|
| 整页编辑控件 | 7 个结构化字段 |
| 取消编辑 | 恢复编辑前字段值 |
| 保存前 Revision | 2 |
| 保存后 Revision | 3 |
| 未审核直接导出 | HTTP 400，无文件 |
| 最终任务阶段 | `exported` |
| DOCX 可打开 | PASS |
| 修改后内容 | 包含“医生补充记录” |
| DOCX SHA256 | `d90914efd4c8a6b951606593035f3f06c89140384303689045e7fe971bb7c001` |

## 安全与追踪

- 服务端根据当前 Revision 前后差异标记人工修改；浏览器提交伪造标记会被清除。
- 人工修改保留原始 `source_spans`，并明确说明原始证据仅供对照。
- 字段证据详情显示片段 ID、角色、说话人、时间范围和置信度。
- 字段级“查依据”使用现有知识检索 API，显示发布机构、版本、章节、页码、文档/片段 ID、URL 和内容 SHA256。
- Revision 过期时保存返回 409；页面保留本地修改并要求医生显式加载最新版。
- 任何知识结果都未自动写入患者事实、诊断或处置。

## 验证

- 3.3 定向测试：57 passed。
- 全量回归：534 passed，1 个第三方弃用告警。
- `node --check static/doctor.js`：PASS。
- Python 编译检查：PASS。
- `/health` 与隔离测试服务 `/ready` smoke：PASS。
- `git diff --check`：PASS。
- 浏览器测试覆盖编辑、取消、保存、主动查询、Revision 409、审核、导出和 DOCX 内容。

## 当前运行容器边界

- `medical-record-agent`（2626）：运行且 Docker health 为 healthy，但 `/ready` 当前报告 demo/mock 可用；不作为真实本地模型稳定发布证据。
- `medilisten-poc-freeze-2666`：停止并保留。
- `medical-record-agent-alpha12-20260911`（2600）：停止并保留。

因此 `alpha-demo-m3` 只具备功能候选条件；完整离线归档和新目录恢复仍需在发布冻结步骤完成后才能标为稳定版本。
