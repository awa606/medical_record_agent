# 2026-07-13 Debug：v0.9.4 SSE 复验与普通医院 PC 复测阻塞

## 背景

`v0.9.4` 主线需要在病历质量增强之外，补一轮主链路稳定性证据，优先项为：

- SSE 断连恢复复验
- 普通医院 `Windows PC` 复测状态说明

## SSE 复验方法

- 脚本：`python scripts/validate_sse_reconnect.py`
- 依赖：直接复用 `app/api/asr_sessions.py` 的 `_asr_session_event_stream`、`_append_events` 和 `Last-Event-ID` 续传逻辑，不额外改 API。

## SSE 复验结果

脚本返回：

```json
{
  "status": "passed",
  "total_events": 501,
  "expected_total_events": 501,
  "full_stream_elapsed_seconds": 0.0294,
  "resume_after_id": 451,
  "resumed_events": 50,
  "expected_resumed_events": 50,
  "first_ids_monotonic": true,
  "resumed_ids_monotonic": true,
  "resume_has_no_duplicate_boundary": true
}
```

结论：

- `Last-Event-ID` 续传链路本轮复验通过。
- 断连后恢复流没有重复边界事件。
- 事件 ID 递增单调，500 条进度事件 + 1 条完成事件回放正常。
- 当前无需再改 `app/api/asr_sessions.py` 的 SSE 事件形状。

报告文件：

- `data/asr_eval/reports/v0_8_11_sse_reconnect/sse_reconnect_report.json`

## 普通医院 PC 复测状态

本轮未完成普通医院 `Windows PC` 复测，原因不是软件失败，而是缺少真实目标环境：

- 当前工作机不是目标“普通医院办公 PC”。
- 仓库内没有该目标机器的 CPU / 内存 / 显卡 / Python / 浏览器版本记录。
- 本地无法伪造真实机器约束，因此不能把本机验证写成“医院 PC 复测已完成”。

## 当前结论

- `v0.9.4` 可以声明：SSE 断连恢复已复验通过。
- `v0.9.4` 不能声明：普通医院 PC 复测已完成。

## 下一步

- 拿到真实普通医院 `Windows PC` 后，至少记录：
  - CPU / 内存 / 是否独显
  - Python 版本
  - 浏览器版本
  - 文本导入、Mock ASR、导出阻断、详情抽屉、SSE 上传链路结果
- 如果该机器无法跑通，再单独补 `logs/debug/` 故障记录，而不是覆盖本条复验记录。
