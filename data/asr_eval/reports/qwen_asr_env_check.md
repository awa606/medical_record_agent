# Qwen-ASR 环境检查报告

> 本报告用于 v0.5.3。它只记录 Qwen-ASR 依赖和初始化状态，不评价模型效果。

## Python

| 项目 | 值 |
| --- | --- |
| 当前 Python | CPython 3.11.6 |
| 可执行文件 | python.exe |
| Qwen 建议隔离环境 | Python 3.12 |

## 依赖状态

| 依赖 | 状态 | 版本/错误 |
| --- | --- | --- |
| nagisa | 不可用 | Could not read model from <PROJECT_ROOT>\.venv-asr\Lib\site-packages\nagisa/data/nagisa_v001.model |
| qwen_asr | 不可用 | Could not read model from <PROJECT_ROOT>\.venv-asr\Lib\site-packages\nagisa/data/nagisa_v001.model |

## 初始化检查

| 项目 | 值 |
| --- | --- |
| 状态 | skipped |
| 说明 | qwen_asr import failed or package is missing |

## 建议

- 当前是 `nagisa_v001.model` 读取失败，重装后若仍失败，应创建 `.venv-qwen-asr` Python 3.12 隔离环境再复测。
