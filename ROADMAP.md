# Medical Record Agent Roadmap

本文是当前唯一迭代路线入口。旧的四周计划、v1.1-v1.4 草案和早期评分材料只作为历史归档，不再作为当前版本承诺来源。

## 当前状态

- 当前正式版本：`v1.4.0`。
- 默认 Docker 角色分类：`SPEAKER_ROLE_PROVIDER=rules`。
- 仓库治理：`main` 要求 PR 和 `verify` CI；单人维护模式不要求同账号自审，说明见 `docs/repository_governance.md`。
- `frozen_clinical_v1` 只作为 CI/schema/smoke 回归集，不作为生产准确率证据。
- `v1.5.0` 尚未发布；必须等 #50 可执行评测集和 Provider 基线合并后再考虑。

每个版本必须回答三个问题：代码实现了什么、数据证明了什么、还有什么没完成。

## v1.4.0：服务端角色质量门禁

目标：任何前端或第三方客户端都不能绕过 speaker-role 审核生成正式病历。

- 统一 `SpeakerRoleQualityPolicy`。
- `ASRResult.role_quality` 记录门禁状态、原因和指标。
- `/api/audio/{audio_id}/generate-record` 在角色质量未通过时返回 `409`。
- `/api/records/extract-fields` 传入 `segments` 时复用同一门禁；纯文本 demo 路径保持兼容。

验收状态：已发布。

## v1.5.0：可执行评测集和 Provider 基线

目标：先让 speaker-role 评测可执行、可复现、统计口径足够诚实，再进入阈值校准。

- 保留 `frozen_clinical_v1` 作为最小回归集。
- 建立 `executable_clinical_v1`，覆盖 21-23 条 synthetic WAV/FLAC 问诊样本。
- 使用 Git LFS 保存 synthetic 音频，普通 Git 只保存 manifest、标注、脚本、prediction artifact 和报告。
- truth annotation 与 prediction artifact 完全分离。
- rules、voiceprint、LLM Provider 分开报告；Mock 不计入产品准确率。
- 报告包含样本数、split、场景覆盖、角色准确率、自动覆盖率、高置信错误数、人工确认率、speaker 数量准确率、混合语句率、关键词召回率和 95% 置信区间。
- calibration/test 严格隔离；校准命令不得读取 test 标签。

验收标准：#50 合并、main CI 通过、报告可由一条命令复现。未达到前不得创建 `v1.5.0` tag 或 Release。

## v1.6.0：自动角色策略与阈值校准

目标：把 v1.5 的评测结果转成可解释、可审计的默认策略。

- #41 必须在 #50 合并后单独 PR 实现。
- 只使用 calibration split 选择阈值，test split 只用于最终验收。
- 按 Provider 分别配置阈值和降级策略：rules、voiceprint、LLM 不共用一个常量。
- 输出 `raw_confidence`、`calibrated_confidence`、`provider`、`policy_version`、`reason_code`、`action`。
- 高风险错误优先进入人工确认，不为了覆盖率放过高置信错误。

## v1.7.0：Demo/Live Provider 解耦

目标：把稳定答辩演示链路和真实 Provider 路线分清。

- 病历生成 API 分为 `demo` 与 `live`。
- 每个响应返回 `requested_provider`、`actual_provider`、`fallback_reason`。
- Mock/规则链路保留为稳定演示能力；真实 LLM Provider 的质量必须有独立评测证据。

## v1.8.0：浏览器录音与断线恢复

目标：补齐真实浏览器录音，而不是只恢复占位入口。

- Browser MediaRecorder：开始、暂停、结束、取消。
- 分块上传到现有 ASR Session。
- SSE 断线重连和重复块保护。
- 麦克风权限失败提示。
- 录音结束后执行离线最终校准。

当前门禁：自动测试已有记录；Chrome/Edge 真人长录音、断网恢复、刷新恢复和内存观察暂时冻结。冻结不等于通过，在恢复真人验收前不得把该项作为发布证据。

## v1.9.0：专病疾病包来源追溯

目标：让发热/呼吸道疾病包的候选诊断参考同时携带对话证据与外部指南来源，避免把代码规则误解为无来源的医学结论。

- 保持 `fever_respiratory_v1` 的规则 ID 和冻结 E2E 口径不变。
- 为候选诊断增加来源编号、标题、发布机构、版本、发布日期、链接和适用范围。
- 分开记录“来源已核验”和“规则映射待医学审核”，不能用链接存在代替医学审核。
- 首批来源覆盖国家卫生健康委流感方案、NICE 肺炎指南、CDC 流感临床资料和 WHO 严重急性呼吸道感染工具包。
- 后端来源字段完成后，再在产品化医生工作台中增加来源查看入口。

## 发布门禁：权限、审批和导出保护

如果系统准备在局域网、公开服务器或真实演示环境运行，安全门禁必须提前到浏览器录音前完成。

- 保护 doctor approval、speaker profile 和导出接口。
- 记录审批、导出和关键配置变更审计日志。
- 继续保持确定性规则主导的安全校验，不能完全交给 LLM。
