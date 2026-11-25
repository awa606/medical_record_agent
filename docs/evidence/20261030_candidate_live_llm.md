# 2026-10-30 候选验收：真实音频 + 真实 DeepSeek

## 结论

- 候选扩展 profile `candidate-live` 已部署在 **26310**，`/ready` 200：真实 FunASR **ready**，在线 Provider **configured/reachable**（探针未触发推理）。
- 同一段真实音频（`fever_01.wav` 前 90 秒）跑完整流程：**30 段 / 2 说话人 / 角色确认 / 生成 / 修改 / 审核 / 导出 / 重开 / 完成**，121.87s，审计链 45 条。
- 与 Mock 首版对照：真实 DeepSeek 多提取到「既往处理」1 个字段，候选诊断由 1 条变为 2 条；核心完整度同为 0.2，未出现冲突或降级。
- 费用：**1 次调用，¥0.009616**（2,933 tokens，含 1,664 cached），预算 ¥20。

## 部署

```powershell
docker compose -f docker-compose.yml -f config/docker-compose.candidate.yml \
  -f config/docker-compose.candidate-live.yml up -d --build
```

| 项 | 值 |
|---|---|
| Provider | `online` / `live`，`ONLINE_LLM_PROFILE=deepseek_demo`，`deepseek-flash` |
| Key | 复用既有只读挂载 `/run/secrets/deepseek.env`（密钥不进入仓库） |
| 账本 | `/app/runtime/cost-ledger.json`（候选独立，不动 8798 账本） |
| 诊断 | `/app/runtime/business-diagnostics` |
| 重试 | `LLM_MAX_RETRIES=0`，超时 120s |
| 脱敏 | `MRA_ANONYMIZE=1` |

### 调试发现

1. **live 模式缺 `ONLINE_LLM_DIAGNOSTICS_DIR` 会 503**：`/ready` 报 `Missing environment variables: ONLINE_LLM_DIAGNOSTICS_DIR_MUST_BE_ABSOLUTE`；补绝对路径后恢复。该变量必须在候选 profile 显式设置。
2. **Provider 就绪探针不产生推理调用**：`runtime_probe.inference_called=false`，可放心用于健康检查。
3. **账本按部署隔离**：候选使用自己的账本，避免与 8798 的 20 元预算混记。
4. **follow 模式仍是真实音频的必要条件**：fast 会把整段判为单一未分配说话人并触发角色门禁 409。

## 首版对照（同一音频、同一病例）

| 项 | Mock（task 2） | DeepSeek（task 3） |
|---|---|---|
| 引擎 | `mock-deterministic-extractor` | `deepseek-flash` |
| latency | 4ms | 3,035ms |
| fallback | false | false |
| 主诉 / 现病史 | partial / complete | partial / complete |
| 既往处理 | **missing** | **complete**（提取到自购药信息） |
| 伴随症状 | complete | complete |
| 既往史 / 过敏史 / 查体 | missing | missing |
| 候选诊断 | 1 条（感冒/风寒） | 2 条（发热待查、肺部感染待排） |
| 核心完整度 | 0.2 | 0.2 |
| 冲突字段 | 0 | 0 |
| 费用 | 0 | ¥0.009616 |

结论：真实 Provider 在**字段召回**上有可见改善（既往处理），但**核心完整度仍低**（缺既往史、过敏史、查体），不能据此宣称模型质量达标；候选诊断数量变化来自提取事实差异，仍全部标记「候选/待医生确认」。

## 运行记录

```text
asr_mode          follow（5 个真实组件）
audio_transcript  30 段
role_confirmation 200 reviewed
generate          task 3
approve/export     export_event 3
reopen/complete   PASS
audit_chain       45 条 ok=true
elapsed           121.87s
ledger            calls=1 charged=9616 micro-CNY
```

原始证据：

- `.artifacts/candidate-acceptance-20261030/audio_acceptance_live.json`
- `.artifacts/candidate-acceptance-20261030/live_ledger.json`（复制自容器账本）

## 边界

- 单段 90 秒节选、单次调用，不构成统计意义上的质量评估。
- 角色确认仍由脚本按系统预测完成；真实场景需医生在界面确认。
- 未测断网（5.2）、连续五次（5.3）、物理麦克风、系统缩放与浏览器按钮路径。
- 候选仍在 26310 运行；不需要时执行 `docker compose -f docker-compose.yml -f config/docker-compose.candidate.yml -f config/docker-compose.candidate-live.yml down`。
