# 演示版连续流程（一条命令跑完）

本文对应 2026-10-30 加固分支上的"完整连续展示流程"：登录 → 建档 → 报到 → 开始接诊 → 生成草稿 → 医生修改 → 分项审核 → 导出 PDF → 重新打开 → 完成就诊 → 审计链与指标核对。

## 前提

- 服务已启动（本地 compose 或隔离候选），默认地址 `http://127.0.0.1:2626`。
- 管理员账号可登录；默认引导管理员为 `admin` / `admin123456`（正式环境必须改）。
- 演示使用 Mock/规则 Provider（`RECORD_PROVIDER_MODE=demo`、`LLM_PROVIDER=mock`），不产生外部模型费用。
- 演示文本为合成病例，不含真实患者信息。

## 运行

```powershell
python scripts/demo_flow.py --base-url http://127.0.0.1:2626 --json-out .artifacts/demo/demo_flow.json
```

可选参数：

| 参数 | 说明 |
|---|---|
| `--admin-user/--admin-password` | 管理员凭证 |
| `--doctor-user/--doctor-password` | 演示医生账号，不存在时自动创建（重复运行复用） |
| `--conversation-file` | 自定义合成对话文本 |
| `--audio-file` | 改走上传音频路径：ASR 会话 → 上传 → 转写 → 角色确认 → 由音频生成 |
| `--no-download` | 跳过 PDF 下载核对 |
| `--json-out` | 输出机器可读报告 |

退出码：`0` 全部步骤通过；`1` 任一步骤失败（报告里标 FAIL）。

## 容器化演示（单命令）

演示 profile 使用 Mock Provider、关闭 ASR 预热，只用于展示流程：

```powershell
docker compose -f docker-compose.yml -f config/docker-compose.demo.yml up -d --build
docker compose -f docker-compose.yml -f config/docker-compose.demo.yml logs -f demo-runner
# 报告写入宿主 ./data/demo_runtime/demo_flow.json
docker compose -f docker-compose.yml -f config/docker-compose.demo.yml down
```

- 入口：`http://127.0.0.1:26300/static/doctor.html`
- 演示管理员：`admin` / `demo-admin-123`（仅 demo profile）
- `demo-runner` 在服务 healthy 后自动执行一次 `demo_flow.py` 并退出，不常驻
- 该 profile **不是**医院候选：不改动 `docker-compose.yml` 默认端口 2626 与 ASR 配置

## 浏览器截图证据

```powershell
python scripts/browser_demo.py --out-dir .artifacts/browser-demo-20261030
```

脚本自起临时服务（Mock Provider），用 Chromium 打开真实医生页，依次截取登录页、工作台、建档后与接诊工作区，并写入 `browser_demo.json`。截图属于过程证据，不提交仓库，也不代替真实按钮验收或视觉认可。

## 步骤与判定

| 步骤 | 判定 |
|---|---|
| health / version / ready | `/health` 200；`/version` 返回 service 与版本；`/ready` 200 或 503 都记录 |
| admin_login | 管理员登录 200 |
| ensure_demo_doctor | 创建演示医生 201，已存在 400 视为通过 |
| doctor_login | 医生登录 200 |
| create_encounter | 新建就诊 200，且科室继承为 `demo-department` |
| check_in / start_encounter | 报到、开始接诊 200 |
| generate_record | 合成对话生成草稿，返回 task_id |
| doctor_edit_review | 医生修改主诉并保存新 Revision，200 且回到待审核 |
| export_readiness / approve | 按当前 Revision 与 content_hash 分项批准 |
| export | 导出成功并产生 export_event |
| download_pdf | PDF 下载 200、文件头 `%PDF`、内容非空 |
| reopen_encounter / revision_history | 重新打开就诊，Revision ≥2，任务阶段为 `exported` |
| complete_encounter | 就诊完成 200 |
| audit_chain | 管理员校验哈希链 `ok=true` |
| metrics | `/metrics` 200 且含聚合计数 |

## 候选部署（真实 ASR，隔离端口）

```powershell
docker volume create mra_candidate_models   # 首次：把既有模型缓存复制进卷
docker compose -f docker-compose.yml -f config/docker-compose.candidate.yml up -d --build
python scripts/demo_flow.py --base-url http://127.0.0.1:26310 --admin-password candidate-admin-123 --audio-file .\fever_90s_16k.wav
```

- 端口 26310；LLM 仍为 Mock，避免外部费用；ASR 为真实 FunASR，预热约 2 分钟。
- 模型缓存必须放命名卷；Windows bind mount 下模型加载会长时间无响应。
- 验收证据见 `docs/evidence/20261030_candidate_audio_acceptance.md`。

## 真实 Provider 候选

```powershell
docker compose -f docker-compose.yml -f config/docker-compose.candidate.yml `
  -f config/docker-compose.candidate-live.yml up -d
```

- 复用既有只读密钥挂载 `/run/secrets/deepseek.env`，账本写在候选运行目录。
- live 模式必须设置 `ONLINE_LLM_DIAGNOSTICS_DIR`（绝对路径），否则 `/ready` 503。
- 单次生成约 ¥0.01；`LLM_MAX_RETRIES=0`，不自动重试。
- 证据见 `docs/evidence/20261030_candidate_live_llm.md`。

## 音频路径

```powershell
python scripts/demo_flow.py --base-url http://127.0.0.1:2626 --audio-file .\demo.wav
```

步骤改为：创建 ASR 会话（`recognition_mode=follow`）→ 上传音频 → 等待转写 → 按系统预测的说话人角色做一次显式确认 → `converge-record` 由音频生成 → 之后与文本路径共用修改、审核、导出、重开。

真实连续音频请用 follow 模式：fast 模式会把整段判为单一未分配说话人，混合语句率超阈值时角色门禁会按设计返回 409。

真实音频与物理麦克风仍需在候选环境按 5.1 证据矩阵补；`--audio-file` 只证明上传链路与角色确认门禁。

## 输出示例

```text
demo flow  version=unregistered  provider=mock  ok=True
  [PASS] health                   {"status": 200, ...}
  [PASS] version                  {"service": "medical-record-agent", ...}
  ...
  ids: {"doctor_user_id": 2, "encounter_id": 1, "task_id": 1, "revision_id": 2, "export_event_id": 1}
  elapsed: 1.8s
```

## 边界

- 这是接口级连续流程，不是浏览器按钮验收；真实浏览器/录音证据仍按 5.1 的证据矩阵补。
- Mock Provider 只证明流程衔接，不证明模型质量；真实 Provider 需另跑并记录费用。
- `/version` 的版本来自 `static/deployment.json`；未登记时显示 `unregistered`，镜像推广时应写入实际 SHA。
- 演示成功不等于医院验收或临床有效性证据。
