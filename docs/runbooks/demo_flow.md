# 演示版连续流程（一条命令跑完）

本文对应 2026-10-30 加固分支上的"完整连续展示流程"：登录 → 建档 → 报到 → 开始接诊 → 生成草稿 → 医生修改 → 分项审核 → 导出 DOCX/Markdown → 重新打开 → 完成就诊 → 审计链与指标核对。

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
| `--no-download` | 跳过 DOCX/Markdown 下载核对 |
| `--json-out` | 输出机器可读报告 |

退出码：`0` 全部步骤通过；`1` 任一步骤失败（报告里标 FAIL）。

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
| download_docx / download_markdown | 两种格式下载 200 且内容非空 |
| reopen_encounter / revision_history | 重新打开就诊，Revision ≥2，任务阶段为 `exported` |
| complete_encounter | 就诊完成 200 |
| audit_chain | 管理员校验哈希链 `ok=true` |
| metrics | `/metrics` 200 且含聚合计数 |

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
