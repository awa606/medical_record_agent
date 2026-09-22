# WBS 3.3 医生修改、审核与导出 Engineering Design Review

## 1. Goal

在现有医生工作台中完成整页病历编辑、主动查询知识依据、保存 Revision、分项审核、重新审核和受控 DOCX 导出，不改变公共 API。

## 2. Deliverables

- 整页字段编辑、取消和未保存提示。
- 字段证据详情，包含原文、说话人、角色、时间片段和置信度。
- 字段级“查依据”面板，展示完整引用元数据。
- Revision 保存、旧批准失效、409 并发冲突提示。
- 审核前导出拒绝、审核后导出且文件内容为最新修改。
- 浏览器与服务端回归证据。

## 3. Input / Output

输入为当前任务的结构化字段、ASR 片段、Revision 标识和知识检索结果。输出为新 Revision、审核记录和最新批准 Revision 对应的 DOCX。

## 4. Constraints

- 保留 `/review`、`/approve`、`/export` 和 `/api/knowledge/retrieve`。
- 原始证据和知识引用只读。
- 医生修改必须审计，不能伪装成 AI 或原文证据。
- 不增加数据库结构、公共路由或前端框架。

## 5. Maximum Uncertainty

在 `live/edge` 模式下，严格证据校验可能把医生手工修订误判为 AI 无依据改写。设计使用现有 `doctor_review_note` 标明人工修改，并保留原证据；服务端只对显式人工编辑采用人工审核语义，仍校验证据身份、角色及危险冲突。

## 6. PBS

1. 编辑状态与表单控件。
2. 字段证据和知识查询。
3. Revision 冲突与批准失效。
4. 审核和导出。
5. 浏览器及 API 验证。

## 7. Architecture

```text
医生页面编辑状态
  -> 现有 /review 条件写入
  -> 新 Revision + 旧批准失效 + 审计
  -> 现有 /approve 分项审核
  -> 现有 /export 服务端门禁

字段“查依据”
  -> 现有 /api/knowledge/retrieve
  -> 只读引用详情
```

## 8. Module Boundaries

- `static/doctor.js`：编辑、查询、冲突提示和展示。
- `static/doctor.html` / `static/doctor-ui-v2.css`：控件和视觉状态。
- `app/api/tasks.py` / `app/services/field_grounding.py`：仅在人工修改语义缺口被测试证明时做最小适配。
- 知识库、模型和录音模块不变。

## 9. Interfaces

不新增接口。保存继续提交完整 `fields`、`expected_revision_id` 和 `expected_content_hash`。知识查询继续提交 `task_id`、`query` 和 `related_fields`。

## 10. State and Failure Behavior

- 编辑开始时保存本地基线；取消恢复基线。
- 输入变化标记为未保存，审核和导出按钮停用。
- 保存成功后退出编辑模式、刷新 Revision，旧批准自动失效。
- 409 时保留本地编辑，显示当前 Revision 已变化并提供“加载最新版本”。
- 知识查询失败只影响参考面板，不修改病历字段。
- 未审核或冲突状态由服务端拒绝导出，前端不能绕过。

## 11. Data and Privacy

原始音频、数据库和导出文件留在本地测试目录。Git 只保存匿名测试摘要。知识查询继续经过现有匿名化处理。

## 12. Verification

- 浏览器：编辑全部章节、取消恢复、保存重载、主动查询、409 冲突、审核和下载。
- API：旧批准失效、旧 Revision 409、未审核导出受控拒绝、最新审批导出成功。
- DOCX：解压检查修改后内容。
- 回归：角色门禁、Encounter 恢复、权限隔离、完整 pytest 和前端语法。

## 13. Rollback

回退前端编辑和查询提交即可恢复只读医生工作台。公共 API 和数据库未迁移，不需要数据回滚。

## 14. WBS / Dependencies

任务保持 WBS 3.3、6h、2026-09-29。前置 3.2、4.1、4.2 已完成。完成后释放 5.1；若超过 6h，登记 R11，不降低验收标准。

## 15. Acceptance and Stop Condition

停止条件为：修改保存后重载一致；未审核直接 API 导出被非 500 业务响应拒绝且无文件；审核后导出文件包含修改内容。完成后不提前执行 5.1 冻结包。

## 固定五问

1. 如何分层？编辑、证据、知识查询、Revision、审核导出分层验证。
2. 不采用什么？不重写页面、不增加状态机框架或公共 API。
3. 最可能失败在哪里？人工修改与严格证据校验冲突，以及并发 Revision 变化。
4. 最低成本验证是什么？匿名任务通过现有 API 完成一次编辑—保存—审核—导出。
5. 如何证明完成？Revision、审计、409、导出门禁、DOCX 内容和浏览器证据共同证明。

## Design Review Gate

**PASS**。该结论只表示实现边界和验收方式明确，不代表 3.3 已完成。
