# Engineering Decision Log

本日志只记录已在资料中找到的结论及其证据。没有证据的条目明确标为 `TODO`，不把计划或候选方案写成已批准决策。

| ID | 主题 | 记录的结论 | 状态 | 依据 |
| --- | --- | --- | --- | --- |
| EDL-001 | 为什么选择 Flutter | **TODO：未找到 Flutter 已被选择的证据。** 当前代码架构为静态 HTML/JavaScript 医生工作台加 FastAPI，而非 Flutter 客户端。若未来引入 Flutter，应新增目标端、功能范围、与现有 Web 前端的取舍及验收依据。 | 未决 | `../README.md`、`../docs/architecture.md` |
| EDL-002 | 为什么选择某模型 | 已记录的是 **ASR 候选路线**，不是最终单一模型决策：以 CER、关键词召回、延迟/RTF 和资源占用进行本地评测；SenseVoice/FunASR 为交付候选，FunASR 作为长音频稳定 fallback，Qwen3-ASR 保留为研究与后续边缘/GPU 复测候选。LLM 的正式默认模型未在已检查资料中确认。 | 部分确定 | `../docs/asr_model_route.md`、`../docs/local_model_edge_benchmark.md` |
| EDL-003 | 为什么采用边缘计算 | **TODO：POC 尚未采用已验收的边缘计算方案。** 资料只表明后续 EVT 将验证边缘设备的离线运行、连续录音、异常恢复和备份；当前 POC 可运行于普通电脑或服务器的本地部署。正式采用前应记录目标硬件、模型缓存、离线证据、成本和性能结果。 | 待 EVT 验证 | `01_Requirement/Sources/midilisten_AI生成式电子病历辅助系统_综合设计3POC报告_20260731.docx`、`../docs/local_model_edge_benchmark.md` |
| EDL-004 | 为什么需要硬件终端 | **TODO：未确认“必须采用专用硬件终端”。** POC 明确没有自研硬件整机，现有运行条件是普通电脑/浏览器、麦克风或音频文件。EVT 可评估麦克风阵列和边缘设备，但这不是已完成或已批准的硬件产品决策。 | 待 EVT 验证 | `01_Requirement/Sources/midilisten_AI生成式电子病历辅助系统_综合设计3POC报告_20260731.docx`、`../docs/普通医院Windows电脑配置基线.md` |

## 记录规则

- 新增决策必须附上可定位的源文件、版本或测试证据。
- “候选”“规划”“可选”不等于已选定；通过验收前保持对应状态。
- 涉及真实患者数据、医院接口、医疗器械边界或采购的决定必须在本日志中单独记录范围和批准依据。
