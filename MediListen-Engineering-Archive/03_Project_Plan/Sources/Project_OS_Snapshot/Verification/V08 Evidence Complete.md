---
type: verification
project: medical-record-agent
phase: Alpha
verification_id: V08
requirement: Evidence Complete
related_wbs:
- '5.4'
method: 验收证据索引与逐项可访问检查
expected_result: 需求→WBS→方法→实际结果→证据可追踪，失败与重测记录保留，M4 四个条件均有证据。
actual_result: null
status: NOT TESTED
evidence: []
owner: 李国毅
acceptance:
- M4四项Exit条件均关联到可读取证据，记录代码SHA、环境、执行时间和结果
- 有修复时重跑受影响测试和连续5次E2E，不沿用修复前通过结果
- 当天无法完成修复、回归和归档时M4保持未通过，报告实际延期
---

# V08 Evidence Complete

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "verification-item"});
```

只有本次有效实际结果和可访问证据同时具备才使用 PASS。前提缺失时使用 BLOCKED 并在 actual_result 写明原因。
