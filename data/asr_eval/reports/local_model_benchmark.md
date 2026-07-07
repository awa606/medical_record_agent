# 本地模型与边缘端评测基线报告

> 本报告用于 v0.5.2 评测框架验收。当前结果只代表本机开发基线，不代表医院电脑或边缘端最终性能。

## 硬件配置

| 项目 | 当前值 |
| --- | --- |
| OS | Windows 10 |
| CPU 逻辑核心 | 24 |
| 内存 | 31.43 GB |
| Python | CPython 3.11.6 |
| CUDA 可用 | 不可用 |
| GPU 数量 | 0 |

## 依赖状态

| 依赖 | 状态 | 说明 |
| --- | --- | --- |
| torch | 可用 | 2.12.1+cpu |
| FunASR | 可用 | 1.3.14 |
| Qwen-ASR | 不可用 | Could not read model from <PROJECT_ROOT>\.venv-asr\Lib\site-packages\nagisa/data/nagisa_v001.model |
| Whisper | 可用 | 20250625 |
| ffmpeg | 不可用 | 未检测到版本 |
| Ollama CLI | 可用 | 只检查命令是否存在，不调用服务 |

## 多引擎运行状态

| 引擎 | 状态 | 报告 | 样本数 | 失败样本 | 说明 |
| --- | --- | --- | ---: | ---: | --- |
| mock | measured | `mock_report.csv` | 3 | 0 | completed |
| funasr | measured | `funasr_report.csv` | 3 | 0 | completed |
| sensevoice | measured | `sensevoice_report.csv` | 3 | 0 | completed |
| whisper | skipped | - | 0 | 0 | Whisper requires a system ffmpeg executable. Install ffmpeg or choose another ASR engine. |
| qwen3 | skipped | - | 0 | 0 | Could not read model from <PROJECT_ROOT>\.venv-asr\Lib\site-packages\nagisa/data/nagisa_v001.model |

## ASR 评测结果

| 报告 | 引擎 | 成功样本 | 失败样本 | 平均 CER | 平均关键词召回 | 平均耗时秒 | 平均 RTF | 状态 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| funasr_report.csv | funasr-paraformer-zh | 3 | 0 | 0.1952 | 0.7667 | 88.1020 | 0.2605 | measured |
| mock_report.csv | mock-asr-v0.2 | 3 | 0 | 0.8786 | 0.3778 | 3.3160 | 0.1326 | measured |
| sensevoice_report.csv | sensevoice-small | 3 | 0 | 0.1669 | 0.7333 | 50.2437 | 0.1614 | measured |

## 结论

- 当前机器角色：developer_baseline。
- 医院 PC 配置：pending_collection。
- 边缘端配置：pending_collection。
- 评测状态：measured_with_skipped_optional_engines。

## 后续动作

- 在普通医院 Windows 办公 PC 上运行同一组命令，补充真实基线。
- 修复 `skipped` 引擎的系统依赖、Python 包导入、模型下载或资源问题后复跑，不把环境阻塞写成模型效果差。
- 当前已实测引擎继续作为本机开发 baseline，最终选型必须等待医院 PC 或边缘端复测。
