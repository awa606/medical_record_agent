---
type: risk
project: medical-record-agent
phase: Alpha
risk_id: R02
description: 目标硬件延迟过大或OOM
category: 性能
probability: 3
impact: 4
affected_wbs:
- '1.1'
- '1.3'
- '2.2'
- '5.2'
trigger: 基线配置无法加载模型或一次完整任务发生OOM
mitigation: W03记录CPU/RAM/显存，执行模型加载与短输入基线，限制模型规格
fallback: 重选可离线且在预算内的配置或Provider，更新基线后重测；不隐瞒超预算
owner: 李国毅
status: open
---

# R02 目标硬件延迟过大或OOM

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "risk"});
```
