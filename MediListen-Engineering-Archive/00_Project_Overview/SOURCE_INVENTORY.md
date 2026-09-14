# Source Inventory

## 盘点范围

已对 `C:\Users\AWA007\Desktop\Data\开题报告` 的可访问文件执行扩展名盘点，并检查根目录的 Office 文件、图表源文件、`病历/medical_record_agent` 代码与配置、PAMI Project OS Vault 以及相关历史资料目录。盘点不把虚拟环境、Git 内部对象、Python 缓存和 Node 依赖当作工程归档源。

盘点时发现项目含有大量历史工作树、运行证据、预览图和构建中间产物。它们保留在原位置，不在档案中重复提交。部分 QA 临时目录拒绝递归访问；这些目录未被改动，也不作为当前工程基线。

## 可访问文件类型计数

下列数值为创建本档案前的可访问盘点结果，包含历史副本：

| 类型 | 数量 |
| --- | ---: |
| `.pptx` | 152 |
| `.docx` | 635 |
| `.xlsx` | 275 |
| `.drawio` | 13 |
| `.md` | 10,579 |
| `.png` | 4,346 |
| `.svg` | 217 |
| `.py` | 8,430 |
| `.json` | 9,984 |

这些计数用于定位资料规模，不表示所有副本均为当前权威版本。

## 权威性与来源规则

| 内容 | 首选事实源 | 本档案处理 |
| --- | --- | --- |
| 当前代码、配置、API 与测试 | `../app/`、`../config/`、`../tests/`、`../Dockerfile`、`../docker-compose.yml` | 源路径索引，不复制代码 |
| 当前产品路线 | `../ROADMAP.md` | 源路径索引 |
| 当前项目状态、任务、依赖、风险和验收 | PAMI Project OS Vault `Projects/Medical_Record_Agent` | `03_Project_Plan/Sources/Project_OS_Snapshot/` 只读快照；原 Vault 为准 |
| POC/概念与课程材料 | 本目录下的 `Sources/` Office 文件 | 逐字节副本 |
| WBS、甘特、路线图和风险图 | `03_Project_Plan/Sources/` 的 `.xlsx` 与 `.drawio` | 保留可编辑源文件 |
| 预览图、视频、模型、数据集、缓存和运行日志 | 原始位置 | 仅登记，不复制或提交 |

## 归档复制校验

`Sources/` 内复制的 Office、Draw.io、工作簿和 Project OS Markdown 在提交前会以 SHA-256 与原文件核对。复制仅改变档案目录中的副本，不修改原始技术内容。
