# Medical Record Agent

Medical Record Agent 是一个面向医学问诊场景的 AI 生成式电子病历辅助系统课程项目。系统支持文本问诊生成病历草稿、音频上传与 ASR 转写、ASR 评测、医生审核、安全校验和导出。

本仓库同时维护工程管理结构：GitHub Issues、PR 模板、每日工作日志、调试报告和版本演进记录。当前版本已推进到 `v0.8.9`：上传音频可通过 Paraformer Streaming 按约 600ms PCM 帧持续输出，使用真实音频处理进度；转写完成后通过 VAD、标点和 CAM++ 校准时间戳与说话人，并联动音频播放器、整位说话人角色校正和实时病历预览。本轮重点修复 SSE 断连恢复、混合语句切分、短促语音误建新说话人、逐句角色误判和实时预览输入边界；三说话人样本仍为待补，不输出伪成绩。

第一次看项目时，建议先读本 README，再读 [`docs/项目文件夹阅读指南.md`](docs/项目文件夹阅读指南.md)。阅读指南按文件夹说明每个目录的用途、应该看什么、以及不同任务如何验收。

## 目录

- [项目概览：Medical Record Agent](#项目概览medical-record-agent)
- [项目文件夹阅读指南](#项目文件夹阅读指南)
- [版本演进路线：v0.1 到 v1.0](#版本演进路线v01-到-v10)
- [系统架构摘要](#系统架构摘要)
- [本地运行指南](#本地运行指南)
- [Docker 本地部署与局域网访问](#docker-本地部署与局域网访问)
- [开发工作流：Issue、开发、调试日志、提交、PR](#开发工作流issue开发调试日志提交pr)
- [主要 API](#主要-api)
- [测试](#测试)
- [数据与隐私边界](#数据与隐私边界)

## 项目概览：Medical Record Agent

项目目标是构建一个可演示、可评测、可追踪的医学 AI 助手工程样例。系统只使用模拟问诊文本、课程样例音频和 Mock/可选 ASR 引擎，不接入真实患者数据、不接入真实医院 HIS/EMR、不提交真实 API Key。

核心能力：

- ASR：MP3/WAV 上传、Mock/本地/线上 ASR 转写、CER 与关键词召回评测。
- SSE：ASR 分段转写、任务状态、步骤和调试信息的实时流式输出。
- 医学对话结构化：问诊文本到病历字段、草稿和导出结果。
- 角色分离：声学 `speaker_id` 与临床角色分开保存，支持医生声纹锁定、整位说话人统一映射和必要时一次性全局确认。
- 音频核对：播放/暂停、拖动、音量、倍速、转写行跳转，以及“尽快识别/跟随播放”两种显示节奏。
- 多说话人：CAM++ 自动声纹聚类，短促语音合并到相邻/相似说话人，避免“嗯、好”等单字独立生成第三人。
- 实时预览：稳定转写产生后更新病历字段、候选诊断、治疗方案和诊断证据；预览不创建正式任务、不能直接导出。
- 医学知识推理：候选诊断、安全校验和医生审核边界。
- 本地模型部署：FunASR、SenseVoice、Whisper、Qwen3-ASR 和 Ollama LLM provider 可选接入，并提供多引擎评测运行器。
- 医生端工作台：`/static/doctor.html`
  - 文本导入生成病历。
  - 上传 MP3/WAV 音频实时转写。
  - 上传 MP3/WAV 音频生成病历。
  - 显示转写进度、长音频切片进度、分段数量、角色校正状态和下一步操作提示。
  - 逐段校正医生/患者角色和转写文本。
  - ASR 评测：CER、keyword_recall、recognized、missing。
  - 医生审核、候选诊断、安全校验和导出。
- 开发调试台：`/static/debug.html`
  - 保留 ASRResult、Task、Steps、Safety JSON。
  - 支持文本、音频、评测和 SSE 调试。
- Agent 主链路：
  - `conversation_text -> 字段抽取 -> 病历草稿 -> 安全校验 -> 医生审核`。
- ASR 对比引擎：
  - `mock`：默认可用，用于验证工程链路。
  - `funasr`：本地真实 ASR baseline，可选依赖。
  - `sensevoice`：SenseVoice Small 本地中文/多语种候选，可选依赖。
  - `whisper`：Whisper Base 本地多语种候选，可使用项目本地便携 `ffmpeg`。
  - `qwen3`：Qwen3-ASR-0.6B 本地对比引擎，可选依赖。
  - `online`：线上 ASR 对比接口，通过环境变量配置。

## 项目文件夹阅读指南

项目文件夹、阅读顺序、系统结构图和每次任务完成后的汇报模板，见 [`docs/项目文件夹阅读指南.md`](docs/项目文件夹阅读指南.md)。

## 版本演进路线：v0.1 到 v1.0

| 版本 | 阶段 | 说明 |
| --- | --- | --- |
| v0.1 | 基础 ASR 流程 | 音频上传、ASR 转写结果结构化和病历生成入口。 |
| v0.2 | SSE 实时流式转写 | ASR 会话分段转写、任务状态、步骤和错误信息的实时流式输出。 |
| v0.3 | 医生/患者角色校正 | 医生/患者角色分离、ASR 片段策略、逐段人工校正和校正后病历生成。 |
| v0.4 | 医学知识推理 | 病历字段、草稿、安全校验和候选诊断。 |
| v0.5 | 本地模型评测 | 硬件采集、多引擎运行状态、FunASR/SenseVoice/Whisper 本机实测、公开非医疗 smoke 测试、边缘端配置建议。 |
| v0.6 | 医生端产品化与本地部署 | 优化医生工作台实时转写状态、长音频切片进度、角色校正入口、审核导出按钮和 Docker 局域网访问。 |
| v0.7 | 医生端工作台布局 | 固定三栏工作台、病历草稿槽位、AI 辅助区、标准版/关怀版和操作区。 |
| v0.8 | 流式转写、多说话人联动与评测冻结 | Paraformer 原生流式转写、真实进度、音频播放器、CAM++ 说话人校准、SSE 断连恢复、医生声纹注册、整位说话人角色映射、证据回放和实时结构化预览。 |
| v1.0 | 可部署交付系统 | 本地启动、可选本地模型、日志、版本和 PR 工作流。 |

完整版本说明见 [`docs/版本演进记录.md`](docs/版本演进记录.md)，里程碑目录见 [`versions/`](versions/)。

## 系统架构摘要

```text
static/*.html
  -> FastAPI app.main
  -> app.api routers
  -> MedicalRecordOrchestrator
  -> LLM / ASR / Export services
  -> SQLite + local runtime files
```

关键目录：

```text
medical_record_agent/
  app/                         FastAPI 后端、Agent 编排、服务、Schema、SQLite
  static/                      医生端、调试台和入口页
  docs/                        架构、版本、调试、评分和历史开发文档
  logs/                        每日日志和调试报告
  .github/                     Issue 模板和 PR 模板
  versions/                    版本归档入口
  scripts/                     数据处理、评测和诊断脚本
  tests/                       单元测试与 API 测试
  data/                        本地运行数据和样例占位目录
```

详细架构见 [`docs/architecture.md`](docs/architecture.md)，ASR 文件流说明见 [`docs/asr_sse_file_stream.md`](docs/asr_sse_file_stream.md)，角色校正说明见 [`docs/asr_role_correction.md`](docs/asr_role_correction.md)，说话人和角色路线见 [`docs/speaker_diarization_role_strategy.md`](docs/speaker_diarization_role_strategy.md)，模型路线见 [`docs/asr_model_route.md`](docs/asr_model_route.md)，医生端 v1.0 验收见 [`docs/doctor_workbench_acceptance_v1_0.md`](docs/doctor_workbench_acceptance_v1_0.md)，两说话人 RTTM 汇总见 [`data/asr_eval/reports/v0_8_8_diarization/diarization_summary.md`](data/asr_eval/reports/v0_8_8_diarization/diarization_summary.md)，终答辩冻结清单见 [`docs/scoring/v1_0_final_freeze_checklist.md`](docs/scoring/v1_0_final_freeze_checklist.md)，四周迭代计划见 [`docs/四周迭代执行计划.md`](docs/四周迭代执行计划.md)，工程规则见 [`docs/engineering_rules.md`](docs/engineering_rules.md)，能力证据见 [`docs/能力证据追踪矩阵.md`](docs/能力证据追踪矩阵.md)。

## 本地运行指南

基础环境：

```powershell
cd path\to\medical_record_agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

启动服务：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后访问：

- 入口页：http://127.0.0.1:8000/static/index.html
- 医生端：http://127.0.0.1:8000/static/doctor.html
- 调试台：http://127.0.0.1:8000/static/debug.html
- API 健康检查：http://127.0.0.1:8000/health

可选依赖：

```powershell
# FunASR
pip install -r requirements-asr.txt
python scripts/check_funasr_env.py

# v0.5.2 隔离 ASR 评测环境
py -3.11 -m venv .venv-asr
.\.venv-asr\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.venv-asr\Scripts\python -m pip install -r requirements.txt -r requirements-asr.txt -r requirements-asr-experimental.txt -r requirements-qwen3-asr.txt
.\.venv-asr\Scripts\python scripts\setup_ffmpeg_portable.py
.\.venv-asr\Scripts\python scripts\check_asr_dependencies.py

# Qwen3-ASR
pip install -r requirements-qwen3-asr.txt
```

Online ASR 只允许通过环境变量配置：

```powershell
$env:ONLINE_ASR_API_URL = "https://your-asr-provider.example/api/transcribe"
$env:ONLINE_ASR_API_KEY = "<set-in-environment-only>"
```

## Docker 本地部署与局域网访问

本项目支持 Docker Desktop 本地部署，镜像包含基础 Web 服务、SQLite、Mock ASR、FunASR 和 SenseVoice CPU 依赖。

Docker 默认对外访问端口为 `2626`，容器内部服务端口仍为 `8000`。如需更换宿主机端口，可在启动前设置 `MRA_HOST_PORT`。

构建并启动：

```powershell
docker compose up -d --build
```

如需临时使用其他端口：

```powershell
$env:MRA_HOST_PORT = "2630"
docker compose up -d --build
```

本机访问：

- 医生端：http://127.0.0.1:2626/static/doctor.html
- 健康检查：http://127.0.0.1:2626/health

局域网其他电脑访问时，先用 `ipconfig` 查看本机 IPv4，例如 `192.168.1.23`，然后访问：

```text
http://192.168.1.23:2626/static/doctor.html
```

Docker 运行数据写入 `data/docker_runtime/`，模型缓存写入 `data/asr_model_cache/`，两者均不提交 GitHub。完整说明见 [`docs/docker_local_deploy.md`](docs/docker_local_deploy.md)。

## 开发工作流：Issue、开发、调试日志、提交、PR

所有工程变更必须按以下流程执行：

1. 创建 GitHub Issue。
   - Bug 使用 `.github/ISSUE_TEMPLATE/bug.md`。
   - Feature 使用 `.github/ISSUE_TEMPLATE/feature.md`。
   - Research 和 Refactor 使用对应模板。
2. 开发或文档修改。
   - 每个功能必须对应一个 Issue。
   - 不得在无 Issue 的情况下合入新功能。
3. 记录日志。
   - 每天必须有 `/logs/daily/YYYY-MM-DD.md`。
   - 所有 Bug 必须记录在 `/logs/debug/`。
   - 调试模板见 [`logs/template.md`](logs/template.md)。
4. 提交前验证。
   - 运行 `git diff --check`。
   - 运行 `$env:PYTHONPATH = (Get-Location).Path; pytest -q`。
5. 按提交规范提交并创建 PR。
   - PR 必须关联 Issue。
   - PR 必须填写日志路径和验证命令。

提交约定：

- `feat:` new feature
- `fix:` bug fix
- `refactor:` code restructure
- `docs:` documentation update
- `test:` testing

调试规范见 [`docs/debug_guide.md`](docs/debug_guide.md)。

## 主要 API

文本病历生成：

- `POST /api/records/generate`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/steps`
- `GET /api/tasks/{task_id}/events`

音频与 ASR：

- `POST /api/asr/sessions?engine=mock|funasr|sensevoice|whisper|qwen3|online`
- `POST /api/asr/sessions/{session_id}/audio`
- `GET /api/asr/sessions/{session_id}/events`
- `GET /api/asr/sessions/{session_id}/result`
- `PATCH /api/asr/sessions/{session_id}/result`
- `POST /api/audio/upload`
- `POST /api/audio/{audio_id}/transcribe?engine=mock|funasr|sensevoice|whisper|qwen3|online`
- `GET /api/audio/{audio_id}/transcript`
- `POST /api/audio/{audio_id}/evaluate`
- `POST /api/audio/{audio_id}/generate-record`

医生审核与导出：

- `POST /api/tasks/{task_id}/review`
- `POST /api/tasks/{task_id}/approve`
- `POST /api/tasks/{task_id}/export`

## 测试

```powershell
$env:PYTHONPATH = (Get-Location).Path
pytest -q
node --check static\doctor.js
.\.venv-asr\Scripts\python scripts\run_local_asr_benchmark.py --engines mock funasr sensevoice whisper qwen3 --audio-dir video --truth-dir data/asr_eval/ground_truth --reports-dir data/asr_eval/reports
.\.venv-asr\Scripts\python scripts\prepare_public_asr_smoke_samples.py --limit 5
.\.venv-asr\Scripts\python scripts\run_local_asr_benchmark.py --engines mock funasr sensevoice whisper qwen3 --audio-dir data/asr_eval/public_smoke/audio --truth-dir data/asr_eval/public_smoke/ground_truth --reports-dir data/asr_eval/reports/public_smoke --mode smoke
```

当前测试覆盖：

- ASR factory、Mock ASR、Online ASR、FunASR、SenseVoice、Whisper、Qwen3 ASR。
- ASR role strategy。
- ASR evaluator。
- ASR session SSE API。
- ASR role correction API。
- 音频 API。
- 文本病历生成 API。
- 任务 API。
- fever 字段抽取规则。
- 数据集处理 pipeline。

## 手动验收

文本链路：

1. 打开 `/static/doctor.html`。
2. 点击“文本导入”。
3. 粘贴模拟问诊文本。
4. 点击“确认生成”。
5. 确认左栏生成病历字段，中栏显示对话转写，右栏显示病历草稿、安全校验和候选诊断。

音频链路：

1. 打开 `/static/doctor.html`。
2. 点击“上传转写”或“上传生成病历”。
3. 选择 MP3/WAV 课程样例音频。
4. 选择可用 ASR 引擎。
5. 中间转写栏会通过 SSE 追加分段结果。
6. 转写完成后可逐段校正医生/患者角色和文本。
7. 保存角色校正后再生成病历，或打开“ASR评测”查看 CER、keyword_recall、recognized、missing。

调试链路：

1. 打开 `/static/debug.html`。
2. 使用文本、音频或评测入口。
3. 打开调试详情，检查 ASRResult、Task、Steps、Safety JSON。

## 数据与隐私边界

- 不上传真实患者数据。
- 不提交真实 API Key。
- 不提交模型权重、下载数据集、运行输出和大体积音视频文件。
- `data/raw_external/`、`data/uploads/`、`data/outputs/` 等运行数据目录只保留必要占位文件。
- Toyhom/Chinese-medical-dialogue-data 等外部数据只用于课程实验，不用于真实诊疗。
- 诊断相关内容只能作为候选，必须由医生确认。

## 参考文档

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/asr_sse_file_stream.md`](docs/asr_sse_file_stream.md)
- [`docs/asr_role_correction.md`](docs/asr_role_correction.md)
- [`docs/asr_model_route.md`](docs/asr_model_route.md)
- [`docs/项目文件夹阅读指南.md`](docs/项目文件夹阅读指南.md)
- [`docs/四周迭代执行计划.md`](docs/四周迭代执行计划.md)
- [`docs/local_model_edge_benchmark.md`](docs/local_model_edge_benchmark.md)
- [`docs/engineering_rules.md`](docs/engineering_rules.md)
- [`docs/能力证据追踪矩阵.md`](docs/能力证据追踪矩阵.md)
- [`docs/版本演进记录.md`](docs/版本演进记录.md)
- [`docs/debug_guide.md`](docs/debug_guide.md)
- [`versions/`](versions/)
- [`docs/dev_logs/`](docs/dev_logs/)
- [`docs/scoring/`](docs/scoring/)
