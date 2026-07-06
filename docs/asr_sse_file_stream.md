# ASR SSE 文件流转写

本文说明 `v0.2.1` 的文件流实时转写接口。该版本不修改 ASR 引擎核心逻辑，只在 API 层新增会话、事件和前端渲染编排。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/asr/sessions?engine=mock|funasr|qwen3|online` | 创建 ASR 转写会话。 |
| `POST` | `/api/asr/sessions/{session_id}/audio` | 上传 MP3/WAV 音频，生成可回放的 SSE segment 事件。 |
| `GET` | `/api/asr/sessions/{session_id}/events` | 订阅 `text/event-stream`，接收会话、上传、转写、分段和完成事件。 |
| `GET` | `/api/asr/sessions/{session_id}/result` | 读取最终 `ASRResult`。 |

## SSE 事件

| 事件 | 说明 |
| --- | --- |
| `session_created` | 会话已创建。 |
| `audio_uploaded` | 音频已保存，返回 `audio_id` 和文件名。 |
| `transcribing` | 后端开始转写或准备推送分段。 |
| `segment` | 单个转写片段，包含 `role`、`speaker`、`text`、`progress` 和完整 `segment`。 |
| `completed` | 转写完成，包含最终 `asr_result`。 |
| `failed` | 转写失败，包含错误信息。 |

## 前端流程

```text
/static/doctor.html
  -> POST /api/asr/sessions
  -> POST /api/asr/sessions/{session_id}/audio
  -> EventSource(/api/asr/sessions/{session_id}/events)
  -> segment 追加到中间转写栏
  -> completed 后复用 /api/audio/{audio_id}/generate-record
```

## 当前边界

- `v0.2.1` 先实现上传后文件流 POC：后端复用现有 ASR 引擎结果，按 segment 通过 SSE 推送到前端。
- 浏览器麦克风实时录音尚未实现；后续可用 MediaRecorder 分片上传或 WebSocket 扩展。
- 真正的流式解码取决于底层 ASR 引擎能力，本版本不改 FunASR、Qwen3 或 online ASR 核心逻辑。
- 会话和运行产物默认写入 `data/uploads/`，该目录按隐私规则不提交到 Git。
