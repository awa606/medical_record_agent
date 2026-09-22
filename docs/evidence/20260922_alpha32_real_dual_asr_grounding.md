# WBS 3.2：真实双人 ASR 的本地 Qwen 字段落地闭环

**结论：3.2 的 Alpha 验收证据已完成，V10 Alpha Semantic Safety 可判定 PASS。** 这只证明本地模型在一份真实双人 FunASR 结果上形成安全、可追踪、待医生审核的病历草稿；不证明临床有效性、正式冻结集准确率或企业发布安全性。

## 修复边界

- 真实运行代码 SHA：`7f6cf2db08653fbfdbf9992fdef903b21ee4b924`；最终交付代码 SHA：`5088ec4b6b6c71eacb8eaedfa6f1d091bd9f438f`。后者只补充归一化字段的 `missing/status` 一致性，并再次通过同一组73项定向测试。
- 保持现有 Ollama、Qwen、业务 API、角色阈值和数据库结构；没有新增模型或云端回退。
- Ollama 传输层只验证 JSON 载荷形状；完整字段一致性由 `LLMRecordGenerator` 统一处理，避免传输层在安全归一化之前拒绝可安全降级的输出。
- 模型选择的引用只有在唯一匹配已审核音频片段且角色允许时才进入字段。模型改写被替换成原始转写原句；医生提问、重复短词和无法定位内容被移除。
- 一个字段没有任何可信患者引用时，字段明确标记为 `missing` 并提示医生补录，不把模型改写保存为患者事实。
- 本轮复用既有真实 FunASR/CAM++ 输出，没有重新转写音频。完整音频、转写、模型输出、SQLite 和日志均留在 Git 忽略的 `.artifacts/`。

## 可重算输入

| 输入 | SHA256 |
|---|---|
| 完整约 310 秒 WAV | `93291c6894de5bcb7945af4f456e1ab3402fb8a78f60b5c00bfbc7185c8c414d` |
| 完整 FunASR/CAM++ JSON | `c3c369967b16d23f2020dc80d9e531a5d6221e42222a81b2581a95c3354db886` |
| 0–89 秒派生 WAV | `f702dc5dc8cf8835df5c2b07489eb582e00f709c25b98d98e9889a0513a8b691` |
| 0–89 秒派生转写 | `0b831c6810ad4bf37ed63926ee28083f2775438cf926705fe2ebb9bc2980fb4f` |

Provider 为本地 Ollama `0.34.2`、`qwen3:4b`，模型摘要 `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`。运行模式禁止 Mock、云端和固定文本回退。

## 真实结果

| 输入 | 角色门禁 | 草稿 | 字段证据与安全结果 |
|---|---|---|---|
| 完整约 310 秒 | 未确认时 409；人工映射后 `passed`、pending 0、审计 1 | 本地 Qwen 生成，状态 `WAITING_DOCTOR_REVIEW` | 4 个完整字段、1 个部分字段、3 个缺失字段；无证据字段未进入患者事实；`safety_blocked=false` |
| 0–89 秒片段 | 未确认时 409；人工映射后 `passed`、pending 0、审计 1 | 本地 Qwen 生成，状态 `WAITING_DOCTOR_REVIEW` | 主诉和既往处理完整，现病史及伴随症状保留可信原句并标记部分完成；`safety_blocked=false` |

两个输入均产生2个带患者事实和知识引用的候选方向，且保持待医生确认；没有自动确诊、治疗或处方。完整运行的私有任务和追踪输出 SHA256 分别为 `2dbd6785f0ed47ea84b3485277b33e01ffa3e3abb55680a17d183987f420d324` 与 `06d12477fad74e769a7a2880ec9e4ff55b19b579d84a0c0c2aa0a92a34427bdb`。

## 验证

- 临床事实、引用归一化、Ollama 传输和 fail-closed 定向测试：73 passed。
- 完整测试：527 passed。
- `node --check static/doctor.js`、`git diff --check`：PASS。
- 独立 Uvicorn `/health` 与 `/ready` smoke：PASS。
- 本轮差异没有新增音频、数据库、模型、密钥或身份数据。

本结论关闭的是3.2第一项“至少一份通过角色门禁的真实ASR结果完成字段、证据和草稿生成”。T09、V01、Issue #41的大样本性能与正式临床语义验证均不因本结果改变。机器可读结果见[同名 JSON](20260922_alpha32_real_dual_asr_grounding.json)。
