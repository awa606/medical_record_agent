<!-- GENERATED MIRROR | SOURCE OF TRUTH: Obsidian | DO NOT EDIT MANUALLY -->

# CURRENT STATUS · medical-record-agent

> **GENERATED MIRROR**
>
> **SOURCE OF TRUTH: Obsidian**
>
> **DO NOT EDIT MANUALLY**

- Updated at: `2026-11-06T07:58:56.003Z`
- Source hash: `f1fb176a57f13d4abcb64e1248b280180830938f030bd281641a3130b230c321`
- Phase: **Alpha**
- Repo: `codex/ui-hospital-record-v1@cbf2761461fe9737c6f0c2a87e47be529ba57f7a`
- Base main: `a1f38cd1b5601e624a7dc22bc3462664951a8238`
- Active PR: [#115](https://github.com/awa606/medical_record_agent/pull/115) · OPEN
- Last merged PR: None
- Forecast Alpha Exit: **26327原44115d88-perf2已恢复；规则、实时事实和默认关闭的中断恢复代码已交付。知识24查询8/15、人群过滤30到0但无答案仍失败；Nemotron60秒计算135.708秒不晋级。正式16项99h和5.1 VERIFY不变，不预报新退出日期。**

## Progress

| Backlog | Ready | In Progress | Blocked | Verify | Done | Planned Hours |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 0 | 0 | 1 | 3 | 8 | 99 |

## Current Task

**5.1 · 三条主路径E2E Smoke** — `VERIFY`

## Hardware Gate

| Gate | Status | Classification |
|---|---|---|
| G1_architecture | PASS | baseline_complete |
| G2_bom_completeness | PASS | reference_baseline |
| G3_cost | VERIFY | REFERENCE_ESTIMATE_ONLY |
| G4_mechanical_fit | VERIFY | REAL_HARDWARE_REQUIRED |
| G5_technical_risk | BLOCKED | HARDWARE_DEFERRED |

**Purchase Decision: DEFERRED**

## Milestones

| Milestone | Date | Status |
|---|---|---|
| M1 | 2026-09-23 | OPEN |
| M2 | 2026-09-25 | OPEN |
| M3 | 2026-10-01 | OPEN |
| M4 | 2026-10-07 | OPEN |

## Blockers

- 1.2 Docker / 本地运行环境整合：目标硬件支线已DEFERRED；开发机50%进度与历史证据保留。恢复后先借用或取得Jetson Orin Nano Super 8GB或等效设备，再执行两小时分层Bring-up Smoke。

## Next

- Single next task: 隔离3998194候选已完成实际历史恢复与共享目录锁检查；先恢复精确提交的远端CI，再补受影响生成/恢复验收，原26327保持44115d88。
- Parallel waiting task: 在线说话人CPU实时目标未过；BGE旧向量一致性未过；本地字段漏提仍独立研究。保留同期三种布局样机、数据准备和用户视觉选择任务；硬件仍延期。

## Manual Actions

- 打开本地23712工作台及comparison.html，按相同病例试用A/B/C；记录视觉偏好、原文查找与往返，目标医生独立使用另行记录。

JSON mirror: [`CURRENT_STATUS.json`](CURRENT_STATUS.json)
