# Qwen3-ASR-0.6B 本地对比引擎

## 范围

`engine=qwen3` 使用本地 Qwen3-ASR-0.6B 做预录音频批量转写，只用于和 `engine=funasr` 做 A/B 评测。FunASR 仍是 baseline，不会被替换。

当前不做实时 ASR，不接真实患者数据，不改变病历字段抽取逻辑。

## 安装依赖

Qwen3-ASR 依赖单独维护在：

```text
requirements-qwen3-asr.txt
```

安装：

```powershell
pip install -r requirements-qwen3-asr.txt
```

如果依赖未安装，调用 `engine=qwen3` 会返回：

```text
Qwen3-ASR dependencies are not installed. Please install requirements-qwen3-asr.txt
```

## 模型下载

默认模型 ID：

```text
Qwen/Qwen3-ASR-0.6B
```

首次运行时，模型包通常会从 Hugging Face 缓存下载权重。也可以提前设置本地模型目录：

```powershell
$env:QWEN3_ASR_MODEL_ID = "C:\models\Qwen3-ASR-0.6B"
```

可选运行参数：

```powershell
$env:QWEN3_ASR_DEVICE = "cpu"
$env:QWEN3_ASR_LANGUAGE = "zh"
$env:QWEN3_ASR_MAX_NEW_TOKENS = "512"
```

如果使用 GPU，可把 `QWEN3_ASR_DEVICE` 设置为 `cuda` 或具体设备映射值，取决于本机 PyTorch 和 qwen-asr 版本支持情况。

## 运行 fever_01.wav

启动服务：

```powershell
uvicorn app.main:app --reload
```

前端：

```text
http://127.0.0.1:8000/static/index.html
```

上传 `video/fever_01.wav`，在引擎下拉框选择 `Qwen3-ASR 0.6B`。

API 示例：

```powershell
$form = @{ file = Get-Item "video/fever_01.wav" }
$uploaded = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/upload" -Form $form
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/$($uploaded.audio_id)/transcribe?engine=qwen3"
```

## 和 FunASR 对比

使用同一套评估脚本分别输出 CSV：

```powershell
python scripts/evaluate_asr.py --engine funasr --audio-dir data/asr_eval/audio --truth-dir data/asr_eval/ground_truth --output data/asr_eval/reports/funasr_report.csv
python scripts/evaluate_asr.py --engine qwen3 --audio-dir data/asr_eval/audio --truth-dir data/asr_eval/ground_truth --output data/asr_eval/reports/qwen3_report.csv
```

重点比较字段：

```text
filename,engine,duration,inference_time,cer,keyword_recall,recognized_keywords,missing_keywords
```

`cer` 越低越好，`keyword_recall` 越高越好。`fever_01.wav` 可重点看发热、40 度、咳嗽、铁锈色痰、布洛芬等关键词是否召回。

## 角色分离限制

Qwen3-ASR-0.6B 当前只作为文本转写对比引擎使用，不保证稳定返回医生/患者 speaker 或 role。

当没有可靠角色时，`ASRResult.conversation_text` 输出：

```text
[待校正] 原始转写文本
```

同时加入 warning：

```text
Qwen3-ASR did not provide reliable speaker roles; please manually review roles.
```

后续用于严格医患轮次分析前，需要人工复核角色。
