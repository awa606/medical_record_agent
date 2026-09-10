---
type: project_view
project: medical-record-agent
phase: Alpha
owner: 李国毅
project_os_version: project-os-v1
cssclasses:
- project-os-view
---

# Risk Register：什么可能导致失败

概率与影响均使用1–5级；Score实时计算为Probability×Impact。风险不是已经发生的问题；状态open表示需要持续关注。

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "risks"});
```
