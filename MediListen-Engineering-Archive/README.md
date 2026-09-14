# MediListen Engineering Archive

本目录将 MediListen 的工程资料按阶段和主题归档，供后续 AI 协作、毕业设计管理与产品开发检索。原始技术资料未被移动或改写；对根目录资料采用逐字节副本，对现有代码、配置、测试和文档采用仓库内源路径索引。

## 项目目标

构建面向医学问诊场景的 AI 生成式电子病历辅助系统。系统将文本、音频文件或浏览器录音整理为可编辑病历草稿，保留原始证据和版本关系，并要求医生审核当前版本后才允许导出。项目仅用于课程和工程验证，不替代临床判断，不接入真实 HIS/EMR，也不使用真实患者数据。

## 当前阶段

当前项目管理事实源将项目置于 **EVT / Alpha**：`POC → Alpha → Alpha+ → Beta → EVT Exit → Ready for DVT`。本档案记录的计划快照日期为 2026-09-10。DVT 仅有路线出口标记，尚无可归档的实施计划或验收资料。

## 已完成内容

- POC 的统一输入、病历草稿、医生审核与受控导出闭环已有报告和演示材料。
- 代码仓库当前正式版本标注为 `v1.4.0`，其中服务端角色质量门禁已发布。
- 可编辑的 Alpha WBS、EVT 路线、阶段门和产品生命周期图已归档。
- 当前 Project OS 的 15 项 Alpha 任务、风险、里程碑和验证笔记已作为只读快照归档。

“代码或文档存在”不等于已完成本阶段验收；具体未证实项见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。

## 未完成内容

- Alpha 的本地部署、真实录音、本地 ASR/LLM、医生工作流、持久化和 E2E 验收任务尚无已验收证据。
- Alpha Exit 所需的成本、断网真实链路、连续 5 次真实音频 E2E 与证据完整性仍待验证。
- Alpha+、Beta、EVT Exit 和 DVT 的实施资料与验收记录待后续补充。

## 当前最大风险

真实音频在目标环境的本地、离线、可重复闭环尚未获得 Alpha 验收证据。该风险同时影响模型可用性、角色质量门禁、部署一致性和最终 E2E 验收；不可用 Mock 或文本演示替代。

## 使用方式

先阅读 [PROJECT_STATUS.md](PROJECT_STATUS.md)、[ENGINEERING_DECISION_LOG.md](ENGINEERING_DECISION_LOG.md) 和 [00_Project_Overview/SOURCE_INVENTORY.md](00_Project_Overview/SOURCE_INVENTORY.md)，再按主题进入对应目录。开发时以仓库根目录的 [README.md](../README.md)、[ROADMAP.md](../ROADMAP.md) 和 `docs/` 为代码事实源；项目状态、日期、依赖和验收以 Project OS 的原始 Vault 为准，本档案中的快照只用于追溯。

```text
MediListen-Engineering-Archive/
├── 00_Project_Overview/      项目背景、概念和盘点
├── 01_Requirement/           需求、POC 范围和毕业设计边界
├── 02_System_Architecture/   软件架构和流程图
├── 03_Project_Plan/          WBS、甘特、阶段门和计划快照
├── 04_AI_Module/             ASR、LLM、角色和证据链路线
├── 05_Hardware/              现有硬件事实和 EVT 待验证项
├── 06_Test/                  测试、验证和证据入口
└── 07_Report/                POC、评审和汇报材料
```

## 归档原则

- `Sources/` 中的 Office、Draw.io 和 Project OS 文件为原文件副本或只读快照，不在本档案内改写技术内容。
- 图片、视频、构建预览、运行日志、模型、数据集、缓存和历史工作树不重复纳入 Git；它们以源位置和用途登记，避免引入敏感数据或不可复现产物。
- 每次更新阶段、方案或验收结论时，先更新相应的 `SOURCE_INDEX.md`，再更新状态与决策记录；缺少证据时使用 `TODO`。
