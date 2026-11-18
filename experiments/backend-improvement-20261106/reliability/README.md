# 生成任务中断：隔离验证

本工具只使用新目录中的合成SQLite库、真实编排器和阻塞的固定响应Provider，不启动应用服务、Docker或模型。不读取运行库，不触及8798/26327，不修改产品代码。

## 执行

```powershell
& 'C:\Program Files\Python311\python.exe' -B experiments/backend-improvement-20261106/reliability/task_interruption.py
```

程序创建自己的子进程，在该进程进入固定Provider后终止它，再用另一个进程执行应用启动所调用的`init_db()`并读取任务。只控制自己持有的Popen进程；输出在`.artifacts/backend-improvement-20261106/task-interruption/isolated-*`。合成数据和失败结果保留，不自动删除。

## 2026-11-06结果

已在Python3.11运行一次，目录`isolated-yaufzavf`：

| 项目 | 中断前 | 新进程初始化数据库后 |
| --- | --- | --- |
| 任务 | EXTRACTING_FIELDS | EXTRACTING_FIELDS |
| 步骤 | extract_fields / RUNNING | extract_fields / RUNNING |
| 错误原因 | 空 | 空 |
| 病历版本 | 无 | 无 |
| 固定Provider进入记录 | 1 | 1 |

真实模型及在线接口调用为0。结果确认数据库初始化不会收口这条中断任务；不是活服务的完整重启或恢复验收，也没有证明任何运行病例曾因此中断。

下一验证应独立设计持久任务的中断收口、实例归属和执行租约，不自动重发可能已产生外部费用的请求。此工具没有实现生产恢复或放行新版本。

## 单实例锁与中断收口的独立契约实验

`recovery_contract.py`是上述失败之后的实验实现，没有被应用启动导入。默认`enabled=False`；显式开启还要求同进程持有数据库路径对应的OS锁、配置身份一致，并声明部署前已停止所有旧写入进程。布尔声明不能自行证明旧写者已停止，生产部署必须另行核验。

```powershell
& 'C:\Program Files\Python311\python.exe' -B experiments/backend-improvement-20261106/reliability/recovery_contract.py --repo . --output .artifacts/backend-improvement-20261106/recovery-contract/windows-r1
```

不要对同一证据目录重复运行；后续实验需使用新的输出目录。恢复函数只把`CREATED / EXTRACTING_FIELDS / GENERATING_DRAFT / SAFETY_CHECKING`改为失败，同时结束其仍运行的步骤并写入审计。已有输入、结果、版本、导出和费用不重建，不触发Provider或重试。只要待收口任务关联到仍有效批准，整笔事务拒绝，留给人工核查。

### 实测记录

| 平台与范围 | 结果 | 本地证据 |
| --- | --- | --- |
| Windows Python 3.11.6，当前源码的真实SQLite建库函数 | 16项契约检查通过 | `.artifacts/backend-improvement-20261106/recovery-contract/windows-r1` |
| Linux Python 3.11.15，现有应用镜像内独立`/tmp`目录和合成库 | 同一16项契约检查通过 | `.artifacts/backend-improvement-20261106/recovery-contract/linux-r1` |

检查覆盖竞争进程拒绝、仅终止自建进程后锁可重获、正常释放、默认关闭、锁身份与旧写者前置条件、数据库身份变化拒绝、注入失败的全事务回滚、精确四状态收口、待审核/完成/失败/未知状态不动、输入与结果及版本不变、步骤和审计一致、重复执行无新增审计、无重试、有效批准异常拒绝。

Linux使用容器`d153e797cc0c`，镜像`medical-record-agent:full-acceptance-44115d88-perf2`，仅复制实验脚本到`/tmp/mra-recovery-contract-dpunjjyd`；未修改应用目录或连接运行库。实验后主服务仍为`running`，重启计数为0。Linux库代码是该运行镜像中的版本，不冒称当前源码已完成容器发布验证。两平台真实模型和云接口调用均为0。

独立ASR审查代理发现实验防误用缺口：外部提前关闭锁句柄后，旧Python锁对象仍可发起恢复。先用独立控制保留失败`closed-before.txt`，再增加`closed`与`fileno`有效性检查；Windows的`closed-after/`和Linux的`linux-closed-after/`均证明第二个锁持有者不受旧对象影响、数据库完全不变。修复后只跑这一新增控制，未重复原16项；不能把中间16项当成最后版本全量复跑成绩。

### 尚未证明的边界

- 只证明各自OS/内核中的合作进程互斥；没有证明Windows和Linux对同一共享目录互斥，也没有验证NFS等远程文件系统。
- 尚未把锁接入FastAPI lifespan；必须在数据库初始化之前取得锁，并持有到进程退出，不能只包住一次恢复函数。
- 旧版本不会获取新锁，OS锁也无法替代部署时停止全部旧写者。它不是多worker、分布式队列或租约方案。
- 进程被杀时外部在线请求可能已经扣费，无法凭本地状态判断服务端是否完成；实验明确不自动重试、不清费用预留。
- 只使用合成库验证已批准关联异常；尚无运行数据修复、真实部署恢复或发布验收结论。

此结果支持继续设计一个默认关闭的单实例候选；生产接入仍等待独立Research与Design判断。
