# 2026-07-11 Debug：说话人角色混淆与 SSE 断连稳定性

## Problem

用户反馈真实音频转写中出现两个问题：

- 一条转写行同时包含医生和患者句子，导致角色标注互相污染。
- SSE 前端显示连接异常，只显示少量段落，后台仍在继续处理。

## Root Cause

- 早期流式窗口按固定时间切段，不等于说话人边界。
- 文本规则逐句判断角色，短句“嗯、我、没有”权重过高，容易把所有说话人判成患者。
- 短促语音会被 CAM++ 聚成临时第三人。
- SSE 事件回放存在逐事件人工延迟，首次断连后前端直接标记失败。

## Fix

- Paraformer Streaming 原始窗口只保留为 provisional 状态，不进入正式病历预览。
- 正式转写列表只消费 VAD/说话人边界确认后的稳定 utterance。
- 短于 1 秒或累计有效语音不足 3 秒的声纹簇不直接成为主要说话人，优先合并到相邻或最相似说话人。
- 角色从逐句判断改为整位说话人统一映射。
- SSE 改为追加式事件日志，支持 keepalive 和 `Last-Event-ID` 恢复，不再逐事件等待 220ms。
- 前端断连后允许 EventSource 自动重连，不把第一次网络抖动标为任务失败。

## Verification

- 定向测试：`33 passed`
  - `tests/test_asr_sessions_api.py`
  - `tests/test_funasr_streaming_engine.py`
  - `tests/test_records_api.py`
  - `tests/test_speaker_diarization.py`
  - `tests/test_speaker_profiles.py`
  - `tests/test_speaker_role_classifier.py`
  - `tests/test_diarization_evaluator.py`
  - `tests/test_summarize_diarization_results.py`
- `node --check static/doctor.js`：通过。
- `python -m py_compile scripts/check_diarization_dependencies.py scripts/evaluate_diarization.py scripts/summarize_diarization_results.py`：通过。

## Remaining Risk

- 三说话人真实样本仍缺人工 RTTM，不能输出三说话人成绩。
- pyannote 和 3D-Speaker 当前只完成依赖检测入口，没有完成本机实测。
- Ollama 角色兜底为可选路线；若本机未安装模型，仍会进入一次全局映射确认。
