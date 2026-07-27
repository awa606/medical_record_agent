# 科室试点部署与运维手册

本文面向单科室、单节点、局域网内试点。试点只允许使用模拟数据或人工脱敏数据，不接入真实 HIS/EMR，不处理真实患者数据，不声明生产合规认证。

## 1. Fresh Install

在项目根目录准备本地环境文件：

```powershell
Copy-Item config\pilot.department.env.example config\pilot.department.env
notepad config\pilot.department.env
```

必须在本地填写：

- `MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD`：首次启动前设置强密码，不能使用默认值、用户名、短密码或常见弱口令。
- `OLLAMA_MODEL` 或 `ONLINE_LLM_*`：`RECORD_PROVIDER_MODE=edge` 下必须使用已配置的非 mock provider。
- `MRA_HOST_PORT`：建议先用 `python scripts\check_docker_port.py --start 2600 --end 2699 --format env` 选择可绑定端口。

环境文件、密码、Token、API Key 只保存在本机，不提交 Git。

## 2. 启动前预检

先在宿主机用同一个环境文件做预检：

```powershell
python scripts\pilot_preflight.py --env-file config\pilot.department.env
```

需要验证已有数据库时：

```powershell
python scripts\pilot_preflight.py --env-file config\pilot.department.env --require-existing-db
```

需要实际调用 provider 时：

```powershell
python scripts\pilot_preflight.py --env-file config\pilot.department.env --check-provider-reachable
```

预检覆盖 SQLite 路径、运行目录可写性、磁盘余量、edge/live 强密码和 provider 配置。脚本不会初始化数据库，也不会替代应用已有的 `/ready` 检查。

## 3. Docker 启动、停止、升级、回滚

启动：

```powershell
docker compose --env-file config\pilot.department.env -f docker-compose.yml -f config\docker-compose.pilot.yml up -d --build
```

检查：

```powershell
docker compose -f docker-compose.yml -f config\docker-compose.pilot.yml ps
curl.exe http://127.0.0.1:$env:MRA_HOST_PORT/health
curl.exe http://127.0.0.1:$env:MRA_HOST_PORT/ready
```

停止但保留数据：

```powershell
docker compose -f docker-compose.yml -f config\docker-compose.pilot.yml stop
```

停止并移除容器但保留 `data/pilot_runtime/` 和模型缓存：

```powershell
docker compose -f docker-compose.yml -f config\docker-compose.pilot.yml down
```

升级：

```powershell
git fetch origin
git switch codex/pilot-ops-v1
git pull --ff-only
python scripts\pilot_preflight.py --env-file config\pilot.department.env --require-existing-db
docker compose --env-file config\pilot.department.env -f docker-compose.yml -f config\docker-compose.pilot.yml up -d --build
python scripts\pilot_smoke.py --base-url http://127.0.0.1:$env:MRA_HOST_PORT --username pilot_admin --password-env MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD
```

回滚：

```powershell
docker compose -f docker-compose.yml -f config\docker-compose.pilot.yml down
git log --oneline -5
git switch --detach <last-known-good-commit>
python scripts\pilot_preflight.py --env-file config\pilot.department.env --require-existing-db
docker compose --env-file config\pilot.department.env -f docker-compose.yml -f config\docker-compose.pilot.yml up -d --build
```

回滚前后都要保留当时的 Git commit、镜像构建时间、预检输出和烟测输出。

## 4. 一键烟雾测试

服务启动并 `/ready` 通过后运行：

```powershell
python scripts\pilot_smoke.py --base-url http://127.0.0.1:$env:MRA_HOST_PORT --username pilot_admin --password-env MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD
```

烟测会依次执行健康检查、就绪检查、登录、模拟问诊文本生成、审核、批准、导出就绪检查和导出。脚本只读取密码环境变量，不从命令行接收密码，也不会打印密码。

## 5. 备份与恢复演练

SQLite 一致性备份使用已有 CLI：

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts\edge_sqlite_backup.py backup --db data\pilot_runtime\medical_record_agent.sqlite3 --output backups\pilot-$stamp.sqlite3
```

恢复演练建议在维护窗口执行：

```powershell
docker compose -f docker-compose.yml -f config\docker-compose.pilot.yml stop
Copy-Item data\pilot_runtime\medical_record_agent.sqlite3 backups\before-restore.sqlite3
python scripts\edge_sqlite_backup.py restore --backup backups\pilot-$stamp.sqlite3 --db data\pilot_runtime\medical_record_agent.sqlite3 --force
docker compose --env-file config\pilot.department.env -f docker-compose.yml -f config\docker-compose.pilot.yml up -d
python scripts\pilot_smoke.py --base-url http://127.0.0.1:$env:MRA_HOST_PORT --username pilot_admin --password-env MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD
```

文件级运行目录也要备份：

- `data/pilot_runtime/uploads/`：上传音频和中间转写材料。
- `data/pilot_runtime/outputs/`：导出的 Markdown/Word 文件。
- `data/pilot_runtime/speaker_profiles/`：医生声纹注册文件。

这些目录需要与 SQLite 备份同一时间点保存。推荐停止容器后复制整个 `data/pilot_runtime/` 到离线介质，并记录备份时间、操作者和删除期限。

## 6. 数据使用、留存与删除

试点数据规则：

- 只使用模拟病例、公开课程样例或人工脱敏材料。
- 脱敏后仍要去除姓名、身份证号、手机号、住址、医保号、门诊号、住院号、精确日期和可识别影像/音频线索。
- 禁止把真实患者音频、病历截图、HIS/EMR 导出、API Key、Token 或账号密码提交到 GitHub。
- 运行数据保存在本机 `data/pilot_runtime/`，默认不提交。

建议留存：

- 烟测和演示样例：试点结束后 7 天内删除。
- 脱敏问题样本：只保留定位缺陷所需最小字段，最长 30 天。
- 备份文件：按科室试点周期保留，试点结束或复盘完成后销毁。

已知缺口：

- 本 PR 不支持真实患者数据上线。
- 本 PR 不提供等保、HIPAA、GDPR、医院生产合规认证。
- 本 PR 不提供 HTTPS 终止、SSO、2FA、集中审计、集中密钥管理和多节点灾备。
- 删除动作目前依赖人工执行文件和备份清理，缺少应用内留存策略和自动删除任务。

## 7. 放行前证据

放行前至少保存以下证据：

- `python scripts\pilot_preflight.py --env-file config\pilot.department.env --json` 输出。
- `curl /health` 和 `curl /ready` 输出。
- `python scripts\pilot_smoke.py ... --json` 输出。
- SQLite 备份文件路径、恢复演练记录、恢复后烟测结果。
- Docker image/commit、启动时间、操作者、回滚 commit。

如果任一项失败，不允许进入科室试点。
