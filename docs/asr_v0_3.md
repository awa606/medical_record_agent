# ASR V0.3: FunASR 批量转写与效果评测

## 范围

V0.3 只支持上传预录音频后的批量转写，不做实时麦克风录音和流式 ASR。原因是课程项目当前核心链路是“医患文本生成病历”，批量转写能先验证真实音频是否能稳定产出 `conversation_text`，并用 CER 和医疗关键词召回率量化质量。

V0.3 评估重点是 ASR 文本准确率和医疗关键词识别率。说话人角色只做工程后处理：双人样本使用手动 `speaker_role_map`，单人朗读脚本使用规则恢复医生/患者轮次；本阶段不承诺真实声纹级说话人分离。

## Mock ASR 与 FunASR

Mock ASR 是默认回退路径，不需要额外依赖，返回固定蛇咬伤问诊样例，适合验证 API、前端和病历生成链路。

FunASR 是真实 ASR 引擎，只有在调用 `engine=funasr` 时才导入和初始化。未安装 FunASR 时，项目仍可启动，文本病历生成与 Mock ASR 不受影响。

## 安装

基础功能：

```powershell
pip install -r requirements.txt
```

FunASR 可选依赖：

```powershell
pip install -r requirements-asr.txt
```

如果本机需要安装 CPU 版 PyTorch，可先运行：

```powershell
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

FunASR 环境诊断：

```powershell
python scripts/check_funasr_env.py
```

该脚本会输出当前 `sys.executable`、`torch` / `funasr` 是否可导入、`torch.__version__`、`torch.cuda.is_available()`，以及 `from funasr import AutoModel` 是否成功。失败时会打印完整 traceback。

## 启动

```powershell
uvicorn app.main:app --reload
```

前端入口：

```text
http://127.0.0.1:8000/static/index.html
```

## API 流程

上传音频使用 raw body，文件名放在 query 参数：

```powershell
$bytes = [System.IO.File]::ReadAllBytes("video/snakebite_01.wav")
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/upload?filename=snakebite_01.wav" -Body $bytes -ContentType "audio/wav"
```

Mock 转写：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/{audio_id}/transcribe?engine=mock"
```

FunASR 转写：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/{audio_id}/transcribe?engine=funasr"
```

预留线上 ASR 转写：

```powershell
$env:ONLINE_ASR_API_URL = "https://your-asr-provider.example/api/transcribe"
$env:ONLINE_ASR_API_KEY = "<set-in-environment-only>"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/{audio_id}/transcribe?engine=online"
```

`engine=online` 是预留线上 ASR 接口，真实平台 API 地址、鉴权方式和返回字段后续按所选平台配置。项目不会写死或提交任何 API Key；`ONLINE_ASR_API_URL` 和 `ONLINE_ASR_API_KEY` 必须由运行环境提供。当前骨架以 JSON 请求发送 `audio_id`、`filename`、`audio_base64`，并期望平台返回可映射到统一 `ASRResult` 的 JSON。

读取 transcript：

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/audio/{audio_id}/transcript"
```

将 ASR 的 `conversation_text` 接入现有病历 Agent：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/{audio_id}/generate-record"
```

该接口内部复用 `MedicalRecordOrchestrator.create_text_task()` 和 `run_existing_text_task()`，不改变现有 `/api/records/generate` 文本生成病历流程。

## ASRResult 字段

`audio_id`: 上传音频 ID。

`engine`: `mock-asr-v0.2`、`funasr-paraformer-zh` 或线上 ASR 返回的 engine 名称。

`text`: ASR 完整转写文本。

`conversation_text`: 送入病历生成 Agent 的医患对话文本。V0.3 只用 `[spk0]`、`[spk1]` 标注说话人，不保证医生/患者角色准确。

`segments`: 分段转写结果，包含 speaker、role、text、start_time、end_time、confidence。

`duration`: 音频或转写片段推断出的时长，无法获得时为 `null`。

`medical_keywords`: 包含 expected、recognized、missing。

`manifest_sample_id`、`scenario`、`speaker_mode`、`evaluate_diarization`、`role_strategy`: 来自 manifest 的样本元数据，用于说明该样本是否适合说话人分离评测，以及使用了哪种角色恢复策略。

`warnings`: ASR 后处理警告。例如 FunASR 只返回一个长 segment 时，系统不会强行套用双人 `speaker_role_map`，而会提示需要人工校正角色。

## 评测方法

CER 使用纯 Python 编辑距离实现：

```text
CER = edit_distance / reference_length
```

计算前会去除空白和常见中英文标点。`reference_length` 为归一化后的人工标注字符数。

医疗关键词识别率：

```text
keyword_recall = recognized_keywords / expected_keywords
```

关键词通过子串匹配判断是否命中，适合作为 V0.3 的轻量验收指标，不等同于医学语义理解。

评测 API：

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/audio/{audio_id}/evaluate" `
  -ContentType "application/json" `
  -Body '{"ground_truth_text":"人工标注文本","expected_keywords":["蛇咬伤","肿痛"]}'
```

