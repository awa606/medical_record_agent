# WBS 2.1 浏览器真实录音 Engineering Design Review

> 日期：2026-09-18
> 分支：`codex/alpha21-browser-recording-verification`
> Research输入：[`R-2.1-Browser-Recording-MVP`](../research/R-2.1-Browser-Recording-MVP.md)
> 选择：**REUSE**
> Design Review Gate：**PASS**

## 1. Goal

复用现有医生工作台录音链路，让医生在Edge中使用物理麦克风完成开始、停止、试听、提交与取消；提交必须取得可追踪的`session_id/audio_id`，取消不得留下最终音频或业务任务。本任务不评价ASR准确率。

## 2. Deliverables

- 现有浏览器录音入口与五种基础操作的实测证据。
- 后端会话、音频标识、WAV元数据与SHA256。
- 取消后的清理证据。
- Research、Design Review和任务验收记录。

## 3. Input / Output

输入为用户授权的物理麦克风PCM采样。浏览器将采样编码为WAV分块并上传；服务端输出录音会话、最终`audio_id`和可读取媒体URL。取消输出为`cancelled`会话，不生成最终音频或业务任务。

## 4. Constraints

- DEV-01 Windows与Edge；本地可信上下文`127.0.0.1`。
- 使用匿名合成问诊语句，不含真实患者身份。
- Spike使用Mock ASR，只验收采音和上传。
- 不增加公共API，不纳入长录音强化、SSE重连或跨刷新恢复。

## 5. Largest Uncertainty

最大未知是浏览器权限与物理麦克风是否能在实际环境中完成采集。该未知已由Realtek麦克风阵列和13.397333秒真实录音消除。真实ASR质量仍未知，归2.2。

## 6. PBS

1. 浏览器录音控制与试听。
2. WAV编码及分块队列。
3. ASR会话上传与最终音频记录。
4. 取消与清理。
5. 验收证据。

## 7. Architecture

`Edge/getUserMedia → doctor.js录音控制与WAV编码 → IndexedDB临时队列 → /api/asr/sessions/{id}/chunks → finalize/complete → audio_id/media`。取消调用会话取消接口并清理浏览器队列及服务端分块。生产实现保持不变。

## 8. Module Boundaries

| 模块 | 责任 | 拥有的数据 |
|---|---|---|
| `static/doctor.js` | 权限、录音状态、WAV、试听、上传队列 | 浏览器瞬态录音和队列 |
| `app/api/asr_sessions.py` | 会话、分块、完成、取消 | session元数据和服务端音频 |
| 音频存储 | 最终WAV与记录 | `audio_id`、文件SHA和媒体路径 |
| ASR Provider | 将已提交音频转写 | ASRResult；不属于2.1验收 |

## 9. Interfaces

保留现有录音会话HTTP路由和`session_id/audio_id`响应。麦克风拒绝、非安全上下文、不支持MediaRecorder、上传失败和取消均显式失败或回到可恢复状态；不得用Mock音频替代真实采音。

## 10. WBS

本评审只覆盖既有WBS 2.1的验证和证据，不新增任务、不修改6h工时。代码已存在且实测满足，因此无需生产实现提交。

## 11. Dependencies

有效前置为4.1持久化DONE。2.1完成后为2.2真实ASR和3.1工作台状态流提供真实浏览器音频输入。Issue #42的V2恢复能力保持独立。

## 12. Critical Path

沿用Project Planner软件支线`4.1 → 2.1 → 2.2 → 2.3 → 3.1 → 3.2 → 4.2 → 3.3 → 5.1 → 5.3`；本评审不自行重算CPM。

## 13. Risks

- R04：前后端状态不同步；以会话文件、UI和后端标识交叉核验。
- R10：最终真实音频验收失败；2.1只证明采集，2.2必须用真实Provider重新转写。
- 原始音频泄漏；文件仅保存在`.artifacts`，Git只保留匿名摘要和SHA。

## 14. Minimal Validation

实际执行：一次物理麦克风录音完成开始、停止、试听和提交；一次录音执行取消。通过阈值为有效WAV、可试听、后端ID存在、待上传队列为0、取消后无最终音频和业务任务。结果全部通过。

## 15. Milestones / Acceptance

- 五项基础操作通过。
- 一次真实麦克风录音获得`audio_id`。
- 取消不误提交，分块及最终音频清理。
- Mock转写明确隔离，不计入2.2。

## 固定五问

1. **为什么这样拆？** 浏览器、会话、存储和ASR责任分离，能证明采音而不混淆转写质量。
2. **替代方案？** AudioWorklet或RecordRTC；当前没有必要收益。
3. **最可能失败在哪里？** 浏览器权限、设备驱动或队列清理；本轮真实Spike已覆盖。
4. **如何最低成本验证？** 一次短录音提交加一次取消。
5. **如何证明完成？** UI状态、WAV参数/SHA、会话与音频ID、取消标记、无残留文件、自动回归共同证明。

## Assumptions

- **A01**：本任务的“真实录音”指物理麦克风采音与后端保存；转写准确率由2.2验收。
- **A02**：Edge是主浏览器；Chrome为回退，不要求在主路径已通过后重复验收。

## Design Review Gate

**PASS。** 15项评审、接口、失败行为、验收和回退边界均明确，最大未知已由真实麦克风Spike消除。该PASS不表示2.2真实ASR或Alpha Gate通过。
