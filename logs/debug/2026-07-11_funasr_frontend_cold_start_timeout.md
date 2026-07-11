# 2026-07-11 FunASR 前端复测冷启动超时记录

## 现象

- 复测入口：`http://127.0.0.1:2601/static/doctor.html`
- 复测样本：`video/snakebite_01.wav`
- 复测路径：医生端音频生成，ASR Engine 选择 `FunASR`。
- 自动化等待 150 秒内没有在前端收到首条 `.transcript-table-row`，截图脚本超时退出。

## 排查

- Docker 服务健康检查通过：`Invoke-RestMethod http://127.0.0.1:2601/health` 返回 `ok`。
- 容器日志显示 FunASR 正在执行模型检查和下载：
  - `iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch`
  - `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch`
  - `iic/punc_ct-transformer_cn-en-common-vocab471067-large`
- 未发现医生端 JavaScript 语法错误或页面加载失败。
- 后端最终完成会话：`data/docker_runtime/uploads/asr_sessions/05371ae9a2334b8188c0b3874fe46544/result.json`。

## 结论

本次超时归类为真实 ASR 模型冷启动/依赖下载耗时问题，不归类为前端流程失败。模型完成初始化后，使用同一 session 恢复页面，医生端可显示 38 条转写段、音频播放器和说话人统一角色映射抽屉。

## 验证

- `docs/final_report/images/v1_0_frontend_acceptance/05_funasr_short_audio_completed.png`
- `docs/final_report/images/v1_0_frontend_acceptance/06_role_unified_correction.png`
- `curl.exe -H "Range: bytes=0-1023" http://127.0.0.1:2601/api/audio/556c3a5bcac8476aa8b17c78dec48c90/media` 返回 `206 Partial Content`。

## 边界

`snakebite_01.wav` 是单人朗读样本，本次只用于真实 ASR 前端流程复测，不纳入 diarization 成绩。三说话人样本仍为待补，不输出伪三说话人成绩。
