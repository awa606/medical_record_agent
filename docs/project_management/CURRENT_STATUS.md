<!-- GENERATED MIRROR | SOURCE OF TRUTH: Obsidian | DO NOT EDIT MANUALLY -->

# CURRENT STATUS · medical-record-agent

> **GENERATED MIRROR**
>
> **SOURCE OF TRUTH: Obsidian**
>
> **DO NOT EDIT MANUALLY**

- Updated at: `2026-09-18T21:28:11.221214+08:00`
- Source hash: `b9925c0ad5005abdd7efafb3a662d5a6cbb96ab4b0d0035974b6ffa5f5403fbc`
- Phase: **Alpha**
- Repo: `codex/alpha21-browser-recording-verification@d01d6b881acb6fa7826e2caacaf2fd78411eb6ac`
- Base main: `613d3889a425eeda4abb9e86fb6ab05ae6da70c0`
- Active PR: [#105](https://github.com/awa606/medical_record_agent/pull/105) · DRAFT
- Last merged PR: [#104](https://github.com/awa606/medical_record_agent/pull/104) · MERGED · `613d3889a425eeda4abb9e86fb6ab05ae6da70c0`
- Forecast Alpha Exit: **Software Lane 2026-10-07; Full M4 TBD / HARDWARE DEPENDENT**

## Progress

| Backlog | Ready | In Progress | Blocked | Verify | Done | Planned Hours |
|---:|---:|---:|---:|---:|---:|---:|
| 11 | 0 | 0 | 1 | 2 | 2 | 99 |

## Current Task

**2.2 · 真实本地ASR转写** — `BACKLOG / RESEARCH NEEDS MORE EVIDENCE`

## Hardware Gate

| Gate | Status | Classification |
|---|---|---|
| G5_technical_risk | BLOCKED | HARDWARE_DEFERRED |
| G4_mechanical_fit | VERIFY | REAL_HARDWARE_REQUIRED |
| G1_architecture | PASS | baseline_complete |
| G3_cost | VERIFY | REFERENCE_ESTIMATE_ONLY |
| G2_bom_completeness | PASS | reference_baseline |

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

- Single next task: 2.2：使用2.1真实麦克风WAV执行FunASR Research Spike，记录CER、关键词召回、RTF和峰值内存
- Parallel waiting task: Hardware Lane：DEFERRED / HARDWARE BLOCKED

## Manual Actions

- 无

JSON mirror: [`CURRENT_STATUS.json`](CURRENT_STATUS.json)
