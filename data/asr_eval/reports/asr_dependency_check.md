# ASR 本地依赖检查报告

> 本报告用于 v0.5.3 多模型 ASR 评测。它只检查依赖和环境变量，不下载模型，不调用真实患者数据。

## Python 与 CUDA

| 项目 | 当前值 |
| --- | --- |
| Python | CPython 3.11.6 |
| Python 可执行文件 | python.exe |
| CUDA 可用 | 不可用 |
| GPU 数量 | 0 |

## 依赖状态

| 依赖 | 状态 | 版本/说明 |
| --- | --- | --- |
| torch | 可用 | 2.12.1+cpu |
| torchaudio | 可用 | 2.11.0+cpu |
| funasr | 可用 | 1.3.14 |
| sensevoice | 可用 | 1.3.14 |
| qwen_asr | 不可用 | Could not read model from <PROJECT_ROOT>\.venv-asr\Lib\site-packages\nagisa/data/nagisa_v001.model |
| whisper | 可用 | 20250625 |
| soundfile | 可用 | 0.14.0 |
| ffmpeg | 可用 | ffmpeg version 8.1.2-essentials_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers; source=project_portable |

## 模型环境变量

| 变量 | 当前值 |
| --- | --- |
| `SENSEVOICE_MODEL_ID` | FunAudioLLM/SenseVoiceSmall |
| `SENSEVOICE_DEVICE` | cpu |
| `SENSEVOICE_LANGUAGE` | zh |
| `WHISPER_MODEL` | base |
| `WHISPER_DEVICE` | cpu |
| `WHISPER_LANGUAGE` | zh |
| `QWEN3_ASR_MODEL_ID` | Qwen/Qwen3-ASR-0.6B |
| `QWEN3_ASR_DEVICE` | cpu |
| `HF_HOME_configured` | False |
| `MODELSCOPE_CACHE_configured` | False |
