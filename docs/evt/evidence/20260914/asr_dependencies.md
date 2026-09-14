# ASR 本地依赖检查报告

> 本报告用于 v0.5.3 多模型 ASR 评测。它只检查依赖和环境变量，不下载模型，不调用真实患者数据。

## Python 与 CUDA

| 项目 | 当前值 |
| --- | --- |
| Python | CPython 3.11.6 |
| Python 可执行文件 | python.exe |
| CUDA 可用 | 可用 |
| GPU 数量 | 1 |

## 依赖状态

| 依赖 | 状态 | 版本/说明 |
| --- | --- | --- |
| torch | 可用 | 2.7.0+cu128 |
| torchaudio | 不可用 | Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "C:\Program Files\Python311\Lib\importlib\__init__.py", line 126, in import_module
    return _bootstrap._gcd_import(na |
| funasr | 不可用 | - |
| sensevoice | 不可用 | SenseVoice uses funasr.AutoModel with FunAudioLLM/SenseVoiceSmall. |
| qwen_asr | 不可用 | - |
| whisper | 不可用 | - |
| soundfile | 可用 | 0.13.1 |
| ffmpeg | 不可用 | - |

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
