# V0.2 三入口与 Mock ASR 流程说明

## V0.1 文本生成病历流程

输入：医患对话文本 `conversation_text`。

输出：病历生成任务 `task_id`、结构化字段、病历草稿、安全校验结果、步骤日志。

API：

- `POST /api/records/generate`：创建文本病历生成任务。
- `GET /api/tasks/{task_id}`：读取任务与结果。
- `GET /api/tasks/{task_id}/steps`：读取字段抽取、草稿生成、安全校验步骤。
- `GET /api/tasks/{task_id}/events`：通过 SSE 监听任务状态。

数据库表：

- `agent_task`：记录任务输入、状态、阶段、结果 JSON、错误和重试次数。
- `agent_task_step`：记录每个 Agent 步骤的输入快照、输出快照、状态和耗时。
- `audit_log`：记录任务创建、状态变化、重试、降级等审计事件。

调用关系：

```text
conversation_text -> /api/records/generate -> MedicalRecordOrchestrator
MedicalRecordOrchestrator -> MockLLM.extract_fields
MedicalRecordOrchestrator -> MockLLM.generate_draft
MedicalRecordOrchestrator -> MockLLM.safety_check
MedicalRecordOrchestrator -> agent_task / agent_task_step / audit_log
```

## V0.2 三入口流程

### 1. 从文本生成病历

输入：页面文本框中的 `conversation_text`。

输出：`task_id`，并通过 SSE 展示任务进度和最终草稿。

调用关系：

```text
页面文本 -> POST /api/records/generate -> task_id
task_id -> GET /api/tasks/{task_id}/events -> 进度
task_id -> GET /api/tasks/{task_id} + /steps -> 结果展示
```

### 2. 上传预录音频测试转写

输入：预录 wav/mp3 音频文件。

输出：Mock ASR 的 `ASRResult`，包括 `engine`、`text`、`conversation_text`、`segments`、`medical_keywords`。

调用关系：

```text
audio file -> POST /api/audio/upload -> audio_id
audio_id -> POST /api/audio/{audio_id}/transcribe -> ASRResult
audio_id -> GET /api/audio/{audio_id}/transcript -> ASRResult
```

该入口只测试转写，不自动创建病历任务。

### 3. 上传预录音频生成病历

输入：预录 wav/mp3 音频文件。

输出：先展示 Mock ASR 结果，再使用 `conversation_text` 创建病历生成任务。

调用关系：

```text
audio file -> POST /api/audio/upload -> audio_id
audio_id -> POST /api/audio/{audio_id}/transcribe -> ASRResult
ASRResult.conversation_text -> POST /api/audio/{audio_id}/generate-record -> task_id
task_id -> GET /api/tasks/{task_id}/events -> 进度
task_id -> GET /api/tasks/{task_id} + /steps -> 结果展示
```

## 节点输入输出

```text
上传音频：audio file -> audio_id
Mock ASR：audio_id -> ASRResult
文本生成：conversation_text -> task_id
字段抽取：conversation_text -> MedicalRecordFields
草稿生成：MedicalRecordFields -> draft
安全校验：fields + draft -> SafetyCheckResult
```

## ASRResult 字段

- `text`：完整纯文本转写。
- `conversation_text`：带 `[医生]`、`[患者]` 标记的医患对话文本，可直接进入现有病历生成链路。
- `segments`：预留 speaker、role、时间戳和 confidence，便于后续接真实 ASR。
- `medical_keywords`：展示预期关键词、命中关键词和缺失关键词。

## 后续真实 ASR 接入位置

当前 `app/services/asr/mock_engine.py` 是 V0.2 的 Mock ASR。后续接 FunASR 时，应在 `app/services/asr/` 下新增真实引擎实现，并保持输出仍为 `ASRResult`。

真实 ASR 只替换音频到 `conversation_text` 的部分，不应改变现有 `MedicalRecordOrchestrator`、`/api/records/generate`、任务表、步骤表和审计日志的主链路。
