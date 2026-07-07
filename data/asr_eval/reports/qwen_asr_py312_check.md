# Qwen-ASR 环境检查报告

> 本报告用于 v0.5.4。它只记录 Qwen-ASR 依赖和初始化状态，不评价模型效果。

## Python

| 项目 | 值 |
| --- | --- |
| 当前 Python | CPython 3.12.10 |
| 可执行文件 | python.exe |
| 执行路径 | `<PROJECT_ROOT>\.venv-qwen-asr\Scripts\python.exe` |
| 环境前缀 | `<PROJECT_ROOT>\.venv-qwen-asr` |
| Qwen 建议隔离环境 | Python 3.12 |
| 是否 Python 3.12 | 可用 |
| 是否 `.venv-qwen-asr` | 可用 |

## 依赖状态

| 依赖 | 状态 | 版本/错误 |
| --- | --- | --- |
| nagisa | 不可用 | Could not read model from <PROJECT_ROOT>\.venv-qwen-asr\Lib\site-packages\nagisa/data/nagisa_v001.model |
| qwen_asr | 不可用 | Could not read model from <PROJECT_ROOT>\.venv-qwen-asr\Lib\site-packages\nagisa/data/nagisa_v001.model |

## 初始化检查

| 项目 | 值 |
| --- | --- |
| 状态 | skipped |
| 说明 | qwen_asr import failed or package is missing |

## 建议

- 已在 `.venv-qwen-asr` Python 3.12 中复现 `nagisa_v001.model` 读取失败；下一步应定位 `nagisa/qwen-asr` 包兼容性、模型文件权限或上游包缺陷，不再把问题归因于 Python 版本。
