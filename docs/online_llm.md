# Online / Ollama LLM 接入说明

## 范围

LLM 负责把问诊文本转换为病历字段、病历草稿和安全校验。当前第一阶段只让真实 LLM 做字段抽取，草稿生成和安全校验继续走稳定的 MockLLM 逻辑，确保 `fever_01.wav` 演示链路可复现。

ASR 和 LLM 是两套不同能力：

- ASR：音频转文字，配置 `ONLINE_ASR_API_URL` / `ONLINE_ASR_API_KEY`。
- LLM：文本理解和字段抽取，配置 `LLM_PROVIDER` / `ONLINE_LLM_*` / `OLLAMA_*`。

如果你配置的是 DeepSeek 或其他 OpenAI-compatible 大模型，应设置 `LLM_PROVIDER=online`，但音频上传页面的 ASR 引擎仍应选择 `FunASR` 或 `Mock ASR`，不要误选 `Online ASR`。

## 环境变量

默认：

```powershell
$env:LLM_PROVIDER = "mock"
```

OpenAI-compatible / DeepSeek 类接口：

```powershell
$env:LLM_PROVIDER = "online"
$env:ONLINE_LLM_API_BASE = "https://your-openai-compatible-endpoint.example"
$env:ONLINE_LLM_API_KEY = "<never-commit-real-key>"
$env:ONLINE_LLM_MODEL = "your-model"
```

Ollama：

```powershell
$env:LLM_PROVIDER = "ollama"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "your-local-model"
```

可选：

```powershell
$env:LLM_TIMEOUT_SECONDS = "30"
$env:LLM_MAX_RETRIES = "2"
```

不要提交真实 API Key，不要把 Key 写入 README、日志、截图或 GitHub。

## 状态与自检

查看配置状态，不调用外部模型：

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/llm/status"
```

返回字段：

```json
{
  "provider": "online",
  "model": "deepseek-chat",
  "configured": true,
  "reachable": false,
  "checked": false,
  "fallback_provider": "mock",
  "fallback": false,
  "fallback_reason": "Reachability not checked. Use POST /api/llm/test."
}
```

执行连接自检，会调用 provider 并检查返回是否可解析为 JSON：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/llm/test"
```

接口不会返回 API Key。若 provider 不可用、超时、JSON 无效或字段不完整，系统运行时仍会 fallback 到 MockLLM。

## 页面提示

`doctor.html` 和 `debug.html` 顶部会分开显示：

- ASR Engine
- LLM Provider
- LLM Model
- LLM Fallback

点击“LLM自检”可以测试在线 LLM 或 Ollama 是否可用。该按钮与音频转写下拉框无关。
