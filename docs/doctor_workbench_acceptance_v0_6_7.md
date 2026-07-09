# v0.6.7 医生端真实前端验收记录

本轮在 Docker `2601` 端口上补齐真实前端验收，目标是确认医生端可以完成文本导入、Mock ASR、真实 FunASR / SenseVoice、16/30 分钟长音频切片展示和完成状态验证。

## 验收环境

- 服务地址：`http://127.0.0.1:2601`
- 页面地址：`http://127.0.0.1:2601/static/doctor.html`
- Docker 端口：`2601:8000`
- 容器状态：`medical-record-agent` healthy
- 样本：
  - `video/snakebite_01.wav`
  - `data/asr_eval/long_audio_stability/audio/long_16min_course_cn.wav`
  - `data/asr_eval/long_audio_stability/audio/long_30min_course_cn.wav`

## 验收结果

| 场景 | 结果 | 关键状态 | 截图 |
| --- | --- | --- | --- |
| 文本导入生成病历 | 通过 | 生成 10 个字段卡片，进入待医生确认 | `docs/final_report/images/v0_6_7_frontend_acceptance/01_text_import_record.png` |
| Mock ASR 上传 | 通过 | SSE 分段显示，角色校正入口可见 | `docs/final_report/images/v0_6_7_frontend_acceptance/02_mock_asr_segments.png` |
| FunASR 短音频 | 通过 | `funasr-paraformer-zh · 1段`，1 段待确认 | `docs/final_report/images/v0_6_7_frontend_acceptance/03_funasr_short_real.png` |
| SenseVoice 短音频 | 通过 | `sensevoice-small · 1段`，1 段待确认 | `docs/final_report/images/v0_6_7_frontend_acceptance/04_sensevoice_short_real.png` |
| SenseVoice 16 分钟切片中 | 通过 | `第 1/4 片转写中` | `docs/final_report/images/v0_6_7_frontend_acceptance/05_long_16min_sensevoice_chunking.png` |
| SenseVoice 16 分钟完成 | 通过 | `sensevoice-small-chunked · 4段`，文本长度 4115 | `docs/final_report/images/v0_6_7_frontend_acceptance/06_long_16min_sensevoice_complete.png` |
| FunASR 30 分钟切片中 | 通过 | `第 1/6 片转写中` | `docs/final_report/images/v0_6_7_frontend_acceptance/07_long_30min_funasr_chunking.png` |
| FunASR 30 分钟完成 | 通过 | `funasr-paraformer-zh-chunked · 6段`，文本长度 7797 | `docs/final_report/images/v0_6_7_frontend_acceptance/08_long_30min_funasr_complete.png` |

## 问题记录

- Docker 首次运行 FunASR 时下载 `model.pt`，日志显示模型文件约 1.13GB，前端会停留在“转写中 0段”直到模型下载和初始化完成。
- 模型缓存完成后，FunASR 短音频复测通过。
- 该问题不是前端失败，属于首次模型准备耗时；已记录到 Debug Log：`logs/debug/2026-07-09_docker_funasr_first_load_slow.md`。

## 前端展示变化

- Docker 访问统一到 `http://127.0.0.1:2601/static/doctor.html`。
- 真实 ASR 完成后，中间栏展示模型名、进度、切片状态、分段数、文件名和校正状态。
- 长音频切片中可看到 `第 N/M 片转写中`。
- 长音频完成后可看到 `*-chunked` 引擎名和合并后的分段数。

## 验证命令

```powershell
docker compose config
docker compose up -d --build
curl http://127.0.0.1:2601/health
curl -I http://127.0.0.1:2601/static/doctor.html
node --check static\doctor.js
$env:PYTHONPATH=(Get-Location).Path; pytest -q
```
