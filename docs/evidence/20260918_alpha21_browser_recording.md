# WBS 2.1 真实浏览器录音验收证据

> 环境：MRA-ALPHA-DEV-01 / Edge / 麦克风阵列（2- Realtek(R) Audio）
> 服务：`127.0.0.1:8765`，隔离运行目录
> Provider边界：`ASR_PROVIDER=mock`，只验证录音与上传
> 结果：**PASS**

## 提交场景

| 项目 | 结果 |
|---|---|
| 匿名就诊 | `SIM-REC-20260918` |
| session_id | `4f96542a510d42e484dea83f0fb6563c` |
| audio_id | `2d1063dd3afb4eec9c6c518c569694c6` |
| 格式 | PCM WAV，单声道，48 kHz，16-bit |
| 时长 | 13.397333秒 |
| 大小 | 1,286,188 bytes |
| SHA256 | `c58c6ff5b5437a2152a2472d2cd8e10be64b42dc213bb3157611ee4333fa732c` |
| 信号检查 | PCM RMS 1720.72，非静音空文件 |
| 试听 | 浏览器媒体控件就绪，实际播放从0推进至13.397333秒 |
| 上传队列 | 已录制1块、已上传1块、待上传0块 |

## 取消场景

取消会话`99e68000c57c4d9880c11e33222056a8`曾通过真实浏览器录音上传5个分块。取消后：

- 会话状态为`cancelled`，`audio_id`和`filename`均为空。
- 只保留`recording_cancelled.json`和会话审计事件。
- 服务端录音分块目录、最终WAV和转写结果均不存在。
- 隔离数据库`agent_task`与`record_revision`为0行，没有生成业务病历任务。

## Mock边界

页面显示的蛇咬转写与草稿来自`mock-asr-v0.2`固定演示内容，与本次真实录音语句无关。这是隔离Spike的预期行为，不作为2.1失败，也不作为2.2真实转写证据。

## 数据保护

原始WAV、SQLite、session日志和界面截图仅保存在本地忽略目录`.artifacts/alpha21-real-mic-20260918_210522/`。Git只保存匿名标识、格式、时长、SHA和验收摘要。

## 自动验证

```text
pytest -q tests/test_doctor_browser_recording_static.py tests/test_browser_recording_playwright.py tests/test_asr_sessions_api.py
60 passed in 60.28s

pytest -q
512 passed, 8 subtests passed in 229.89s

node --check static/doctor.js
exit 0

/health = 200 {"status":"ok"}
/ready  = 200（隔离Mock环境；不表示真实ASR就绪）

git diff --check
exit 0
```

敏感扩展名和密钥模式扫描通过；提交范围不包含音频、SQLite、模型、密钥或身份数据。

## 验收映射

- 开始、停止、试听、提交、取消：PASS。
- 真实麦克风进入后端并取得音频标识：PASS。
- 取消不误提交任务：PASS。
- 真实ASR质量：不适用，转交WBS 2.2。
