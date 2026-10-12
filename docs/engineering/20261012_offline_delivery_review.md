# 固定审核版本的完整离线交付评审

## Research Decision Record

- 目标：迁移 `770bd920aecb45ecf0e3966db948f34b6d6fd637`，不把后续模型实验带入应用。
- 内部资产：`alpha51_release_archive.py`、`data_browser.py`、网关、中文模板、现有匿名白名单及随版帮助。
- 比较：直接复用旧包会遗漏知识缓存和历史记录；重新构建镜像会改变验收对象；采用固定镜像导出、完整缓存复制、匿名一致性数据库备份。
- Spike：D盘新建 Python 3.11 环境，从28个本地wheel通过 `--no-index` 安装 Datasette 0.65.5；查看器10项测试通过，包含中文筛选、关联、认证拒绝、下载/SQL拒绝、来源不修改和篡改拒绝。
- 选择：ADAPT现有交付工具。Research Gate：PASS（交付工具适配；不代表产品发布通过）。
- 局限：Windows、Docker Desktop、Python 3.11、Edge、现有NVIDIA环境；跨电脑和临床质量未经验证。

## 增量设计评审

| 项目 | 设计输入与交付边界 |
|---|---|
| Goal / Deliverables | D盘唯一候选包、独立恢复目录、SHA清单、启动停止说明、真实恢复记录 |
| Input / Output | 固定源码SHA/镜像ID、缓存、SQLite备份、患者白名单、授权音频、wheel → 可校验包；恢复产生独立数据和凭据 |
| Constraints | 不改变页面、Provider、接口、数据库结构、阈值；旧归档保留；两套模型互斥 |
| Largest uncertainty | 旧目录或网络下载隐性依赖；在新目录阻断网络启动、全新查看器安装验证 |
| PBS | 应用源码与镜像、模型/许可、匿名数据、查看器、帮助、恢复控制器、证据 |
| Architecture | 原工具继续读取v1；v2独立交付控制器只管包校验/复制/容器/查看器，不进入业务链 |
| Responsibilities | 创建器拥有不可变包；恢复器拥有新目录；业务服务拥有恢复库；查看器拥有匿名只读投影 |
| Interfaces | create-current显式输入；verify核对精确文件集合；restore新目录/端口/空闲确认；start拒绝模型并行；stop只管登记的本版本 |
| Errors | SHA变化、路径逃逸、缺模型、患者不在白名单、端口占用、另一模型活动均拒绝，不停止其他程序 |
| WBS | 5.1既有交付能力补齐；操作顺序为同步→工具验证→打包→恢复→发布证据；不新增正式任务 |
| Dependencies / Critical path | 工具验证先于归档；归档先于恢复；麦克风/显示随后补齐。正式CPM沿同轮Planner，不另算小时关键路径 |
| Risks | 数据：认证剥离保留账号ID；安全：包不含凭据；资源：模型互斥；排期：额外投入记R11；回退：保留原镜像原库 |
| Validation | 凭据清除、外键、版本/缓存校验、缺模型/篡改/占端口拒绝、容器断外连、真实生成与手工修订分开 |
| Milestones / Acceptance | 包可恢复为候选；三条最终路径、实际显示、5.3五次流程齐全才能发布稳定审核试用版 |

ASSUMPTION A01：默认平台使用已安装Python 3.11与Docker Desktop，包不包含操作系统或Docker安装器。恢复脚本检查前提，不下载它们。

五问：按不可变交付物拆分，便于定位缓存、数据、依赖问题；替代方案为原目录依赖或重构镜像，均不符合验收对象固定要求；最可能失败在缓存路径/离线依赖；最低成本验证为新venv及新目录内部网络启动；完成证明是包SHA、版本、数据关联、真实工作流和失败保护记录，而非容器healthy。

Design Review Gate：PASS（工具边界及最小Spike通过，允许实施已批准交付适配）。产品Gate继续VERIFY，恢复结果另行记录，不预写PASS。

参考：[pip离线依赖](https://pip.pypa.io/en/stable/cli/pip_download/)、[Docker镜像导出](https://docs.docker.com/reference/cli/docker/image/save/)。
