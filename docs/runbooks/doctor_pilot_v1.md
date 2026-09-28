# 医生试用入口与交付包

本轮为**内部候选工具包**，不是`doctor-pilot-v1`稳定发布。模型质量、最终真实三路径、实际显示及新目录恢复仍需通过；5.1保持VERIFY，5.3未启动。只用于DEV-01上的合成病例与模拟问诊。

## 医生使用

双击桌面的“MediListen 医生试用入口”，依次使用“启动服务”“打开工作台”。独立Edge配置隔离维护人员的普通浏览器登录，医生使用组织者分配的账号。面板还提供操作手册、反馈及维护说明。

关闭网页或面板不停止后台、不删除数据。停止服务前结束录音并保存。网页可打开但模型未就绪时，可以查历史记录，真实AI生成保持阻断。启动器不会切换到2626或Mock。

## 首次登记（维护人员）

前提：当前电脑已装Docker Desktop、Edge、Python，8795既有候选运行目录及固定模型已准备。该工具不是任意电脑安装器；不自动下载依赖或模型。

在仓库根目录执行：

```powershell
python scripts/doctor_pilot.py configure --project mra51repair8795 --port 8795 --config .artifacts/workbench-flow-20260928/deployment.json
python scripts/doctor_pilot.py status --config .artifacts/workbench-flow-20260928/deployment.json
powershell.exe -NoProfile -STA -File scripts/Start-DoctorPilot.ps1 -Config .artifacts/workbench-flow-20260928/deployment.json -Python C:\Anaconda\python.exe -InstallShortcut
```

登记会核对Compose标签、三个具名容器、镜像ID、loopback端口、绝对挂载、实际应用Git SHA、静态资源及固定模型manifest摘要。配置不包含密码。实际容器或资源变化时停止操作，由维护人员重新验收登记，不能手工篡改指纹“解决”失败。

`start`只管理已登记的三个容器，设置`unless-stopped`，重复启动不重建实例。`stop`按网关、应用、模型顺序停止，不清卷、不删除缓存或数据库。端口冲突不会停止其他程序；2600、2626、2666不能被登记为本候选。

桌面程序运行在Windows PowerShell 5.1，源文件保留UTF-8 BOM。没有更改机器执行策略或自动登录配置。用户若在其他电脑受组织策略限制，应由该组织维护人员处理，不关闭安全策略。

## 接诊流程与合成患者

登录默认进入工作台。选择张示例、李示例、王示例之一，登记并报到成功后仍留在工作台；点击该行开始接诊，才进入录音／上传／文本工作区。登记成功而报到失败时重试原记录，不重复登记。

只有三条明确的合成患者标识显示模拟姓名；未知历史记录继续脱敏。正在录音、尚未提交录音或未保存编辑时，切换患者被阻止。

## 手册与反馈

源文件在`docs/pilot/doctor-v1/`。本地成品在`.artifacts/workbench-flow-20260928/handbook/`，包含HTML、PDF、实际匿名截图及SHA清单。新版为分任务图文手册（含一页快速开始、PDF书签与页码）；旧包保留在原doctor-pilot-v1目录。配置可使用绝对`handbook_dir`指向新版目录。

```powershell
python scripts/build_doctor_pilot_handbook.py --manifest .artifacts/workbench-flow-20260928/manual-screenshots.json --output .artifacts/workbench-flow-20260928/handbook
```

构建工具为开发环境工具，依赖ReportLab、BeautifulSoup及本机中文字体；不进入生产容器依赖。必须先核对截图仅含合成数据并记录实际应用SHA，生成后渲染检查PDF，不能用另一版本页面截图证明本版本功能。

反馈字段包含匿名试用编号、版本、任务、完成情况、时间、求助、预期/实际和意见。浏览器仅在点击下载时生成JSON，不使用网络请求或本地持久存储；关闭前需下载。不包含病历、账号、音频自动采集功能。

## 故障与回退

| 层 | 表现与处理 |
| --- | --- |
| Docker不可用 | 面板显示错误；先启动既有Docker Desktop，不清空WSL或其他项目 |
| 实例/镜像/挂载不符 | 拒绝启动；核对候选容器和版本，不自动重建 |
| 端口冲突 | 保留占用程序，由维护人员核对，不能杀进程抢端口 |
| `/health`未通过 | 查看本版本应用/网关日志 |
| `/ready`未通过 | 页面可打开时查历史；分别检查ASR、Ollama摘要、缓存和目录，禁止Mock回退 |
| 保存后刷新慢 | 等待页面结果；重新打开最新Revision确认，避免重复保存。保存失败和刷新失败分开判断 |
| 启动锁残留 | 核对锁文件所记PID确已退出，再人工处理；工具不自动删除其他运行操作的锁 |

本轮增加的重启策略可按登记的三个容器ID恢复为`no`；回退前确认当前是否正在录音或生成。数据和既有镜像保持原样。升级必须先一致性备份、隔离验证，再重新登记；完整冻结仍按5.1/5.3 Gate执行。

## 验证边界

- 控制器测试覆盖错误镜像/挂载/模型/端口/Mock、重复启动、锁、超时及只停止本项目。
- 反馈测试验证下载、HTML转义及没有自动上传。
- 真实独立医生账号已在合成病例上完成：保存、知识查询、审核、导出、历史重开。主诉由脚本模拟医生修正，不能算模型首次正确或真实医生评价。
- 桌面面板构造与快捷方式读回可自动检查；真实Windows显示缩放、物理麦克风及外屏仍需最终现场证据。
- 同一版本三路径及恢复通过前，不将内部候选交给医生独立使用。

官方依据：[Docker重启策略](https://docs.docker.com/engine/containers/start-containers-automatically/)、[Edge网站应用与快捷方式](https://support.microsoft.com/en-us/edge/install-manage-or-uninstall-apps-in-microsoft-edge)。本工具使用Edge独立应用窗口，不声称已安装或离线缓存完整PWA。


## 2026-09-28 知识目录增量

当前8795候选应用为 `a3a5ca8`。桌面入口配置改为 `.artifacts/knowledge-workspace-20260928/deployment.json`，手册位于同目录 `handbook/`。旧配置、镜像及手册保留，回退环境文件为 `rollback.env`。

管理员：管理后台 → 资料目录／检索验证／索引状态。医生：病历字段 → 查依据。两者都检索启用版本，但医生还带入就诊上下文，排序不要求相同。2025年流感候选页码定位8/10，保持停用；不以找到文档代替正确定位。

新版手册只增补知识章节；录音、报到两张未修改区域截图沿用86f4b58并标注来源，其余为本轮实际页面。此候选没有新的物理麦克风、实际缩放或完整离线恢复证据，不是稳定发布。
