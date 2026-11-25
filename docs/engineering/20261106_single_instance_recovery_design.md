# 单实例中断任务恢复：研究决策与增量设计

日期：2026-11-06。源基线：36f4de7；运行比较基线：44115d88-perf2。本记录不修改正式16项/99h或5.1 VERIFY状态。

## Research Decision Record

问题：真实编排器在固定Provider处理中退出，重新执行init_db后仍留下EXTRACTING_FIELDS及RUNNING步骤。输入与费用状态不能推定请求是否已执行，禁止自动重发。

比较：只按时间标失败可能误伤活任务；引入Celery/Redis仍不能自动解决已计费请求的幂等性且扩展部署；数据库租约需要心跳、时钟与迁移；本次选择同OS单实例文件锁，启动时只收口旧进程的未完成任务。沿用SQLite事务，无新增依赖/表/API。

最低可行验证：隔离真实SQLite与编排器、固定Provider、仅终止自建子进程。Windows和Linux分别16项契约检查通过。独立复核又发现已关闭锁句柄仍可操作，保留失败并修复，两平台新增控制通过。脚本最终SHA256为6e0bdc63f74bd018a594f957f4f9c167beacd5335ae2627b66e4be87a52dda9d。原16项是修正前成绩，最后变更仅追加受影响控制，不能说全套重跑。

Evidence：experiments/backend-improvement-20261106/reliability/README.md；本地.artifacts/backend-improvement-20261106/task-interruption/、recovery-contract/。不公开数据库/原文/凭据。

**Research Gate：PASS，仅适用于同OS、同数据库绝对路径、所有写入实例协作锁、单worker、显式启用的内部候选。** 不证明跨OS共享卷、NFS、多worker、分布式队列及线上发布。在线说话人和混合检索研究仍为NEEDS MORE EVIDENCE。

## DESIGN REVIEW

| 项目 | 本次设计 |
| --- | --- |
| 1 Goal | 重启后让中断生成明确失败、保留输入与医生已有结果；不自动请求模型、不重复计费。 |
| 2 Deliverables | 内部锁/恢复模块、FastAPI生命周期接入、隔离生命周期回归、运行前置说明。 |
| 3 Input/Output | 输入为当前配置DB绝对路径、显式恢复开关及旧写者已停止声明；输出恢复任务数量或启动错误。 |
| 4 Constraints | 默认关闭；无公共API/数据库迁移/模型变化；只处理四个明确活动状态。 |
| 5 Largest uncertainty | 非协作旧进程仍可写同库；靠部署核验阻断，不把配置声明视为事实证明。 |
| 6 PBS | 锁生命周期、原子收口、启动集成、故障证据四项交付。 |
| 7 Architecture | lifespan先获取OS锁，再init_db，再原子恢复，后启动预热/监视；锁保持至整个lifespan退出。 |
| 8 Modules | recovery模块拥有锁句柄与事务；main负责启停顺序；db既有模型不变；费用账本不修改。 |
| 9 Interfaces | acquire失败拒绝启动；recover只接受当前PID的有效持锁对象及相同DB路径；finally释放。错误不降级绕过。 |
| 10 Work | 完整性代理实现模块与生命周期测试；根代理审查、整合验证；功能/ASR代理独立复核。均属R11增量，不新增正式WBS。 |
| 11 Dependencies | 本研究通过→设计通过→实现→隔离回归→原写者/挂载核验→候选启动。无模型依赖。 |
| 12 Critical path | 正式日级CPM沿用本轮15:12 Planner快照，不另算小时最长路径；本次局部依赖是上述串行链。 |
| 13 Risks | 旧写者/跨OS锁不互通→默认关闭及部署互斥；异常批准关联→整笔拒绝；事务中断→回滚；启动异常→finally释放；外部已扣费→不重试不清预留；范围扩大→不引入队列。 |
| 14 Minimal validation | 已完成两OS锁/事务Spike；新增真实lifespan测试：初始化失败释放、第二实例拒绝、默认关闭、有效批准异常拒绝、正常关停、重复恢复无写入。 |
| 15 Acceptance | 定向回归通过、独立审查、候选中实际重启只收口合成任务且不调用模型；正式部署开启还须核验全部旧写者停止和单worker。未验证前运行开关保持关闭。 |

ASSUMPTION A01：当前目标是单worker的本机Docker部署，路径对应同一内核的本地挂载；部署时必须实际核验，跨容器共享目录锁另补验证。
ASSUMPTION A02：除被登记应用外没有脚本写该业务库；不能仅靠文件锁证明，启用前核对容器挂载与后台任务。
ASSUMPTION A03：进程退出前外部服务可能已经完成/扣费；状态标失败只说明本地未完成，不声称服务端未执行。

