# v0.8.9 说话人角色与 SSE 稳定性验证摘要

## Scope

本报告记录 `v0.8.6-v0.8.9` 的轻量验证结果，重点覆盖：

- SSE 追加式事件日志与断线恢复。
- 临时识别窗口和稳定 utterance 分离。
- 短促语音合并，减少第三说话人误生成。
- 整位说话人角色映射。
- 稳定 utterance 驱动实时病历预览。

## Automated Checks

| 检查 | 结果 |
| --- | --- |
| `node --check static/doctor.js` | passed |
| 说话人/SSE/预览定向 pytest | 33 passed |
| diarization 脚本 py_compile | passed |

## Real Session Evidence

Docker `2601` 中曾使用 `fever_01.wav` 完成真实 FunASR 会话复测。该会话确认：

- SSE 事件 ID 单调递增。
- `Last-Event-ID` 恢复可跳过已发送事件。
- 未出现 `failed` 事件。
- 旧策略会产生大量短句和角色污染；v0.8.9 后稳定列表只消费边界确认后的 utterance。

本报告不提交音频、运行数据库、模型缓存或原始患者数据。

## Boundary

- 当前结论只代表课程样本和本机/Docker 2601 开发环境。
- `fever_01` 和 `chest_pain_01` 是两说话人评测；三说话人仍为待补。
- pyannote/3D-Speaker 为候选路线，依赖未完成前不比较模型效果。
