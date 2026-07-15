# Medical Record Agent Roadmap

本文是当前唯一迭代路线入口。`docs/四周迭代执行计划.md`、`docs/v1_1_to_v1_4_product_roadmap.md` 和早期评分材料保留为历史归档，不再作为当前版本承诺来源。

## 当前状态

- 当前工程口径：`v1.4.0 candidate`；PR 合并、main CI 通过并打 tag 后才成立为正式 `v1.4.0`。
- 默认 Docker 角色分类：`SPEAKER_ROLE_PROVIDER=rules`。
- Mock 演示链路继续保留，用于答辩和端到端稳定演示；真实 ASR/LLM 能力必须用评测数据单独证明。
- 代码实现、数据证据、未完成事项必须在每个版本中同时说明。

## v1.3.7：工程真实性收口

目标：不加业务功能，只让仓库状态和真实实现一致。

- README、ROADMAP、版本记录统一到当前事实。
- GitHub Issue 与实际完成状态对齐，修复乱码 Issue 描述。
- 新增 GitHub Actions：`pytest -q`、`node --check static/doctor.js`、Python 3.11 启动和 `/health` 检查。
- 后续变更必须通过 Issue、分支、PR、CI 后合入。

验收标准：开放 Issue 只保留真实未完成任务；CI 全绿；主分支禁止直接提交。

## v1.4.0 candidate：服务端角色质量门禁

目标：任何前端或第三方客户端都不能绕过 speaker-role 审核生成正式病历。

- 统一 `SpeakerRoleQualityPolicy`，集中处理自动接受阈值、低置信度角色、未映射 speaker、混合语句率和人工确认率。
- `ASRResult.role_quality` 记录门禁状态、原因和指标。
- `/api/audio/{audio_id}/generate-record` 在角色质量未通过时返回 `409`。
- `/api/records/extract-fields` 传入 `segments` 时复用同一门禁；纯文本 demo 路径保持兼容。

验收标准：直接调用 API 不能绕过角色门禁；混合语句超过阈值不能标记为 `passed`；固定测试集中高置信度错误角色数为 0。

## v1.5.0：冻结评测集和阈值校准

目标：先测清楚，再决定默认模型组合。

- 建立双人问诊、三人问诊、单人朗读反例、噪声/打断/重叠样本。
- 每条样本标注真实转写、RTTM/speaker turn、speaker-role 映射、医学关键词、核心病历字段和证据段。
- 比较路线固定为：规则 -> 声纹+规则 -> 声纹+规则+Ollama -> pyannote/3D-Speaker。

建议门禁：自动接受角色准确率 >= 95%，高置信度错误角色数为 0，自动覆盖率 >= 70%，混合语句率 <= 5%，医学关键词召回率 >= 90%。

## v1.6.0：自动角色策略产品化

目标：把评测结果转成可解释、可审计的默认策略。

- 不使用模型自报 confidence 直接决策。
- 按来源校准声纹、规则、LLM 的阈值和可靠性。
- 高置信度自动通过；低置信度只触发一次全局确认。
- 输出决策原因：声纹匹配、两人约束、语义判断、质量门禁。
- Docker 默认配置与文档口径统一。

## v1.7.0：真实录音和真实病历引擎

目标：补齐当前仍是占位的真实浏览器录音和 live provider 边界。

- Browser MediaRecorder：开始、暂停、结束、取消。
- 分块上传到现有 ASR Session，支持 SSE 断线重连和重复块保护。
- 麦克风权限失败提示，录音结束后离线最终校准。
- 病历 API 分为 `demo` 和 `live`，响应返回 `requested_provider`、`actual_provider`、`fallback_reason`。
- 安全校验继续由确定性规则主导，不能完全交给 LLM。
