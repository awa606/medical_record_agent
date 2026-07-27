# 科室试点放行清单

Issue #76 的试点放行以“可部署、可恢复、可审计边界清楚”为准，不以真实患者生产使用为准。

## 配置与凭据

- [ ] 使用 `config/pilot.department.env.example` 复制出本地 `config/pilot.department.env`。
- [ ] 本地环境文件未加入 Git，`git status --short` 不显示真实 env 文件。
- [ ] `MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD` 已设置强密码。
- [ ] `RECORD_PROVIDER_MODE=edge` 或 `live` 时，`LLM_PROVIDER` 不是 `mock`。
- [ ] 如使用 `LLM_PROVIDER=online`，`ONLINE_LLM_API_KEY` 只在运行环境中配置。
- [ ] 如使用 `LLM_PROVIDER=ollama`，本地模型已下载并能被访问。

## 启动前预检

- [ ] `python scripts\pilot_preflight.py --env-file config\pilot.department.env` 通过。
- [ ] 如数据库应已存在，`--require-existing-db` 通过。
- [ ] 如计划验证 provider 连通性，`--check-provider-reachable` 通过。
- [ ] 预检输出没有密码、Token 或 API Key 明文。

## Docker 运维

- [ ] `docker compose --env-file config\pilot.department.env -f docker-compose.yml -f config\docker-compose.pilot.yml config` 通过。
- [ ] 容器启动后 `docker compose ... ps` 显示 healthy 或 running。
- [ ] `/health` 返回 `{"status":"ok"}`。
- [ ] `/ready` 返回 `status=ready`，并包含 SQLite、uploads、outputs、speaker_profiles、provider 检查。
- [ ] 停止、升级、回滚命令已由运维人员演练或复述确认。

## 烟测与审核导出

- [ ] `python scripts\pilot_smoke.py --base-url http://127.0.0.1:$env:MRA_HOST_PORT --username pilot_admin --password-env MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD` 通过。
- [ ] 烟测覆盖登录、文本生成、医生审核、批准、导出就绪和导出。
- [ ] 导出前必须存在医生批准记录。
- [ ] smoke 使用模拟/脱敏文本，没有真实患者信息。

## 备份恢复

- [ ] 已用 `scripts/edge_sqlite_backup.py backup` 生成 SQLite 备份。
- [ ] 已执行 backup -> mutation -> restore 演练，并确认 restore 后变更消失。
- [ ] `uploads`、`outputs`、`speaker_profiles` 已按文件级目录备份。
- [ ] 备份介质、保存期限、删除责任人已记录。

## 数据安全边界

- [ ] 试点只允许模拟或人工脱敏数据。
- [ ] 未接入真实 HIS/EMR。
- [ ] 未收集真实患者音频、病历截图、身份证号、手机号、住址、医保号、门诊号或住院号。
- [ ] 已向试点人员说明：本系统仅辅助生成草稿，不能替代医生判断。
- [ ] 已记录缺口：HTTPS、SSO、2FA、集中审计、集中密钥管理、自动留存删除和生产合规认证不在本次范围。

## 最终结论

- [ ] 放行。
- [ ] 不放行，原因：`______________________________`
