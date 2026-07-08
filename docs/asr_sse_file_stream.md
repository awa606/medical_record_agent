# ASR SSE 文件流转写

本文说明 ASR 文件流实时转写接口。该接口不修改 ASR 引擎核心逻辑，只在 API 层新增会话、事件、长音频切片编排和前端渲染。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/asr/sessions?engine=mock|funasr|sensevoice|whisper|qwen3|online` | 创建 ASR 转写会话。 |
| `POST` | `/api/asr/sessions/{session_id}/audio` | 上传 MP3/WAV 音频，启动后台 ASR 转写；长音频可自动进入切片编排。 |
| `GET` | `/api/asr/sessions/{session_id}/events` | 订阅 `text/event-stream`，接收会话、上传、转写、切片、分段和完成事件。 |
| `GET` | `/api/asr/sessions/{session_id}/result` | 读取最终 `ASRResult`。 |

## SSE 事件

| 事件 | 说明 |
| --- | --- |
| `session_created` | 会话已创建。 |
| `audio_uploaded` | 音频已保存，返回 `audio_id` 和文件名。 |
| `transcribing` | 后端开始转写或准备推送分段。 |
| `chunk_plan` | 长音频启用切片转写时返回切片总数、切片秒数和总时长。 |
| `chunk_started` | 单个切片开始转写，包含 `chunk_index`、`total_chunks` 和 `progress`。 |
| `chunk_completed` | 单个切片完成，包含耗时、文本长度和分段数量。 |
| `chunk_failed` | 单个切片失败，包含失败原因、`retryable` 和 `retry_hint`。 |
| `segment` | 单个转写片段，包含 `role`、`speaker`、`text`、`progress` 和完整 `segment`。 |
| `completed` | 转写完成，包含最终 `asr_result`。 |
| `failed` | 转写失败，包含错误信息。 |

## 前端流程

```text
/static/doctor.html
  -> POST /api/asr/sessions
  -> POST /api/asr/sessions/{session_id}/audio
  -> EventSource(/api/asr/sessions/{session_id}/events)
  -> chunk_* 更新长音频切片状态
  -> segment 追加到中间转写栏
  -> completed 后复用 /api/audio/{audio_id}/generate-record
```

## 当前边界

- 普通短音频直接调用所选 ASR engine；长音频默认只对 `funasr`、`sensevoice` 尝试 5 分钟切片。
- 切片阈值可通过 `ASR_SESSION_CHUNK_MIN_SECONDS` 配置，默认 900 秒；切片长度可通过 `ASR_SESSION_CHUNK_SECONDS` 配置，默认 300 秒。
- 浏览器麦克风实时录音尚未实现；后续可用 MediaRecorder 分片上传或 WebSocket 扩展。
- 真正的流式解码取决于底层 ASR 引擎能力；当前实现是 API 层后台任务 + SSE 事件追踪，不改 FunASR、SenseVoice、Qwen3 或 online ASR 核心逻辑。
- 会话和运行产物默认写入 `data/uploads/`，该目录按隐私规则不提交到 Git。
