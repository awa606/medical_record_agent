---
type: risk
project: medical-record-agent
phase: Alpha
risk_id: R01
description: 本地ASR模型无法稳定离线加载
category: 模型/技术
probability: 3
impact: 4
affected_wbs:
- '1.2'
- '1.3'
- '2.2'
- '5.2'
trigger: 断网模型加载失败、缓存为空或ready仅证明demo
mitigation: 预下载模型、持久化缓存、记录模型规格并核对真实Provider ready
fallback: 保留文本诊断入口供排查，但不得用文本或Mock替代Alpha音频出口
owner: 李国毅
status: open
---

# R01 本地ASR模型无法稳定离线加载

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "risk"});
```
