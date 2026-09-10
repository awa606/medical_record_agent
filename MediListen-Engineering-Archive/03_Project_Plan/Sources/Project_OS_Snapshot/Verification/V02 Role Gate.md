---
type: verification
project: medical-record-agent
phase: Alpha
verification_id: V02
requirement: Role Gate
related_wbs:
- '2.3'
method: 合格与不合格输入的直接 API 正反向测试
expected_result: 合格角色质量可继续；needs_review/blocked 被服务端拒绝正式生成，不能绕过前端直接调用。
actual_result: null
status: NOT TESTED
evidence: []
owner: 李国毅
acceptance:
- 同一真实音频能追踪speaker、role及role_quality
- 至少一个合格路径允许继续，至少一个不合格路径被服务端阻止正式生成
- 直接调用API不能绕过角色门禁
---

# V02 Role Gate

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "verification-item"});
```

只有本次有效实际结果和可访问证据同时具备才使用 PASS。前提缺失时使用 BLOCKED 并在 actual_result 写明原因。
