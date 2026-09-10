# AI Module Sources

## 现有模块入口

- [ASR 模型路线](../../docs/asr_model_route.md)：FunASR、SenseVoice、Whisper、Qwen3-ASR、Mock 和 Online 的路线与实测边界。
- [本地模型与边缘评测](../../docs/local_model_edge_benchmark.md)：性能、资源和环境证据。
- [角色质量策略](../../docs/speaker_diarization_role_strategy.md)：speaker、role 与质量门禁。
- [角色分类与转写提升计划](../../docs/自动角色分类与转写准确率提升计划_v1_3_6.md)：候选策略及其验证边界。
- [提示链设计](../../docs/scoring/prompt_chain_design.md)：课程材料中的提示链说明。

## 已归档结论

- ASR 采用可替换适配层；当前资料只支持“按评测结果选择候选”的路线，不能宣称某一模型已成为最终正式模型。
- 服务端角色质量门禁是现有工程边界；低质量角色结果不应进入正式病历生成。
- LLM Provider 的实际默认模型、模型版本、目标硬件与离线验收结果仍需以运行证据补充。

详见 [ENGINEERING_DECISION_LOG.md](../ENGINEERING_DECISION_LOG.md) 中的模型决策记录。
