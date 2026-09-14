---
type: verification
project: medical-record-agent
phase: Alpha
verification_id: V05
requirement: Offline Mode
related_wbs:
- '1.3'
- '5.2'
method: 断网运行全链路
expected_result: 模型提前缓存；断网后核心流程可执行，没有未披露云端调用或 Mock fallback。
actual_result: null
status: NOT TESTED
evidence: []
owner: 李国毅
acceptance:
- 在已冻结目标配置上验证断网核心流程
- 至少一次本地ASR、病历生成、审核和导出完整成功
- 记录断网方式，确认未切换云端或Mock
- 不未经授权中断其他本机服务
---

# V05 Offline Mode

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "verification-item"});
```

只有本次有效实际结果和可访问证据同时具备才使用 PASS。前提缺失时使用 BLOCKED 并在 actual_result 写明原因。
