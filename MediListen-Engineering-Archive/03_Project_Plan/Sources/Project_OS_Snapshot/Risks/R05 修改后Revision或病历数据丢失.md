---
type: risk
project: medical-record-agent
phase: Alpha
risk_id: R05
description: 修改后Revision或病历数据丢失
category: 数据
probability: 2
impact: 4
affected_wbs:
- '3.3'
- '4.1'
- '4.2'
trigger: 保存后读取不一致或旧版本无法关联
mitigation: 核对SQLite及文件写入，保存后重读，关联Revision和证据
fallback: 保留测试副本定位问题，修复后重跑版本和读写检查；M3不通过
owner: 李国毅
status: open
---

# R05 修改后Revision或病历数据丢失

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "risk"});
```
