# 本地模型与边缘端评测基线报告

> 本报告用于 v0.5.0 评测框架验收。当前结果只代表本机开发基线，不代表医院电脑或边缘端最终性能。

## 硬件配置

| 项目 | 当前值 |
| --- | --- |
| OS | Windows 11 |
| CPU 逻辑核心 | 24 |
| 内存 | 31.43 GB |
| Python | CPython 3.13.5 |
| CUDA 可用 | 可用 |
| GPU 数量 | 1 |

## 依赖状态

| 依赖 | 状态 | 说明 |
| --- | --- | --- |
| torch | 可用 | 2.10.0 |
| FunASR | 不可用 | 未检测到版本 |
| Qwen-ASR | 不可用 | 未检测到版本 |
| Ollama CLI | 可用 | 只检查命令是否存在，不调用服务 |

## ASR 评测结果

| 报告 | 引擎 | 样本数 | 平均 CER | 平均关键词召回 | 平均耗时秒 | 状态 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| mock_report.csv | mock-asr-v0.2 | 1 | 0.9685 | 0.0000 | 0.0010 | measured |

## 结论

- 当前机器角色：developer_baseline。
- 医院 PC 配置：pending_collection。
- 边缘端配置：pending_collection。
- 评测状态：mock_measured_real_asr_dependency_missing。

## 后续动作

- 在普通医院 Windows 办公 PC 上运行同一组命令，补充真实基线。
- 安装 FunASR 或 Qwen3-ASR 后复跑对应引擎，不把依赖缺失写成模型效果差。
- 进入 v0.5.1 后再比较 SenseVoice、Whisper 或多说话人分离路线。
