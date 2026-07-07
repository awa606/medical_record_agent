# Qwen-ASR 环境检查报告

> 本报告用于 v0.5.5。它只记录 Qwen-ASR 依赖、路径和初始化状态，不评价模型效果。

## Python

| 项目 | 值 |
| --- | --- |
| 当前 Python | CPython 3.12.10 |
| 可执行文件 | python.exe |
| 执行路径 | `C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe` |
| 环境前缀 | `C:\mra_qwen_runtime\.venv-qwen-asr` |
| Qwen 建议隔离环境 | Python 3.12 |
| 是否 Python 3.12 | 可用 |
| 是否 `.venv-qwen-asr` | 可用 |
| 路径是否含非 ASCII 字符 | 否 |
| ASCII 运行区 | `C:\mra_qwen_runtime` |

## 依赖状态

| 依赖 | 状态 | 版本/错误 |
| --- | --- | --- |
| nagisa | 可用 | 0.2.11 |
| qwen_asr | 可用 | - |

## 初始化检查

| 项目 | 值 |
| --- | --- |
| 状态 | import_ok |
| 说明 | Qwen3ASRModel import ok; model loading not attempted for Qwen/Qwen3-ASR-0.6B |

## 建议

- Qwen-ASR 基础导入已通过，可进入模型下载和真实转写复测。
