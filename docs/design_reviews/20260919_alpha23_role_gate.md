# WBS 2.3 医患角色门禁 Engineering Design Review

> 日期：2026-09-19
> Research 输入：[`R-2.3-Speaker-Role-Gate`](../research/R-2.3-Speaker-Role-Gate.md)
> 选择：**ADAPT**
> Design Review Gate：**PASS**

## 1. Goal

在不改变后端公共 API、角色模型、策略阈值和数据库结构的前提下，让普通医生五步工作流在真实角色质量 `409` 后提供可恢复的身份确认入口；未确认或复核后仍未通过时继续 fail-closed，通过后才允许重新生成病历。

本次不完成 Issue #41 的正式大样本阈值，不更换 diarization 模型，不新增第六个常驻流程步骤，也不评价后台 LLM 生成质量。

## 2. Deliverables

- 条件式“确认说话人身份”恢复入口。
- 从真实 `role_quality` 和 pending speaker 派生的前端门禁状态。
- 复用现有 PATCH、刷新结果、重新校验和继续生成路径。
- 双人正例、单人反例、直接 API 防绕过和审计留痕证据。
- Research、Design、Evidence 与 Project OS 状态同步。

## 3. Input / Output

输入为现有 `ASRResult` 中的 segments、speaker assignments 和 `role_quality`，以及后端返回的角色质量 `409`。医生通过现有抽屉提交全局 speaker 映射。输出为经 PATCH 保存并重新计算的 `ASRResult`、`role_reviewed` 事件和可继续或继续阻止的业务状态。

## 4. Constraints

- 保持现有五步业务流程、HTTP 路由和请求/响应兼容。
- 禁止自动猜测角色、绕过 `409` 或把低置信度结果写入病历。
- 不修改 CAM++、策略阈值、数据库 schema、Provider 或公共 API。
- 原始音频、RTTM、SQLite、日志和完整转写只保存在本地忽略目录。
- 2.3 计划仍为 2026-09-23、6h；提前验证不改 16 项/99h、依赖和里程碑。

## 5. Largest Uncertainty

最大未知是现有后端闭环是否能在真实模型输出上同时成立正路径、负路径和不可绕过性。该未知已由两段双人片段、一段单人反例、重复 `409`、PATCH 和审计事件消除。剩余最大风险是正式样本量下的 diarization/角色指标，不阻止本次 Alpha 恢复路径设计。

## 6. PBS

1. 真实角色结果与质量门禁。
2. 条件式医生恢复入口。
3. 全局 speaker 映射保存与结果刷新。
4. 生成前再次校验。
5. 正例、负例、防绕过和审计证据。

## 7. Architecture

设计基线为 `codex/alpha23-role-gate-validation@bfcd367af163905dec9aad787c814692a830d424`。本评审形成时，工作树存在限定于 `static/doctor.js` 和对应测试的候选适配；真实模型/API Spike 不依赖这些前端改动。

```text
真实音频
  → FunASR + CAM++
  → ASRResult / role_quality
  → 普通医生工作流
      ├─ passed：允许生成
      └─ needs_review / blocked：显示条件式身份确认
            → 现有 session PATCH
            → 重新计算 role_quality + role_reviewed
            ├─ passed 且 pending=0：允许重新生成
            └─ 其他：继续阻止
```

## 8. Module Responsibilities

| 模块 | Responsibility | Owned Data |
|---|---|---|
| FunASR/CAM++ | 转写、说话人分段与聚类 | segments、speaker IDs、diarization turns |
| Role policy | 角色校准、pending 与质量判定 | speaker assignments、`role_quality` |
| ASR Session API | 保存人工全局映射、重新计算并审计 | session result、`role_reviewed` |
| Audio generation API | 在生成前强制检查角色质量 | generate task 状态；不拥有角色映射 |
| Doctor UI | 仅在需要时显示恢复入口、收集医生映射并刷新 | 临时 UI 选择；不自行决定最终角色质量 |
| Evidence | 保存匿名哈希、指标和 Gate 结论 | 派生证据；不保存原始媒体到 Git |

## 9. Interfaces

| 接口 | Input | Output / 状态归属 | Error / Fail closed | 调用方与依赖 |
|---|---|---|---|---|
| `PATCH /api/asr/sessions/{session_id}/result` | 已认证用户、全局 `speaker_roles` | 更新后的 `ASRResult`；Session API 拥有持久化结果 | 无效 speaker/role、权限或状态冲突显式失败 | Doctor UI；依赖 session ID 与现有结果 |
| `POST /api/audio/{audio_id}/generate-record` | 已认证用户、现有 audio/result | 门禁通过时创建生成任务 | 角色未确认或质量未过返回 `409`；不得自动回退 | Doctor UI / 受控客户端；依赖 Audio API 与 role policy |
| Doctor recovery action | `role_quality`、pending assignments | 打开现有身份确认抽屉 | 没有可更新 session ID 时保持阻止并登记遗留缺口 | 普通医生页面；复用现有 PATCH 客户端 |

公共 API、字段结构和错误码保持现状。前端只消费服务端状态，不在客户端伪造 `passed`。

## 10. WBS

| 项目 | 冻结值 |
|---|---|
| WBS / Owner | 2.3 / 李国毅 |
| 日期 / 工时 | 2026-09-23 / 6h；提前证据不重排基线 |
| Deliverable | 角色策略、质量门禁、人工确认恢复及审计证据 |
| Acceptance | 真实双人正路径、真实单人负路径、直接 API 不可绕过、人工确认后合法继续 |
| Evidence | Research、Design Review、匿名 Evidence、Project OS V02 链接 |

