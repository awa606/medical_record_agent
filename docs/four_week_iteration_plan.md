# 四周迭代执行计划

本文把课程手册的 Day1-Day20 过程要求映射到 Medical Record Agent 的下一轮产品化迭代。默认路线为：文件流实时转写优先、普通医院 Windows 办公 PC 为最低配置基线、四周完成 POC 到可交付版本。

## 总目标

- `v0.2.1`：MP3/WAV 上传后通过 ASR 会话和 SSE 分段显示实时转写。
- `v0.3`：增强医生/患者角色区分、置信度提示和人工校正入口。
- `v0.4`：扩展症状、疾病、检查、用药和关联规则知识库。
- `v0.5`：完成本地模型和边缘端配置评测。
- `v1.0`：完成前端产品化、文档、测试记录、Debug 记录和版本封版。

## Day1-Day20 任务表

| 阶段 | 日期范围 | 目标 | 产出证据 |
| --- | --- | --- | --- |
| 第1周 能跑 | Day1-Day5 | 打通 MP3/WAV 文件流 ASR SSE POC，建立接口和日志规范 | ASR 会话接口、SSE 事件、接口说明、每日记录 |
| 第2周 能用 | Day6-Day10 | 前端实时转写、角色显示、病历生成闭环和知识库结构扩展 | 端到端演示、角色校正记录、知识库字段表 |
| 第3周 能稳 | Day11-Day15 | 本地模型评测、稳定性测试、Bug List 闭环 | 模型评测表、30-60 分钟测试、Debug 报告 |
| 第4周 能交付 | Day16-Day20 | 前端产品化、部署说明、边缘端配置建议、v1.0 封版 | README、Release、版本日志、最终演示清单 |

## Issue Seed

这些条目按 GitHub Issue 模板整理。远端 Issue 创建后，把编号补回本文件和 `docs/traceability_matrix.md`。

| 类型 | 标题 | 验收标准 |
| --- | --- | --- |
| feature | `feat: ASR session SSE file streaming` | MP3/WAV 上传后中间转写栏按 segment 实时追加；`pytest` 覆盖会话、事件和结果。 |
| feature | `feat: doctor/patient role correction` | 每段转写显示医生/患者角色、置信度和人工校正状态。 |
| feature | `feat: medical knowledge association rules` | 知识库覆盖症状、疾病、检查、用药、规则和提示模板，并能触发候选诊断提示。 |
| research | `research: local ASR and LLM benchmark on hospital PC` | 输出准确率、延迟、CPU/内存/GPU 占用和适用模型建议。 |
| research | `research: edge deployment requirement` | 输出 CPU-only、GPU workstation、edge device 三档配置建议。 |
| refactor | `refactor: simplify audio to record workflow` | 保持 API 行为不变，减少重复流程和演示遗留分支。 |
| feature | `feat: product-grade doctor workbench UI` | 主工作区布局更清晰，上传、转写、角色校正、病历生成和导出路径可完成。 |

## 每日记录要求

每个工作日必须新增或更新 `logs/daily/YYYY-MM-DD.md`，字段使用 `logs/daily/template.md`。记录必须写结果，不只写动作；阻塞项必须能转成后续 Issue 或 Debug 报告。
