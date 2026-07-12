# 医生端工作台 v1.0 验收记录

验收日期：2026-07-11  
验收入口：`http://127.0.0.1:2601/static/doctor.html`  
运行方式：`docker compose up -d --build medical-record-agent`  
验收样本：文本内置 fever clean、`video/snakebite_01.wav`  

## 结论

医生端 v1.0 主流程可用于终答辩演示：文本生成、Mock ASR、FunASR 短音频恢复展示、播放器、说话人统一角色映射、证据面板和正式生成入口均可见。FunASR 首次复测出现模型下载/冷启动超过 150 秒的情况，后端随后完成识别；该问题归类为真实 ASR 模型运行时耗时，不归类为前端流程失败。

## 验收项

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 服务健康检查 | 通过 | `Invoke-RestMethod http://127.0.0.1:2601/health` 返回 `ok` |
| 文本生成病历 | 通过 | `docs/final_report/images/v1_0_frontend_acceptance/02_text_generation_record.png` |
| 证据面板 | 通过 | `docs/final_report/images/v1_0_frontend_acceptance/03_evidence_panel.png` |
| Mock ASR 前端流程 | 通过 | `docs/final_report/images/v1_0_frontend_acceptance/04_mock_asr_transcript.png` |
| FunASR 短音频流程 | 通过，需预热 | 完成后恢复 session，显示 38 条转写段 |
| 播放器 Range | 通过 | `206 Partial Content`，`Content-Range: bytes 0-1023/895437` |
| 说话人统一角色映射 | 通过 | 单说话人样本要求人工映射，不伪造医生/患者两人 |
| 正式生成链路 | 通过 | 文本主链路可生成病历；音频链路在角色确认后进入生成 |

## 截图清单

- `docs/final_report/images/v1_0_frontend_acceptance/01_doctor_workbench_home.png`
- `docs/final_report/images/v1_0_frontend_acceptance/02_text_generation_record.png`
- `docs/final_report/images/v1_0_frontend_acceptance/03_evidence_panel.png`
- `docs/final_report/images/v1_0_frontend_acceptance/04_mock_asr_transcript.png`
- `docs/final_report/images/v1_0_frontend_acceptance/05_funasr_short_audio_completed.png`
- `docs/final_report/images/v1_0_frontend_acceptance/06_role_unified_correction.png`
- `docs/final_report/images/v1_0_frontend_acceptance/frontend_acceptance_evidence.json`

## 已知边界

- `snakebite_01.wav` 是单人朗读样本，只用于真实 ASR 和前端流程复测，不纳入 diarization 成绩。
- FunASR 首次冷启动或缓存补齐会显著慢于已预热状态；答辩演示应先预热模型或先走 Mock ASR 保底流程。
- 单说话人样本会提示“仅检测到一位真实说话人，不能伪造成医生和患者两人”，需要医生人工确认角色。
- 三说话人样本仍为待补，不输出三说话人成绩。

## 复测命令

```powershell
docker compose up -d --build medical-record-agent
Invoke-RestMethod http://127.0.0.1:2601/health
node --check static/doctor.js
curl.exe -s -D - -H "Range: bytes=0-1023" -o NUL "http://127.0.0.1:2601/api/audio/556c3a5bcac8476aa8b17c78dec48c90/media"
```

## Debug 记录

FunASR 首次等待超时记录见：`logs/debug/2026-07-11_funasr_frontend_cold_start_timeout.md`。
