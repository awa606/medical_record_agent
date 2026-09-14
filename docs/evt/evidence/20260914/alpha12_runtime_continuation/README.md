# Alpha 1.2 本地运行环境续验记录

本记录对应 `MRA-ALPHA-1.2`，用于证明当前分支在开发机上可以重新构建隔离容器，并由真实本地 FunASR 与 Ollama 提供运行就绪状态。结果仍为 **PARTIAL**，不能替代 Jetson 目标环境验收。

## 本次结果

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 当前源码 | PASS | `codex/alpha-local-closed-loop-safety@403dc6121a27bbf38e0e2ffd24d447b7bb39f952` |
| 当前镜像构建 | PASS | `medical-record-agent:closed-loop`，镜像摘要见 [`results.json`](results.json) |
| 服务健康 | PASS | `/health` 返回 HTTP 200 |
| 运行就绪 | PASS | `/ready` 返回 HTTP 200；SQLite、运行目录、Provider 和 ASR 均通过 |
| 本地 LLM | PASS | Ollama `qwen3:4b` 实际探测成功，模型摘要已记录，Mock 回退关闭 |
| 本地 ASR | PASS（upload profile） | Paraformer、VAD、标点和 CAM++ 四组件从本地缓存完成预热 |
| 医生页面 | PASS | `/static/doctor.html` 返回 HTTP 200 |
| 状态语义 | PASS | 严格 `edge` 模式的 `fallback_provider` 修正为 `null`，23项相关测试通过 |

## 复现命令

私有运行目录、模型缓存目录和测试密码必须由执行者在本地提供，不得写入仓库。

```powershell
$env:MRA_LOOP_RUNTIME = 'C:/private/mra-alpha12/runtime'
$env:MRA_ASR_CACHE = 'C:/private/mra-asr-cache'
$env:MRA_OLLAMA_MODELS = "$env:USERPROFILE/.ollama/models"
$env:MRA_LOOP_ADMIN_PASSWORD = Read-Host '输入本次隔离测试密码' -MaskInput
$env:MRA_LOOP_PORT = '2782'

docker compose -p mra-alpha12-current -f compose.local-loop.yml build app
docker compose -p mra-alpha12-current -f compose.local-loop.yml up -d --pull never
curl.exe http://127.0.0.1:2782/health
curl.exe http://127.0.0.1:2782/ready
curl.exe -X POST http://127.0.0.1:2782/api/llm/test
```

相关回归测试：

```powershell
python -m pytest -q `
  tests/test_llm_status_api.py `
  tests/test_runtime_hardening.py `
  tests/test_llm_adapter.py `
  --basetemp=.artifacts/test-tmp/alpha12-status-fix-20260914
```

## 修复的问题

`get_llm_status()`此前在严格 `live/edge` 模式仍返回 `fallback_provider: mock`，虽然同时声明 `fallback_allowed: false`。运行状态对使用者产生矛盾信息。本次把严格模式的候选回退明确设为 `null`，并增加 `live` 与 `edge` 回归断言。Provider选择、生成流程和安全门禁没有改变。

## 尚未证明

- Jetson ARM/CUDA 目标环境能够启动当前镜像。
- 8GB共享内存下同时运行目标模型的峰值与稳定性。
- 实时麦克风链路所需的五组件 streaming profile 已在目标设备通过。
- 目标设备上的持续运行、温度、降频和重启恢复。

因此任务继续保持 `IN PROGRESS`。本轮开发机结果只补充现有1.2证据，不把任务移入 `VERIFY` 或 `DONE`。

## 机器可读证据

[`results.json`](results.json)记录了采样时间、分支、提交、工作树状态、Docker版本、镜像摘要、端点结果、测试命令、文件SHA-256和未验证项。文件不包含管理员密码、原始病历、身份数据、音频或模型权重。