恢复仅改CREATED、EXTRACTING_FIELDS、GENERATING_DRAFT、SAFETY_CHECKING；保留输入、result_json、retry_count、Revision、批准、导出。结束RUNNING步骤并写同事务审计。任何待收口任务关联有效批准则拒绝整次启动恢复。未知状态不改。重复运行恢复数量0，不新增审计。

## 固定五问

1. 为什么这样拆：将互斥、状态事务和生命周期分开，能分别证明没有活进程被误伤、没有部分写入、失败后不遗留锁。
2. 替代方案：超时扫描缺少执行归属；队列/租约适合多实例但本次验证与维护成本过高，不能天然保证付费调用幂等。
3. 最可能失败：旧版本不持锁或共享卷锁不互通。故默认关闭，部署核验未满足就不启用。
4. 最低成本验证：合成库+固定Provider+自建子进程，不停活服务、不联网、不加载模型；跨容器用两个无网工具容器对独立合成目录竞争锁。
5. 怎样证明完成：生产模块定向测试、实际lifespan以及隔离容器重启证据齐全。设计通过不等于发布门禁通过。

**DESIGN REVIEW GATE：PASS，允许实现默认关闭的单实例候选。** 跨容器挂载互斥、真实候选启动与发布验收继续单列待验证；未完成不得启用当前展示环境的恢复开关。

## 实现前发现与更窄的锁生命周期修订

源码核对发现：生成及ASR主工作由Starlette BackgroundTasks执行，ASR进度线程则是daemon且任务结束只等待1秒；因此不能把lifespan结束等同于所有后台写者已退出。经根代理确认，本批不增加ASGI请求追踪或改造AnyIO任务管理，改为更保守的**整个进程持锁**。

- 成功完成启动并即将yield前，把锁放入模块私有registry持强引用；lifespan正常退出、请求异常或监视器清理异常均不主动释放。
- OS在整个进程正常退出或强制终止时释放文件锁；不在atexit先解锁，避免其后仍有daemon写入。
- 同PID不得对同一数据库重新启动应用或TestClient，不支持应用热重载；测试使用独立子进程核验退出后释放。
- 进入yield之前的启动错误没有已接受的请求写者，仍由最外层finally释放锁。
- 有效批准检查覆盖任何与待恢复任务关联的历史Revision，即使`approval.task_id`为空或错误、批准不指向当前Revision也拒绝；不只检查当前版本。

**修订后Design Gate仍为PASS，仅允许上述更窄的默认关闭候选。** 原“lifespan退出释放”在成功启动路径不再适用；当前展示配置继续不启用。

## 实现记录与配置边界

内部候选在`app/services/task_recovery.py`实现，`app/main.py`仅负责启动顺序和锁保留。不修改现有运行配置。要在后续已核验的隔离部署中启用，必须同时显式设置：

| 环境变量 | 要求 |
| --- | --- |
| `MRA_SINGLE_INSTANCE_RECOVERY_ENABLED` | 默认为0；明确设为1才尝试恢复 |
| `MRA_RECOVERY_OLD_WRITERS_STOPPED` | 必须明确为1，且部署者已实际检查旧写者停止 |
| `MRA_RECOVERY_WORKER_COUNT` | 必须明确为1；不能据此替代检查服务器实际worker数量 |
| `WEB_CONCURRENCY`、`UVICORN_WORKERS` | 若存在必须为1，不允许冲突或无法解释的值 |
| `MEDICAL_RECORD_AGENT_DB` | 必须是绝对路径，取得锁后配置变化拒绝恢复 |

成功启动后即使把开关改成0，同PID仍不能对该库重新进入lifespan。恢复查询也会保守拒绝同就诊的其他有效批准；这是异常状态下的安全停机，不是自动修复所有历史不一致。费用账本和预留锁完全不动。

验证先以真实lifespan保留“应FAILED、实际EXTRACTING_FIELDS”的失败，再运行专属24项测试通过。最后增加同PID开关绕过及错误PID释放两项身份控制，仅复验新增及受影响5项通过，另21项未重复；不宣称最终26项重新全跑。测试包含独立子进程生命周期、正常进程退出和kill释放、事务注入失败、旧批准错误关联、默认关闭和初始化失败释放。未连接活业务库，真实模型与云调用为0。

证据位于本机`.artifacts/backend-improvement-20261106/recovery-contract/production-before-contract.txt`、`production-targeted-r1.txt`、`production-identity-delta.txt`。尚未部署、未开启运行版恢复开关；独立挂载与候选启动由根任务继续验收。
