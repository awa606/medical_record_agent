# WBS 4.2 字段证据、知识引用与 Revision 关联 Engineering Design Review

## 1. Goal

冻结Alpha的版本关联契约：每次医生保存都建立新Revision；字段原文证据、候选知识引用、业务对象身份和内容哈希随版本保存；旧批准失效；并发旧版本不可覆盖新版本。

## 2. Non-goals

不实现整页编辑器、主动知识查询、完整批准/导出体验、跨刷新任务恢复、事件溯源平台、HIS审计或新的公共API。

## 3. Inputs and Outputs

- 输入：当前Revision ID和内容哈希、医生编辑后的`MedicalRecordFields`、已有ASR SourceSpan与Knowledge Reference。
- 输出：同一Encounter/Task下的新Revision、更新后的Task/Encounter指针、批准失效记录和审计事件。

## 4. Constraints

- 保持现有SQLite Schema、HTTP路由和Pydantic模型兼容。
- 字段证据和知识引用只读继承；医生编辑病历字段值，不直接改写来源对象。
- 所有写操作保持事务性；失败不得留下半个Revision。

## 5. Architecture

```text
current Revision + expected hash
  -> ReviewRequest
  -> deterministic draft/safety validation
  -> BEGIN IMMEDIATE
  -> invalidate old approval
  -> insert full Revision snapshot
  -> update Encounter current_revision
  -> compare-and-swap Task current_revision
  -> append audit event
  -> COMMIT / rollback on any failure
```

## 6. Module Boundaries

- `app/api/tasks.py`：校验请求、重算草稿与安全状态、把并发冲突映射为409。
- `app/db/sqlite.py`：Revision事务、内容哈希、批准失效、Task/Encounter指针和审计。
- `app/schemas/medical_record.py`：SourceSpan和ClinicalReference的持久化契约。
- `app/api/encounters.py`：读取当前和历史Revision；本轮不扩展响应。
- 3.3前端：以后必须保留只读证据对象并提交预期Revision身份。

## 7. Data Contract

Revision必须保留`encounter_id / task_id / revision_no / source / content_hash / fields_json / result_json / created_by / created_at`。字段证据至少保留`text / segment_id / index / start_time / end_time`；知识引用至少保留`reference_id / title / organization / version / url / evidence_scope / verification_status`。

## 8. Concurrency and Revision Contract

客户端提交`expected_revision_id`和`expected_content_hash`。服务器在`BEGIN IMMEDIATE`事务内比较当前Revision；任一不匹配返回409且不创建Revision、不失效当前批准、不改变Task/Encounter。

## 9. Approval and Export Boundary

成功创建医生修改Revision后，旧批准必须失效，任务返回等待医生审核；只有新Revision重新逐项批准后才能导出。知识引用不构成医生批准，也不能自动写入患者事实。

## 10. Traceability and Comparison

Before/After通过相邻Revision的完整`result_json`重算。4.2不保存派生Diff，避免双重事实源；Evidence提供一份匿名比较样例。3.3可在客户端生成显示Diff，但不得修改历史Revision。

## 11. Privacy and Security

测试只用匿名合成内容。原始音频、运行数据库、模型缓存和身份数据不进Git。Reference测试URL使用不可访问的`.invalid`域名，防止外部请求。

## 12. Failure Behavior

- 旧Revision或哈希：409，提示刷新。
- Revision插入、Task更新、批准失效或审计失败：整笔事务回滚。
- 证据冲突或安全未通过：不允许批准/导出。
- 证据对象丢失：回归测试失败，4.2不得DONE。

## 13. Test and Acceptance Strategy

- 新增关联测试：两版同一业务对象、字段Before/After、segment/time/reference保存重载一致。
- 复用既有测试：事务故障回滚、并发仅一份成功、旧ID/哈希409、批准失效和导出阻断。
- 运行定向pytest、完整pytest、前端语法、health/readiness、diff和敏感文件检查。
- 三项WBS验收全部有证据后才可进入DONE。

## 14. Rollout and Rollback

本轮没有生产Schema或API改动，发布只增加测试与证据。若后续发现问题，回退新测试/文档不会影响历史数据；实际产品修复必须保持旧Revision可读和内容哈希可重算。

## 15. Risks, Dependencies and Estimate

- 风险：3.3客户端整页编辑可能丢弃只读证据；内容较大时完整快照存储增长。
- 依赖：3.2和4.1已DONE；3.3在4.2完成后实施。
- 6h覆盖契约验证、测试、Evidence和Project OS同步；企业审计与长期归档不在范围内。

## Fixed Five Questions

1. **如何拆分？** Revision身份、字段证据、知识引用、并发、批准失效分别验证。
2. **哪些替代方案未采用？** 独立证据关系表、事件溯源平台、公共Diff API和前端整页编辑。
3. **最可能失败在哪里？** 后续客户端保存时覆盖或丢失只读证据对象。
4. **最低成本验证是什么？** 一次匿名两版本事务、重载和关联断言。
5. **如何证明完成？** 可重跑测试、连续Revision、稳定哈希、字段/引用Before-After和门禁回归。

## Gate

**Design Review Gate: PASS**。这表示版本关联边界、失败行为和验收明确；不表示3.3或完整演示闭环已通过。
