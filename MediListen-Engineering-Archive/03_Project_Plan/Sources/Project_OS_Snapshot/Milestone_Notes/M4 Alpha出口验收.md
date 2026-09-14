---
project: medical-record-agent
projects:
- medical-record-agent
phase: Alpha
owner: 李国毅
people:
- 李国毅
status: open
progress: 0
tags:
- milestone
- alpha
kind: milestone
wbs: M4
task: Alpha出口验收
date: '2026-09-25'
evidence: []
type: milestone
milestone_id: M4
blockedBy:
- uid: '[[Projects/Medical_Record_Agent/Tasks/5.4 Alpha缺陷回归和证据归档]]'
  reltype: FINISHTOSTART
  kind: technical
acceptance:
- 目标方案成本≤3000元
- 断网核心流程通过
- 连续5次真实音频E2E通过
- 验收证据包完整
acceptance_verified: false
verified_by: null
verified_at: null
---

# M4 Alpha出口验收

这是阶段成果门，不是普通任务；验收不新增工时。日期和条件保存在本笔记属性中，甘特标记从这里读取。

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "milestone"});
```

任务全部完成仍须逐条核验条件并附实际证据；没有证据保持未通过。
