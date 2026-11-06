# 2026-10-30 演示版：容器化单命令 + 浏览器截图

## 版本标识

| 项 | 值 |
|---|---|
| 分支 | `codex/enterprise-hardening-20261030` |
| 演示镜像 | `medical-record-agent:demo-20261030` |
| PR | #114（base `codex/alpha51-demo-visual-e2e`） |
| 演示管理员 | `admin` / `demo-admin-123`（仅 demo profile） |
| 端口 | 26300（demo overlay），默认 compose 仍为 2626 |

## 本块交付

1. `config/docker-compose.demo.yml`
   - Mock Provider、关闭 ASR 预热、固定管理员、独立网络 `10.250.250.0/24`（宿主机 Docker 默认地址池耗尽时也能启动）
   - `demo-runner` 在应用 healthy 后自动执行一次连续流程并退出，报告写入宿主 `data/demo_runtime/demo_flow.json`
2. `scripts/demo_flow.py` 增强
   - 真实后台生成需要轮询：同时等待 `result_json` 与 `current_record_revision_id`
   - 报告瘦身（13KB）：只保留标量字段与少量结构化字段，避免把整份 Revision 写进证据
   - `--seed-only`：只准备演示医生，便于浏览器手工演示
3. `scripts/browser_demo.py`
   - 自起临时服务 + Chromium，截取登录页、工作台、建档、接诊工作区四张图，写入 `.artifacts/browser-demo-20261030/`
4. `docs/runbooks/demo_flow.md` 增补容器化与截图命令
5. `--audio-file` 音频路径
   - 创建 ASR 会话 → 上传 WAV → 轮询转写（mock 6 段）→ 按 `role_quality.decisions` 的预测角色做一次显式确认（`PATCH /api/asr/sessions/{id}/result`）→ `converge-record` 生成任务
   - 之后的医生修改、审核、导出、重开与文本路径共用
   - 真机 uvicorn 实测：音频路径 30 步全 PASS、2.82s，`audio_id`/`asr_session_id` 入报告，审计链 13 条校验通过

## 验证

| 项目 | 结果 |
|---|---|
| 镜像构建 | `medical-record-agent:demo-20261030` 构建成功（复用本地层缓存） |
| compose 配置 | `docker compose ... config --quiet` 通过，服务 `medical-record-agent` + `demo-runner` |
| 容器内连续流程 | **32 步全 PASS**，耗时 51.79s，审计链 33 条校验通过，`export_event=2`，报告 `ok=true` |
| 报告大小 | 13,218 B（瘦身后） |
| 浏览器截图 | 4 张：`01_login` 422KB、`02_workbench` 74KB、`03_encounter_created` 100KB、`04_workspace` 87KB，1440×900 |
| 版本接口 | `/version` 返回 service、version、provider=mock、record_provider_mode=demo、started_at |
| 单元测试 | `tests/test_demo_flow.py` 5 项通过（文本、seed-only、音频路径、版本、二次运行复用医生） |

复现：

```powershell
docker compose -f docker-compose.yml -f config/docker-compose.demo.yml up -d --build
docker compose -f docker-compose.yml -f config/docker-compose.demo.yml logs demo-runner
python scripts/browser_demo.py --out-dir .artifacts/browser-demo-20261030
```

## 边界

- demo profile 使用 Mock Provider 与规则草稿，只证明流程衔接，不证明模型质量或临床有效性。
- 音频路径使用 Mock ASR（固定 6 段合成对话）+ 一次显式角色确认；真实音频、真实 ASR、物理麦克风与系统缩放未覆盖。
- 截图是 headless Chromium 在 Windows 宿主上的过程证据；真实 Edge、系统缩放、物理麦克风与录音未覆盖。
- 演示成功不等于医院验收；5.1 的授权音频三路径仍按原证据矩阵推进。
- 截图与报告保存在 `.artifacts/` 与 `data/`，不提交仓库；宿主机 Docker 网络池已接近耗尽，演示 overlay 固定子网只是绕开该环境问题。
