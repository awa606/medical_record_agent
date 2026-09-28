<!-- GENERATED MIRROR | SOURCE OF TRUTH: Obsidian | DO NOT EDIT MANUALLY -->

# CURRENT STATUS · medical-record-agent

> **GENERATED MIRROR**
>
> **SOURCE OF TRUTH: Obsidian**
>
> **DO NOT EDIT MANUALLY**

- Updated at: `2026-09-28T20:31:05.915198+08:00`
- Source hash: `e47847f3a9524a45c5d83ef3a84c5b3c6a8f8b97c1f558042b4b4c09c7b21d26`
- Phase: **Alpha**
- Repo: `codex/alpha51-demo-visual-e2e@be88e7453407fe1966c12e716408bc64e31d6fec`
- Base main: `a1f38cd1b5601e624a7dc22bc3462664951a8238`
- Active PR: [#113](https://github.com/awa606/medical_record_agent/pull/113) · DRAFT
- Last merged PR: [#112](https://github.com/awa606/medical_record_agent/pull/112) · MERGED · `a1f38cd1b5601e624a7dc22bc3462664951a8238`
- Forecast Alpha Exit: **Software Lane baseline 2026-10-07; restored course checkpoint 2026-09-29; first-output quality and final three-path/display gates pending; Full M4 TBD / HARDWARE DEPENDENT**

## Progress

| Backlog | Ready | In Progress | Blocked | Verify | Done | Planned Hours |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 0 | 0 | 1 | 3 | 8 | 99 |

## Current Task

**5.1 · 8B预热通过但质量9/21；8795课程数据演示及隔离恢复完成，保留4B** — `VERIFY`

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

- Single next task: 5.1：定位本地首次输出的字段归属、漏提与主体混入；保留课程历史备用，质量通过后补最终同SHA三路径及实际显示验收
- Parallel waiting task: 无；例11规则误拦单独留证；8B未晋级，训练及5.3不启动

## Manual Actions

- 当前无需操作、补数据或采购；最终版本验收时再配合物理录音与外屏检查

JSON mirror: [`CURRENT_STATUS.json`](CURRENT_STATUS.json)
