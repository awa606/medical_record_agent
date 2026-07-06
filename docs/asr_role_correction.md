# v0.3 医生/患者角色校正

本文说明 `v0.3` 的角色校正闭环。该版本不替换 ASR 模型，只在 ASR 会话结果层增加人工校正、保存和后续病历生成衔接。

## 目标

- 每条转写 segment 显示角色、文本、置信度和校正状态。
- 医生可把 segment 标记为 `医生`、`患者` 或 `待确认`。
- 医生可直接修改单条转写文本。
- 保存后重建 `conversation_text`，后续病历生成使用校正后的内容。
- 单段长文本、缺少角色或待确认角色必须标记为 `needs_review`。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `PATCH` | `/api/asr/sessions/{session_id}/result` | 保存角色和文本校正，返回更新后的 `ASRResult`。 |
| `GET` | `/api/asr/sessions/{session_id}/result` | 读取最终或已校正的 `ASRResult`。 |
| `POST` | `/api/audio/{audio_id}/generate-record` | 兼容旧流程，从已校正 transcript 生成病历任务。 |

## 数据规则

- `ASRSegment.role` 使用 `医生`、`患者`、`待确认`。
- `ASRSegment.reviewed_by_doctor` 表示该 segment 已由医生确认。
- `ASRSegment.needs_review` 表示该 segment 仍需人工复核。
- `ASRResult.reviewed_by_doctor` 仅当所有 segment 都被确认时为 `true`。
- `ASRResult.needs_review` 只要存在待确认 segment 就为 `true`。

## 前端流程

```text
SSE segment 显示
  -> 医生切换角色 / 编辑文本
  -> 点击保存角色校正
  -> PATCH /api/asr/sessions/{session_id}/result
  -> 后端重建 conversation_text
  -> 生成病历使用校正后的 transcript
```

## 验收标准

- 上传 MP3/WAV 后，中间栏能显示分段转写。
- 每段能切换 `医生 / 患者 / 待确认`。
- 每段文本可编辑。
- 保存后重新读取 result，角色和文本保持一致。
- 使用 `/api/audio/{audio_id}/generate-record` 时，病历生成输入为校正后的 `conversation_text`。
