# Online ASR 对比验证

## 范围

Online ASR 只作为对比引擎接入，不替换 FunASR，也不改变病历 Agent 主流程。当前项目仍只支持上传预录音频后的批量转写，不做实时 ASR，不接真实患者数据。

## ASR 与 LLM 的区别

- ASR 负责“音频 -> 文字”，例如 FunASR、Mock ASR、Qwen3-ASR、Online ASR。
- LLM 负责“文字 -> 病历字段/草稿/安全校验”，例如 MockLLM、Online LLM、Ollama LLM。
- `Online ASR` 和 `Online LLM` 是两套不同配置，互不替代。

如果只是测试 DeepSeek 或其他在线大模型，请不要在音频转写下拉框选择 `Online ASR`；请使用文本导入，或将 ASR 选择为 `FunASR` 后上传生成病历，再通过 LLM 状态/自检查看 `LLM_PROVIDER=online` 是否配置成功。

## 环境变量

不要把任何真实 API Key 写入代码、文档或测试文件。运行前在本机环境中设置：

```powershell
$env:ONLINE_ASR_API_URL = "https://your-asr-provider.example/api/transcribe"
$env:ONLINE_ASR_API_KEY = "<your-runtime-api-key>"
```

`ONLINE_ASR_API_URL` 是线上 ASR 的 HTTP JSON 接口地址。`ONLINE_ASR_API_KEY` 会以 `Authorization: Bearer <key>` 请求头发送。

如果任一变量缺失，`engine=online` 会返回清晰错误，提示缺少 `ONLINE_ASR_API_URL` 或 `ONLINE_ASR_API_KEY`。

这些变量只用于在线语音识别。DeepSeek/OpenAI-compatible 大模型配置使用 `ONLINE_LLM_*`，详见 `docs/online_llm.md`。

## fever_01.wav 测试

启动服务：

```powershell
uvicorn app.main:app --reload
```

在前端打开：

```text
http://127.0.0.1:8000/static/index.html
```

上传 `video/fever_01.wav`，在“上传预录音频测试转写”或“上传预录音频生成病历”的引擎下拉框选择 `Online ASR`。

也可以用 API：

```powershell
$form = @{ file = Get-Item "video/fever_01.wav" }
$uploaded = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/upload" -Form $form
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/$($uploaded.audio_id)/transcribe?engine=online"
```

## 返回格式适配

线上接口请求体为 JSON：

```json
{
  "audio_id": "sample-id",
  "filename": "fever_01.wav",
  "audio_base64": "..."
}
```

项目会通过 `normalize_online_asr_response(data) -> ASRResult` 适配常见返回字段，例如 `text`、`transcript`、`segments`、`utterances`、`sentences`、`medical_keywords`、`keywords`。适配后统一写入 `ASRResult`，供现有评估和病历生成入口复用。

## 和 FunASR 对比

批量计算 CER 和 keyword_recall：

```powershell
python scripts/evaluate_asr.py --engine funasr --audio-dir data/asr_eval/audio --truth-dir data/asr_eval/ground_truth --output data/asr_eval/reports/funasr_report.csv
python scripts/evaluate_asr.py --engine online --audio-dir data/asr_eval/audio --truth-dir data/asr_eval/ground_truth --output data/asr_eval/reports/online_report.csv
```

对比 `funasr_report.csv` 和 `online_report.csv` 中的：

```text
filename,engine,duration,inference_time,cer,keyword_recall,recognized_keywords,missing_keywords
```

`fever_01.wav` 当前 FunASR 关键词可做到 `missing=[]`，但如果只返回单段长文本，角色会被标记为 `single_segment_needs_review`。Online ASR 的价值是对比文本准确率、关键词召回和是否能返回更可用的说话人分段。
