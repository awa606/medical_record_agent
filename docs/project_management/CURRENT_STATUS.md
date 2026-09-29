<!-- GENERATED MIRROR | SOURCE OF TRUTH: Obsidian | DO NOT EDIT MANUALLY -->

# CURRENT STATUS · medical-record-agent

> **GENERATED MIRROR**
>
> **SOURCE OF TRUTH: Obsidian**
>
> **DO NOT EDIT MANUALLY**

- Updated at: `2026-09-29T10:32:48.210128+08:00`
- Source hash: `80faa23bb04f9482361bf25af978ced92e26285ac357af9f320e42404d405f20`
- Phase: **Alpha**
- Repo: `codex/alpha51-demo-visual-e2e@2ba52dd204a7e5c9ce0ba4346e4d67a73ef94a84`
- Base main: `a1f38cd1b5601e624a7dc22bc3462664951a8238`
- Active PR: [#113](https://github.com/awa606/medical_record_agent/pull/113) · DRAFT
- Last merged PR: [#112](https://github.com/awa606/medical_record_agent/pull/112) · MERGED · `a1f38cd1b5601e624a7dc22bc3462664951a8238`
- Forecast Alpha Exit: **Software Lane baseline 2026-10-07; restored course checkpoint 2026-09-29; first-output quality and final three-path/display gates pending; Full M4 TBD / HARDWARE DEPENDENT**

## Progress

| Backlog | Ready | In Progress | Blocked | Verify | Done | Planned Hours |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 0 | 0 | 1 | 3 | 8 | 99 |

## Current Task

**5.1 · 展示8795与独立测试8798交付；原文和分项审核恢复，模型质量及最终发布仍待验收** — `VERIFY`

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

- Single next task: 5.1：在独立测试版定位首次字段主诉归属和漏提，保留失败；模型质量通过后完成同SHA三路径、显示及恢复
- Parallel waiting task: 8795固定展示界面，后续功能进入8798；5.3和模型训练不启动

## Manual Actions

- 可通过桌面使用测试版新建匿名患者、上传音频并核对保存；最终验收时再安排物理麦克风

JSON mirror: [`CURRENT_STATUS.json`](CURRENT_STATUS.json)