实施顺序限定为：真实 Spike → Research PASS → Design PASS → 条件式 UI 适配 → 定向/浏览器/全量回归 → Project OS 同步。一次只修改恢复入口这一层。

## 11. Dependencies

- 技术链保持 `2.2 → 2.3 → 3.1`；2.2 已有效完成，2.3 通过后才释放 3.1。
- 1.2 硬件延期不阻止 DEV-01 的本次软件闭环，但继续阻止目标设备验收。
- 16 项、99h、19 条技术依赖和 4 条资源依赖保持不变。
- Issue #41 与正式冻结样本评测是后续验证依赖，不是本次 Alpha 恢复入口的前置条件。

## 12. Critical Path

沿用同轮 Project Planner 日级快照，不另写 hours 最长路径算法。2.3 是软件链中 2.2 与 3.1 之间的当前前置任务；本次不修改 Gantt、M1–M4 或 2026-10-07 软件支线预测。

## 13. Risks

| 类别 / 风险 | Trigger | Mitigation / 回退 | Owner / 影响 |
|---|---|---|---|
| Technical：说话人边界质量不足 | Boundary F1、mixed utterance 或 speaker count 在正式集退化 | 保留人工确认；正式集失败时重开 Issue #41 Research | 李国毅 / 2.3、V02 |
| Integration：快速路径缺 session ID | 角色 `409` 后无法 PATCH 当前结果 | 本轮以 follow-session 完成；快速路径登记独立遗留缺口 | 李国毅 / Doctor UI |
| Performance：真实模型冷启动或分段慢 | 角色恢复超时或资源不足 | 与2.2性能缺口分开；不在本改动更换模型 | 李国毅 / 2.2、2.3 |
| Data：真值对齐不可靠 | RTTM 或角色真值无法复核 | 仅使用无身份且轮次清晰片段；保留 SHA 和对齐规则 | 李国毅 / Evidence |
| Security：前端绕过门禁或原始音频入Git | 直接 API 可生成，或敏感/媒体文件被暂存 | 后端再次校验；敏感扫描；只提交匿名摘要 | Codex / 2.3、安全Gate |
| Schedule：6h估算超出 | UI/API/浏览器回归超时 | 只修恢复入口；超出时记录R11并重新预测 | 李国毅 / 软件支线 |
| Scope：顺手更换模型/阈值 | 出现新的Provider或schema差异 | 拒绝无关改动；每次只处理失败层 | Codex / PR范围 |
| People：角色真值依赖人工判断 | 无法确认doctor/patient映射 | 使用已授权课程音频和可复核RTTM；无法确认则 Gate 回退 | 李国毅 / Research Gate |

## 14. Minimal Validation

最低成本验证包含：

1. 两段真实双人音频经 FunASR/CAM++ 得到两个 speaker。
2. 未确认前每段连续两次生成 API 均为 `409`。
3. PATCH 全局映射后 `passed`、pending 0、`role_reviewed` 恰有 1 条。
4. 生成任务只验证被接受并排队；后台 LLM 刻意不执行。
5. 单人反例保持 `blocked / single_speaker_counterexample`，连续两次 `409`。
6. UI 回归验证入口正常时隐藏、`409` 时出现、未解决时不能继续、确认通过后可继续。

双人实测 diarization：发热片段 `speaker count error=0 / boundary F1=0.5294 / mixed=0.2857 / role consistency=0.8838`；胸痛片段 `0 / 0.3846 / 0.3750 / 0.8780`。这些数值用于描述本次输入，不作为 Issue #41 正式阈值结论。

## 15. Milestones / Acceptance

| Gate | 条件 | 本次状态 |
|---|---|---|
| Research Gate | 真实正/负路径、重复防绕过和人工恢复成立 | PASS |
| Design Gate | 边界、接口、失败行为、验证和回退明确 | PASS |
| WBS 2.3 | UI适配与全部回归、Evidence、核验人/时间齐全 | 实施完成后按 Project Planner Gate 判定 |
| V02 Alpha | 真实双人正路径、真实单人负路径、不可绕过 | 本证据支持 Alpha 范围判定 |
| Issue #41 | 正式样本量、准确率、覆盖率和高置信度错误阈值 | OPEN / 未完成 |

任务完成不等于 Alpha 阶段或目标硬件 Gate 通过。

## 固定五问

1. **为什么这样拆？** 模型与后端已经能工作，把真实策略、恢复 UI、服务端再校验和证据分层后，可以只修失败层。
2. **替代方案？** 原样复用会留下不可恢复 UI；新模型或新服务成本高且无必要证据，因此选择有限适配。
3. **最可能失败在哪里？** 正式样本上的 diarization 边界和快速上传缺 session ID；前者留给 Issue #41，后者作为独立缺口。
4. **如何最低成本验证？** 两段双人片段、一段单人反例、重复 `409`、一次 PATCH 和条件式浏览器入口。
5. **如何证明完成？** 输入与报告 SHA、匿名指标、后端 409/PATCH/审计闭环、浏览器恢复测试和完整回归共同证明。

## Assumptions

- **ASSUMPTION A01**：选取的双人片段不含可识别身份信息，且 RTTM 的 doctor/patient 对齐可用于本次工程验证。
- **ASSUMPTION A02**：follow-session 是2.3的受控主路径；快速上传若没有 session ID，不在本轮扩展 API。
- **ASSUMPTION A03**：本地 Ollama 配置只用于证明门禁通过后能够创建任务；后台 LLM 未执行，不推断病历质量。

## Design Review Gate

**PASS**。15项评审、固定五问、接口、风险、最小验证和回退均已明确。PASS 只授权既定的最小医生恢复适配，不表示 2.3、V02、Issue #41 或 Alpha 阶段已经自动通过。
