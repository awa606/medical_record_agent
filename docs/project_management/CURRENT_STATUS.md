<!-- GENERATED MIRROR | SOURCE OF TRUTH: Obsidian | DO NOT EDIT MANUALLY -->

# CURRENT STATUS · medical-record-agent

> **GENERATED MIRROR**
>
> **SOURCE OF TRUTH: Obsidian**
>
> **DO NOT EDIT MANUALLY**

- Updated at: `2026-09-29T00:30:27.346768+08:00`
- Source hash: `6db2e30d9a3e7426351718487cc5d9ade313187e0271f06bfd2bfc2f1b9e14b7`
- Phase: **Alpha**
- Repo: `codex/alpha51-demo-visual-e2e@b2f2cf9431be2241ed079093adb394c41510c6b2`
- Base main: `a1f38cd1b5601e624a7dc22bc3462664951a8238`
- Active PR: [#113](https://github.com/awa606/medical_record_agent/pull/113) · DRAFT
- Last merged PR: [#112](https://github.com/awa606/medical_record_agent/pull/112) · MERGED · `a1f38cd1b5601e624a7dc22bc3462664951a8238`
- Forecast Alpha Exit: **Software Lane baseline 2026-10-07; restored course checkpoint 2026-09-29; first-output quality and final three-path/display gates pending; Full M4 TBD / HARDWARE DEPENDENT**

## Progress

| Backlog | Ready | In Progress | Blocked | Verify | Done | Planned Hours |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 0 | 0 | 1 | 3 | 8 | 99 |

## Current Task

**5.1 · 展示入口恢复；case11规则误拦修复，4B首次12/21、8B9/21未达质量门** — `VERIFY`

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

- Single next task: 5.1：基于可信重放基线定位4B剩余主诉错引、漏提及字段归属；质量通过后再验收最终同SHA三路径、实际显示与恢复
- Parallel waiting task: 无；例11局部修复已回归但未部署；8B未晋级，训练与5.3不启动

## Manual Actions

- 当前无需操作、补数据或采购；最终版本验收时再配合物理录音与外屏检查

JSON mirror: [`CURRENT_STATUS.json`](CURRENT_STATUS.json)
