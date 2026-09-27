<!-- GENERATED MIRROR | SOURCE OF TRUTH: Obsidian | DO NOT EDIT MANUALLY -->

# CURRENT STATUS · medical-record-agent

> **GENERATED MIRROR**
>
> **SOURCE OF TRUTH: Obsidian**
>
> **DO NOT EDIT MANUALLY**

- Updated at: `2026-09-27T15:07:20.447929+08:00`
- Source hash: `1171faffa8fb9716c9501c8eb3b530814504cd2c97efa191cd82ddf2a24d18cb`
- Phase: **Alpha**
- Repo: `codex/alpha51-demo-visual-e2e@272fa6bdd2843e0cce69d5682a103f47a10604d2`
- Base main: `a1f38cd1b5601e624a7dc22bc3462664951a8238`
- Active PR: [#113](https://github.com/awa606/medical_record_agent/pull/113) · DRAFT
- Last merged PR: [#112](https://github.com/awa606/medical_record_agent/pull/112) · MERGED · `a1f38cd1b5601e624a7dc22bc3462664951a8238`
- Forecast Alpha Exit: **Software Lane baseline 2026-10-07; visual rework/restore impact pending; Full M4 TBD / HARDWARE DEPENDENT**

## Progress

| Backlog | Ready | In Progress | Blocked | Verify | Done | Planned Hours |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 0 | 0 | 1 | 3 | 8 | 99 |

## Current Task

**5.1 · 三路径Smoke：0d39d642部署候选已复验，人工缩放后切换2626** — `VERIFY`

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

- Single next task: 补齐实际Edge125%/150%证据，满足门禁后切换2626，再完成最终SHA真实三路径与离线恢复
- Parallel waiting task: 无；5.1保持VERIFY，5.3不启动

## Manual Actions

- 8791手动设置Edge125%及150%，提供菜单百分比和关闭菜单后的页面/详情截图；不再重复原生识别

JSON mirror: [`CURRENT_STATUS.json`](CURRENT_STATUS.json)
