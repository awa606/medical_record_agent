# v0.1 Basic ASR Pipeline

## 目标

建立基础 ASR 链路，验证音频上传、转写结果结构化和后续病历生成入口。

GitHub Issue：[#1](https://github.com/awa606/medical_record_agent/issues/1)

## 验收证据

- API：`POST /api/audio/upload`
- API：`POST /api/audio/{audio_id}/transcribe`
- Schema：`ASRResult`、`ASRSegment`
- 测试：`tests/test_asr_mock.py`、`tests/test_audio_api.py`

## 状态

已具备 Mock ASR 和可选真实 ASR 引擎接入能力。
