# WBS 4.2 字段证据与 Revision 关联验收证据

- 日期：2026-09-22
- 分支：`codex/alpha42-evidence-revision`
- 基线：`main@318202578ae2771ff67719a6ef34c73740460f5c`
- Research：`PASS / REUSE`
- Design Review：`PASS`
- 生产代码变更：无

## 匿名 Before / After

| 项目 | Before | After | 结果 |
|---|---|---|---|
| Revision | 2 | 3 | 连续且属于同一Encounter/Task |
| 修改字段 | 原现病史 | 医生修改后的现病史 | 可比较 |
| 字段证据 | `seg-patient-001`, 12.3–14.7秒 | 完全相同 | 保留 |
| 候选知识引用 | `NHC_TEST_GUIDELINE_2025` | 完全相同 | 保留 |
| 保存重载 | SQLite写入前对象 | 新连接读取Revision | 关联未丢失 |

测试夹具只使用匿名合成文本和不可访问的`.invalid`测试URL。

## 门禁回归

- 旧Revision ID/内容哈希返回409且不写入。
- 两个并发修改只有一个成功。
- Revision插入、Task更新、批准失效或审计失败时事务回滚。
- 修改后旧批准失效；未重新批准不得导出。

## 验证结果

- `tests/test_review_revision_transaction.py`: **13 passed**。
- 完整pytest：**528 passed, 1 warning**，213.16秒。
- `node --check static/doctor.js`: PASS。
- `git diff --check`: PASS。
- 2626 `/health`: 200。
- 2626 `/ready`: 200，但当前为`demo/mock`，只证明演示容器就绪，**不作为真实FunASR＋Qwen证据**。
- 2666与2600历史容器继续停止并保留。

## 验收结论

4.2三项验收均有可重算证据：修改前后版本可追踪、同一业务对象及字段输入片段可定位、保存重载后关联不丢失。该结论不包含3.3整页编辑器或企业级审计。

机器可读结果：[20260922_alpha42_revision_lineage.json](./20260922_alpha42_revision_lineage.json)。
