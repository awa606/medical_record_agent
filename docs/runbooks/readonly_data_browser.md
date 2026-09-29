# 数据与知识查看器（只读快照）

2026-09-29中文化：当前两个环境从各自桌面入口点击“数据与知识查看器”。入口先对所属应用生成一致性备份，再按该环境匿名清单发布快照；实际端口以启动器为准。目录、表头、筛选、排序、分页、关联和权限说明使用中文，数据库及查询标识不变。🔒仅表示访问受限。使用说明见[操作手册](../pilot/doctor-v1/manual.html#viewer)，术语见[统一词表](../pilot/doctor-v1/terminology.md)。下方旧入口和旧数量保留为历史说明，不代表当前采样。

本地显示适配位于`tools/data-browser/templates`、`plugins`和`assets`，不修改第三方安装文件。Windows启动固定使用`-X utf8`读取中文模板插件。英文技术原名作为辅助信息；临床原文、知识正文和JSON原始输出保持不变。

医生入口仍为 `http://127.0.0.1:8795/static/doctor.html`。技术浏览器依次尝试8796、8797、18896、18897，以启动器输出为准。2026-09-29本轮实际使用 `http://127.0.0.1:8796/`；Windows端口限制会变化，旧18896地址不能作为固定入口。它展示**明确合成病例的只读快照**，不是实时数据库或病历编辑后台。

现在也可从桌面“MediListen 医生试用入口”点击“数据／知识浏览器”，自动恢复已登记快照并完成本地认证。“检查状态”显示实际端口、来源版本及快照时间。知识编辑仍通过“知识管理（管理员）”进入医生应用，不能在只读浏览器中修改。

## 安装、启动、刷新和停止

在本仓库根目录使用PowerShell 7。Datasette 0.65.5及依赖单独锁定，不改生产依赖。

```powershell
python -m venv .artifacts/alpha51-data-browser-20260928/venv
./.artifacts/alpha51-data-browser-20260928/venv/Scripts/python.exe -m pip install -r tools/data-browser/requirements-lock.txt
./scripts/Start-MRADataBrowser.ps1 -SourceDb '.artifacts/<本轮目录>/source-backup.private.sqlite3' -SourceLabel '8795 / <实际运行SHA> / <备份时间>' -OpenBrowser
./scripts/Start-MRADataBrowser.ps1 -Action Open
./scripts/Start-MRADataBrowser.ps1 -Action Refresh -OpenBrowser
./scripts/Start-MRADataBrowser.ps1 -Action Stop
```

`SourceDb`必须是先在应用容器内用SQLite Backup API生成、再复制到本机的一致性备份，会被解析为绝对路径。不要从Windows直接读取Docker正在使用的WAL库。刷新前重新备份，并更新来源SHA和时间；复用旧备份只能称为重新发布同一采样。首次使用本地一次性链接登录，不需要医生账号，不要复制该链接到Git或报告。后续使用同一浏览器配置；换浏览器或登录失效时执行刷新并重新打开。

刷新先生成、校验新快照，在另一个可绑定端口启动成功，再停止本工具旧进程。停止不删快照，不影响8795、2626和模型。端口选择实际尝试本机绑定，不只检查监听列表；Windows保留端口即使无人监听也不可用。默认端口均不可用时明确失败；可指定`-Port 18898`等已确认空闲端口，不停止无关服务。旧快照及manifest保留，可用同一工具重新启动。

桌面“MediListen 数据与知识浏览器”会重新发布已保存备份的快照并在本机浏览器建立新认证；它不会自动获取最新业务库。要显示新的业务变更，维护者先做容器内备份，再刷新。

## 两分钟关联演示

首页打开 `mra_snapshot`：

1. **业务链**：`patient`筛选 `SIM-DEMO-0929-FEVER`，点行ID；通过下方关联记录进入 `encounter`、`record_revision`、`approval`、`export_event`。`revision_field`展示各字段值、状态和原文引用。
2. **知识链**：`knowledge_source`查看机构和URL，进入关联 `knowledge_document`查看版本、启停和SHA，再打开 `knowledge_chunk`查看章节、页码和完整正文；最后查看 `knowledge_embedding_metadata`模型和维度。
3. 表格中的外键可返回关联记录。Datasette 0.65.5单行页主要提供入向关联；返回上游时先回表格再点外键。长正文可打开行详情阅读。

9月28日20:13、8afc6bd容器备份的投影含4名合成患者、8次就诊、12个Revision、7条批准、8条导出、7个知识文档版本、116个片段、96条embedding元数据，其中4份文档启用。后续刷新以首页和manifest为准。停用／历史文档用于版本检查，**不表示医生检索使用它们**；embedding行数不等于混合检索验收。

## 数据边界与故障

- `tools/data-browser/synthetic-allowlist.json`列出经核对的四个合成患者ID，不按前缀自动放行。
- SQLite一致性备份包含已提交WAL，再按表、列和JSON白名单投影；不迁移或初始化业务库。原库副本仅在内存，落盘只有投影。
- 不导出账号、密码哈希、登录会话、身份映射、运行凭据、音频路径、原始任务JSON或向量数组。
- 仅监听127.0.0.1；未认证403；禁止任意SQL、整库下载及写入。认证后允许读取白名单数据的分页JSON，不因此授权真实患者数据。
- 库、令牌、PID、截图和日志只在忽略目录 `.artifacts/`。
- 缺表、ID缺失、外键断裂、SHA异常均停止发布，保留旧浏览器；不自动修改源库。
- 403时使用同一浏览器配置，或 `Refresh -OpenBrowser`，不关闭认证。
- 重启后保存的PID可能被Windows分配给无关程序。启动器会忽略过期PID并保留该程序，不再将其误报为不可恢复故障；新实例仍需通过端口绑定和认证检查。
- 后台启动输出写入本地私有日志，避免子进程继承输出管道造成启动窗口一直等待。该日志不上传。

## 验证

```powershell
./.artifacts/alpha51-data-browser-20260928/venv/Scripts/python.exe -m unittest tests.test_data_browser -v
```

覆盖WAL、白名单、JSON投影、关联、原库不变、刷新保留、SHA篡改及权限。独立Edge证据见[本轮记录](../evidence/20260928_alpha51_schema_and_browser.md)。工具可用不替代5.1三路径、实际外屏缩放及最终版本离线恢复。
