---
type: risk
project: medical-record-agent
phase: Alpha
risk_id: R07
description: Alpha范围扩张导致三周无法完成
category: 进度/范围
probability: 4
impact: 4
affected_wbs:
- '1.1'
- '5.4'
trigger: 新增Alpha+、Beta任务或第16项正式任务
mitigation: 冻结15项WBS，新增需求进入未来范围清单并评估影响
fallback: 保持边界；无法在剩余容量交付则报告延期，不占用后续阶段时间而不披露
owner: 李国毅
status: open
---

# R07 Alpha范围扩张导致三周无法完成

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "risk"});
```
