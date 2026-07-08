# 本地模型与边缘端评测基线报告

> 本报告用于 v0.5.8 本地 ASR 模型评测与长音频稳定性记录。当前结果只代表本机开发基线，不代表医院电脑或边缘端最终性能。

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
| ffmpeg | 可用 | 未检测到版本; source=project_portable |
| Ollama CLI | 可用 | 只检查命令是否存在，不调用服务 |

## 额外运行环境

| 报告 | Python | FunASR | Qwen-ASR | Whisper | CUDA | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| `qwen3/hardware_profile.json` | CPython 3.12.10 | 不可用 | 可用 | 不可用 | 不可用 | developer_baseline |

## 多引擎运行状态

- 运行模式：`strict`
- 评测分层：`course_medical_cn`
- 分层说明：三条课程中文医患样本，是本项目 ASR 主评测，可用于医学关键词和流程效果分析。

| 引擎 | 状态 | 报告 | 样本数 | 失败样本 | 说明 |
| --- | --- | --- | ---: | ---: | --- |
| funasr | measured | `funasr_report.csv` | 2 | 0 | completed |
| sensevoice | measured_with_warnings | `sensevoice_report.csv` | 1 | 1 | completed with skipped or failed samples |

## ASR 评测结果

| 报告 | 引擎 | 成功样本 | Smoke 样本 | 失败样本 | 平均 CER | 平均关键词召回 | 平均耗时秒 | 平均 RTF | 平均 CPU% | 标准化 CPU% | 峰值 RSS MB | 状态 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| funasr_report.csv | funasr-paraformer-zh | 2 | 0 | 0 | 0.1934 | 0.3333 | 332.0820 | 0.2447 | 310.0310 | 12.9180 | 4819.7400 | measured |
| qwen3/qwen3_report.csv | qwen3-asr-0.6b | 2 | 0 | 0 | 0.8903 | 0.0000 | 1104.7340 | 0.7326 | 973.6195 | 40.5675 | 18909.3600 | measured |
| sensevoice_report.csv | sensevoice-small | 1 | 0 | 1 | 0.1726 | 0.2667 | 168.2180 | 0.1752 | 345.1990 | 14.3830 | 2712.3600 | measured_with_failed_samples |

## 结论

- 当前机器角色：developer_baseline。
- 医院 PC 配置：pending_collection。
- 边缘端配置：pending_collection。
- 评测状态：measured。

## 后续动作

- 在普通医院 Windows 办公 PC 上运行同一组命令，补充真实基线。
- 修复 `skipped` 引擎的系统依赖、Python 包导入、模型下载或资源问题后复跑，不把环境阻塞写成模型效果差。
- 当前已实测引擎继续作为本机开发 baseline，最终选型必须等待医院 PC 或边缘端复测。
