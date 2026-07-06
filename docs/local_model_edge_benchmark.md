# 本地模型与边缘端评测方案

本文用于第3周“能稳”阶段，目标是在普通医院电脑基线下评测 ASR/LLM 本地运行效果，并给出边缘端配置建议。

## 硬件基线

| 档位 | 建议配置 | 用途 |
| --- | --- | --- |
| 普通医院 PC | Windows 10/11，4-8 核 CPU，16 GB 内存，CPU-only 或集显 | 最低可用基线，验证离线转写和病历生成是否可接受。 |
| 独显工作站 | Windows/Linux，8-16 核 CPU，32 GB 内存，8-12 GB VRAM | 对比本地 ASR/LLM 加速收益。 |
| 边缘端 | 小型工控机或边缘 GPU/NPU 设备，16-32 GB 内存 | 验证门诊边缘部署、离线运行和隐私隔离可行性。 |

## 模型矩阵

| 类型 | 候选 | 评测指标 |
| --- | --- | --- |
| ASR | `mock`、FunASR、Qwen3-ASR、online baseline | CER、关键词召回、单段延迟、总耗时、CPU/内存/GPU 占用。 |
| LLM | `mock`、Ollama 本地模型、online baseline | 字段完整率、候选诊断合理性、生成耗时、资源占用。 |
| 知识库 | 规则模板、症状-疾病关联、检查/用药提示 | 命中率、误触发、医生复核成本。 |

## 记录表

| 样本 | 模型 | 硬件 | 输入时长 | 总耗时 | CER | 关键词召回 | 峰值内存 | GPU/CPU 占用 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 验收标准

- 至少完成 `mock` 与一个真实本地 ASR 引擎对比。
- 至少记录一台普通医院 PC 基线配置。
- 每条结论必须有测试命令、样本名称和数据表支撑。
- 不提交真实患者音频、模型权重、API Key 或大体积评测产物。

## 推荐命令

```powershell
$env:PYTHONPATH = (Get-Location).Path
python scripts/check_funasr_env.py
python scripts/evaluate_asr.py --engine mock
pytest -q tests/test_asr_evaluator.py tests/test_asr_factory.py
```
