---
type: project_view
project: medical-record-agent
phase: Alpha
owner: 李国毅
project_os_version: project-os-v1
cssclasses:
- project-os-view
---

# Milestones / Gate：什么时候算阶段完成

M1 Environment Ready → M2 AI Pipeline Ready → M3 Clinical Workflow Ready → M4 Alpha Exit。里程碑代表阶段结果，使用原日期和依赖；不计普通任务数量和工时。

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "milestones"});
```
