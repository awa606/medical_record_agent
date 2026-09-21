# WBS 3.2：双人真实 ASR 结果与本地 Qwen 草稿复验

**结论：部分通过；3.2 保持 VERIFY，V10 保持 NEEDS MORE EVIDENCE。** 两个闲置容器已停止，2626 演示容器仍运行。本轮复用此前真实 FunASR/CAM++ 输出，通过独立的本地 Ollama `qwen3:4b` 验证角色、字段、证据和草稿；**没有重新转写音频**。

## 运行边界

- Git 基线：`984f97dccf6aa30562bf00504b02d0337b437c32`；所有 WAV、完整转写、模型输出、SQLite 和日志只存于忽略的 `.artifacts/alpha32-dual-real-20260921_143838/`。原 2.3 运行证据未修改。
- 60 秒既有片段：WAV SHA256 `e0d16a3192b99ee99c74fc730facd22338cd4da2a3bb28da980d6d99375f74a4`；FunASR 结果 SHA256 `d7425b09008d846fc892c8bac9210d4122c4b71af8c25b83f65bc69a2fb9c271`。
- 完整发热双人录音：WAV SHA256 `93291c6894de5bcb7945af4f456e1ab3402fb8a78f60b5c00bfbc7185c8c414d`；既有 FunASR/CAM++ 结果 SHA256 `c3c369967b16d23f2020dc80d9e531a5d6221e42222a81b2581a95c3354db886`。0–30、0–60、0–89 秒输入均从这对已校验文件派生，未运行新 ASR。
- Provider：本地 Ollama 0.34.2、`qwen3:4b`，模型摘要 `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`。使用 `RECORD_PROVIDER_MODE=edge`、本地地址和离线缓存；Mock、云端及固定文本回退均未用于本轮草稿。
- 原 2.3 摘要中的通用输出文件名不能用来判断音频来源；本报告以原始 WAV 和转写 JSON 哈希为准。

## 实际结果

| 输入 | 角色未确认 | 人工映射后 | 本地生成 | 字段与门禁 |
|---|---|---|---|---|
| 既有 120–180 秒片段 | 409 | `passed`，pending 0，审计 1 | 草稿生成 | 3 个字段有真实片段引用；无候选方向；核心完整度 0.4，未达到可审核完整度 |
| 完整约 310 秒录音 | 409 | `passed`，pending 0，审计 1 | `FAILED` | Qwen 连续产生不符合字段 Schema 的 `physical_exam`（`missing=true`却非空）；严格模式没有替代成功结果 |
| 派生 0–89 秒 | 409 | `passed`，pending 0，审计 1 | 草稿和 2 个有来源的候选方向 | `present_illness` 引用序号/片段或字段逐句支持不成立；冲突和审核阻断保留 |
| 派生 0–60 秒 | 409 | `passed`，pending 0，审计 1 | 草稿和 2 个有来源的候选方向 | 同样有现病史证据冲突，审核阻断保留 |
| 派生 0–30 秒 | 409 | 仍为 `blocked` | 未生成 | 角色质量门禁正确拒绝，不计正例 |

0–89 秒派生音频 SHA256 `f702dc5dc8cf8835df5c2b07489eb582e00f709c25b98d98e9889a0513a8b691`，派生转写 SHA256 `0b831c6810ad4bf37ed63926ee28083f2775438cf926705fe2ebb9bc2980fb4f`。本轮没有将证据不匹配字段改为 `complete`，也没有放宽否定、主体、数值、单位或审核规则。短片段的候选方向仅供医生参考，不是自动确诊。

**唯一待修复层：本地 Qwen 对较长双人转写的字段抽取与原文证据对齐。** 长输入先失败于 Schema；较短且信息较全的输入可出草稿，但现病史不能由所引原文逐句支持。应针对这一层做限界改进并用同一输入复测；不能用 120–180 秒安全但内容不足的片段宣布 3.2 完成。既有 240 条合成安全集通过也不替代双人真实音频的完整验收。

## 容器与回归

按容器名停止 `medilisten-poc-freeze-2666`（ID 前缀 `2608a7345ead`）和 `medical-record-agent-alpha12-20260911`（`ac3a540a41ec`）；两者为 `exited`，2600/2666 无监听。保留 `medical-record-agent`（`7f1cc0b73d53`）运行在 2626；未删除镜像、卷、挂载目录或旧证据。2626 `/health` 为 200、`/ready` 为 200，但其 Provider 是 `demo/mock`，不作为本轮本地模型就绪证据。

录音、ASR、角色、字段及 API 定向回归：67 passed、4 subtests passed。完整 `pytest`：522 passed、8 subtests passed。`node --check` 和 `git diff --check` 通过。脚本 `scripts/verify_alpha32_dual_asr_loop.py` 在输入 SHA 不匹配或输出目录已存在时拒绝执行；会把完整输出写入忽略目录，stdout 仅输出匿名摘要。机器可读摘要见[同名 JSON](20260921_alpha32_real_dual_asr_replay.json)。