## 批量评测脚本

准备目录：

```text
data/asr_eval/audio/
data/asr_eval/ground_truth/
data/asr_eval/reports/
```

音频和人工标注文本同名，例如：

```text
data/asr_eval/audio/snakebite_01.wav
data/asr_eval/ground_truth/snakebite_01.txt
```

运行：

```powershell
python scripts/evaluate_asr.py --engine mock --audio-dir data/asr_eval/audio --truth-dir data/asr_eval/ground_truth --output data/asr_eval/reports/mock_report.csv
python scripts/evaluate_asr.py --engine funasr --audio-dir data/asr_eval/audio --truth-dir data/asr_eval/ground_truth --output data/asr_eval/reports/funasr_report.csv
```

CSV 字段：

```text
filename,engine,duration,inference_time,cer,keyword_recall,recognized_keywords,missing_keywords
```

## 样本 Manifest 与角色策略

样本配置位于：

```text
data/asr_eval/manifest.json
```

每个样本包含：

```text
sample_id,scenario,speaker_mode,evaluate_diarization,role_strategy,speaker_role_map,expected_keywords
```

`snakebite_01` 是单人朗读型样本，原始文本只有“发言人1”。它只用于 ASR 文本准确率、医疗关键词识别率、字段抽取和病历生成测试，不能用于真实说话人分离评测。它的 `evaluate_diarization=false`，`role_strategy=single_speaker_script_split`，系统会用规则把单人脚本恢复成 `[医生]` / `[患者]` 的 `conversation_text`。

`chest_pain_01` 是双人问诊样本，`发言人1=医生`，`发言人2=患者`。它使用 `role_strategy=manual_speaker_role_map`。

`fever_01` 是双人问诊样本，`发言人2=医生`，`发言人1=患者`。它也使用 `role_strategy=manual_speaker_role_map`，但映射方向与 `chest_pain_01` 相反。

API 和 `scripts/evaluate_asr.py` 会按音频文件名 stem 匹配 `sample_id`。例如上传 `snakebite_01.wav` 时，会应用 `snakebite_01` 的角色策略与关键词配置。

如果 `chest_pain_01` 或 `fever_01` 的真实 ASR 结果只有一个长 segment，或者没有两个可靠 speaker label，系统会把 `role_strategy` 改为 `single_segment_needs_review`，`conversation_text` 使用 `[待校正] 原始转写文本`，并在 `warnings` 中提示人工复核。这样避免把整段内容错误映射成单一“医生”或“患者”。

## 热词

医疗热词位于：

```text
config/hotwords_medical.txt
```

FunASR 引擎会读取该文件，并在调用 `generate()` 时尝试作为 hotword 参数传入。不同 FunASR 版本对热词支持可能存在差异，若当前模型不支持，热词文件仍会用于关键词评测。

## 当前限制

V0.3 不保证真实声纹级说话人分离。`snakebite_01` 是单人朗读样本，不能用于真实说话人分离评测；`chest_pain_01` 和 `fever_01` 只使用 manifest 中的手动角色映射。

FunASR 返回 speaker 时，V0.3 只把 speaker label 映射为医生/患者，不判断声纹身份。

FunASR 只返回单段长文本时，V0.3.1 不再强行使用 manifest 的双人角色映射，需人工校正后再用于严格的医患轮次评估。

真实门诊噪声、多人插话、方言和远场录音效果需要后续单独测试。

FunASR 首次运行可能下载模型，耗时和磁盘占用取决于本地环境。

本项目不接入真实患者数据，不提供医疗器械级性能承诺。
