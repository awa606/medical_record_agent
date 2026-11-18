# 2026-10-30 候选验收：隔离端口部署 + 真实音频

## 结论

- 候选镜像 `medical-record-agent:candidate-d7b86f3` 已部署到隔离端口 **26310**，健康检查 `healthy`。
- 真实 FunASR 就绪：`paraformer-zh-streaming`、`paraformer-zh`、`fsmn-vad`、`ct-punc`、`cam++`，预热 **112.8s**。
- 真实音频（`fever_01.wav` 前 90 秒，16k 单声道）走 follow 模式：**30 段、2 个说话人、混合语句率 0.0**；显式确认角色后生成成功。
- 全流程 **30+ 步全 PASS，168.12s**：上传 → 转写 → 角色确认 → 生成 → 医生修改 → 分项审核 → 导出 → 重开 → 完成 → 审计链（19 条）→ 指标。
- 导出：DOCX 1759B、Markdown 997B。**LLM 仍为 Mock**，不产生外部模型调用。

## 部署

```powershell
docker compose -f docker-compose.yml -f config/docker-compose.candidate.yml up -d --build
```

| 项 | 值 |
|---|---|
| 端口 | 26310 |
| 网络 | `10.250.251.0/24`（固定子网，避开宿主地址池耗尽） |
| 模型 | 命名卷 `mra_candidate_models`（5.8GB，从既有缓存复制） |
| 管理员 | `admin` / `candidate-admin-123`（仅候选 profile） |
| ASR | `funasr`，`REQUIRE_FUNASR=1`，预热开启 |
| LLM | `mock` / `RECORD_PROVIDER_MODE=demo` |
| 健康 | `/ready` 200，`asr_models.status=ready` |

### 部署中发现并修复的问题

1. **Windows 绑定挂载导致预热卡死**：首次把 5.8GB 模型缓存以 bind mount 方式挂进容器，模型加载约 45 分钟无进展且 `/health` 超时；改为命名卷（容器内 ext4）后 **112.8s** 完成预热。
2. **HF 联网挂起风险**：候选 profile 增加 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`，离线使用缓存。
3. **fast 模式对真实连续音频过严**：fast 单文件转写把整段判为一个 `speaker_unassigned`，混合语句率 0.5–1.0，角色门禁按设计返回 409；改用 `recognition_mode=follow` 后得到 30 段/2 说话人，门禁可通过。演示脚本现按环境自动选择：真实模型已预热（`/api/asr/prewarm/status` 有 components）→ follow，Mock → fast，可用 `--recognition-mode` 覆盖。

## 真实音频运行

```powershell
python scripts/demo_flow.py --base-url http://127.0.0.1:26310 `
  --admin-password candidate-admin-123 `
  --audio-file .\fever_90s_16k.wav `
  --json-out .artifacts\candidate-acceptance-20261030\audio_acceptance.json
```

| 步骤 | 实际结果 |
|---|---|
| ASR 会话 / 上传 | `engine=funasr`，session `42be3129…`，audio `d851f844…` |
| 转写 | 30 段，2 说话人，混合语句率 0.0 |
| 角色确认 | PATCH 200，`status=reviewed` |
| 生成 | `converge-record` 200，task 1 |
| 医生修改 / 审核 / 导出 | Revision 2、approved、export_event 1 |
| 重开 / 完成 | 未丢状态，encounter completed |
| 审计链 | 19 条，`ok=true` |
| 指标 | `/metrics` 200 |

自动化模式复验（`asr_mode=follow` 自动选择）：30 段、2 说话人、角色确认、生成、导出、重开、完成全 PASS，198.19s，审计链 32 条；报告 `.artifacts/candidate-acceptance-20261030/audio_acceptance_auto.json`。

## 边界

- LLM 是 Mock/规则，不证明模型质量；费用 0。
- 音频为仓库内合成咨询录音的 90 秒节选，不是本轮新采录音；物理麦克风、浏览器录音、实际缩放未测。
- follow 模式下的说话人角色由脚本按系统预测自动确认，真实场景需医生本人确认。
- 未接入真实 Provider（DeepSeek/Ollama）、未做断网 5.2、未跑 5.3 连续五次。
- 候选容器仍在 26310 运行，验收后可直接访问医生页。

## 原始证据

- `.artifacts/candidate-acceptance-20261030/audio_acceptance.json`（30 步报告）
- `.artifacts/candidate-acceptance-20261030/prewarm.json`（预热状态与组件）
- `.artifacts/candidate-acceptance-20261030/fever_90s_16k.wav`（实际输入，2.8MB）
