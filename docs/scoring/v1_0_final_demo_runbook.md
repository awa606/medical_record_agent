# v1.0 终答辩演示 Runbook

## 0. 开场前检查

```powershell
docker compose up -d --build medical-record-agent
Invoke-RestMethod http://127.0.0.1:2601/health
node --check static/doctor.js
```

预期结果：

- `medical-record-agent` 为 `running` / `healthy`。
- `/health` 返回 `ok`。
- 浏览器打开 `http://127.0.0.1:2601/static/doctor.html`。

## 1. 预热

1. 打开医生端。
2. 先用 `snakebite_01.wav` 走一次 FunASR，等待模型加载完成。
3. 如果模型下载或初始化超过 2 分钟，切换到 Mock ASR 继续录屏主线。
4. 不删除 `data/asr_model_cache/` 和 `data/docker_runtime/`。

## 2. 主演示顺序

1. 展示首页和医生审核边界。
2. 点击“文本生成”，用默认 fever clean 文本生成病历。
3. 展示左侧病历字段、右侧候选诊断、治疗方案和证据面板。
4. 切换 Mock ASR，上传 `snakebite_01.wav`，展示 SSE 分段追加。
5. 打开“显示设置”，展示按说话人统一校正和逐段文本校正。
6. 展示已完成的 FunASR session：38 条转写段、播放器、倍速、拖动和 Range。
7. 展示 RTTM 评测汇总：`fever_01` 与 `chest_pain_01` 两条两说话人结果。
8. 展示冻结清单和不可提交文件边界。

## 3. 现场话术

- “Mock ASR 是保底演示路线，用于证明 SSE、前端和病历 Agent 闭环。”
- “FunASR 是真实本地 ASR 路线，首次冷启动可能下载和初始化模型，所以答辩前需要预热。”
- “`snakebite_01` 是单人朗读，只用于 ASR 流程，不作为 diarization 成绩。”
- “本轮只发布两说话人 RTTM 结果，三说话人样本明确待补。”
- “AI 输出必须经过医生确认，系统不是临床自动诊断产品。”

## 4. 卡住时处理

| 现象 | 处理 |
| --- | --- |
| FunASR 长时间等待首段 | 说明模型冷启动，切回 Mock ASR 主线 |
| 页面显示旧 UI | 强制刷新，确认 Docker 已重新 build |
| 音频不播放 | 展示 Range 命令和截图证据，不现场调浏览器策略 |
| 角色映射待确认 | 现场选择医生/患者或说明单人样本不能伪造两人 |
| 评委问三说话人成绩 | 回答待补，不展示伪成绩 |

## 5. 收尾文件

- `docs/doctor_workbench_acceptance_v1_0.md`
- `docs/scoring/v1_0_final_freeze_checklist.md`
- `data/asr_eval/reports/v0_8_8_diarization/diarization_summary.md`
- `docs/final_report/images/v1_0_frontend_acceptance/frontend_acceptance_evidence.json`
