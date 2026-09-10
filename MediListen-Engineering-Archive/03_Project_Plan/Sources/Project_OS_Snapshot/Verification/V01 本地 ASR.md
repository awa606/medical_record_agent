---
type: verification
project: medical-record-agent
phase: Alpha
verification_id: V01
requirement: 本地 ASR
related_wbs:
- '1.3'
- '2.2'
method: 真实录音本地 Provider 运行与结果核对
expected_result: 真实音频生成同一 audio_id 的 ASRResult，记录模型/Provider/日志，Mock 和云端结果不得替代正式证据。
actual_result: null
status: NOT TESTED
evidence: []
owner: 李国毅
acceptance:
- 预下载并固定ASR和LLM模型版本
- 断网后模型仍可加载，记录实际Provider和模型位置
- 正式证据不得依赖Mock、云端调用或未披露的fallback
- 至少一次经2.1提交的真实录音由本地Provider转写成功
- 保存输入标识、结果和日志，能够对应同一音频
- Mock结果不得计为正式转写通过
---

# V01 本地 ASR

```dataviewjs
await dv.view("00_Home/project-os", {"project": "medical-record-agent", "phase": "Alpha", "section": "verification-item"});
```

只有本次有效实际结果和可访问证据同时具备才使用 PASS。前提缺失时使用 BLOCKED 并在 actual_result 写明原因。
