# 版本里程碑

本目录用于保存 Medical Record Agent 的关键里程碑说明。每个里程碑目录只放轻量级文档、配置摘要和证据索引，不存放真实患者数据、模型权重、下载数据集或大体积运行产物。

## 标准版本线

| 版本 | 目标能力 | GitHub Issue | 目录 |
| --- | --- | --- | --- |
| v0.1 | basic ASR pipeline | [#1](https://github.com/awa606/medical_record_agent/issues/1) | `versions/v0.1_basic_asr_pipeline/` |
| v0.2 | SSE streaming | [#2](https://github.com/awa606/medical_record_agent/issues/2) | `versions/v0.2_sse_streaming/` |
| v0.3 | role separation | [#3](https://github.com/awa606/medical_record_agent/issues/3) | `versions/v0.3_role_separation/` |
| v0.4 | medical reasoning | [#4](https://github.com/awa606/medical_record_agent/issues/4) | `versions/v0.4_medical_reasoning/` |
| v1.0 | deployable system | [#5](https://github.com/awa606/medical_record_agent/issues/5) | `versions/v1.0_deployable_system/` |

## 归档规则

- 每个里程碑必须能追溯到 GitHub Issue、每日工作日志和验证结果。
- Bug 修复必须关联 `/logs/debug/` 调试报告。
- 版本目录只记录工程证据和交接说明，不复制运行数据。
