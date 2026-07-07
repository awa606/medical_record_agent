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
| ASR | `mock`、FunASR、SenseVoice、Whisper、Qwen3-ASR、online baseline | CER、关键词召回、单段延迟、总耗时、RTF、CPU/内存/GPU 占用。 |
| LLM | `mock`、Ollama 本地模型、online baseline | 字段完整率、候选诊断合理性、生成耗时、资源占用。 |
| 知识库 | 规则模板、症状-疾病关联、检查/用药提示 | 命中率、误触发、医生复核成本。 |

## 记录表

| 样本 | 模型 | 硬件 | 输入时长 | 总耗时 | CER | 关键词召回 | 峰值内存 | GPU/CPU 占用 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fever_01.wav` | `mock-asr-v0.2` | 本机开发基线 | 25.0s | 0.001s | 0.968548 | 0.0 | 31.43 GB 总内存 | CUDA 可用，1 张 GPU | 仅证明评测链路跑通；mock 固定输出蛇咬伤脚本，不代表真实 ASR 效果。 |

## v0.5.0 本机基线

本轮已建立评测框架和配置采集，不强制下载或安装大模型。

| 项目 | 当前结果 |
| --- | --- |
| OS | Windows 11 |
| CPU | 24 逻辑核心 |
| 内存 | 31.43 GB |
| GPU/CUDA | `torch.cuda.is_available() = True`，检测到 1 张 GPU |
| FunASR | 当前环境未安装，待安装后复测 |
| Qwen-ASR | 当前环境未安装，待安装后复测 |
| Ollama CLI | 已检测到命令，但 `OLLAMA_BASE_URL` / `OLLAMA_MODEL` 未配置 |
| 评测状态 | `mock_measured_real_asr_dependency_missing` |

生成的证据文件：

- `data/asr_eval/reports/hardware_profile.json`
- `data/asr_eval/reports/mock_report.csv`
- `data/asr_eval/reports/local_model_benchmark.md`

## v0.5.1 多引擎运行状态

本轮新增统一评测入口 `scripts/run_local_asr_benchmark.py`。它会逐个尝试创建 ASR 引擎，能运行的生成 CSV，依赖缺失的记录为 `skipped`，不把依赖问题写成模型效果差。

当前实测结果：

| 引擎 | 当前状态 | 说明 |
| --- | --- | --- |
| `mock` | `measured` | 已完成 1 条 `fever_01.wav` 样本评测，只证明评测链路可跑。 |
| `funasr` | `skipped` | 当前环境缺少 `funasr` Python 依赖，待安装 `requirements-asr.txt` 后复测。 |
| `qwen3` | `skipped` | 当前环境缺少 Qwen3-ASR 依赖，待安装 `requirements-qwen3-asr.txt` 后复测。 |

新增证据文件：

- `data/asr_eval/reports/local_asr_benchmark_run.json`
- `data/asr_eval/reports/local_asr_benchmark_run.md`
- `data/asr_eval/reports/local_model_benchmark.md`

## v0.5.2 本地多模型 ASR 实测

本轮在隔离环境 `.venv-asr` 中完成多模型依赖安装与同样本评测。当前结果只代表本机开发环境，不代表医院 PC 或边缘端最终性能。

环境事实：

| 项目 | 当前值 |
| --- | --- |
| Python | CPython 3.11.6 |
| torch | 2.12.1+cpu |
| CUDA | `.venv-asr` 中不可用，本轮按 CPU-only 基线记录 |
| FunASR | 可用，已实测 |
| SenseVoice | 可用，已实测 |
| Whisper | Python 包可用，但系统缺少 `ffmpeg`，本轮跳过 |
| Qwen-ASR | 依赖安装后导入失败，错误为 `nagisa_v001.model` 读取失败，本轮跳过 |

样本说明：

| 样本 | 时长 | 说明 |
| --- | ---: | --- |
| `fever_01.wav` | 309.94s | 发热肺炎方向课程样本 |
| `chest_pain_01.wav` | 496.30s | 胸痛方向课程样本 |
| `snakebite_01.wav` | 111.93s | 文件扩展名为 `.wav`，实际容器为 MP3；脚本用 `soundfile` 探测时长 |

同样本实测摘要：

| 引擎 | 状态 | 成功样本 | 平均 CER | 平均关键词召回 | 平均耗时 | 平均 RTF | 结论 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `mock` | `measured` | 3 | 0.8786 | 0.3778 | 3.3160s | 0.1326 | 只证明工程链路可跑，不代表真实 ASR 效果。 |
| `funasr` | `measured` | 3 | 0.1952 | 0.7667 | 88.1020s | 0.2605 | 当前 CPU-only 下可作为普通话本地 baseline。 |
| `sensevoice` | `measured` | 3 | 0.1669 | 0.7333 | 50.2437s | 0.1614 | 当前 CPU-only 下速度优于 FunASR，需继续扩展方言/多语种样本。 |
| `whisper` | `skipped` | 0 | - | - | - | - | 缺少系统 `ffmpeg`，不评价模型效果。 |
| `qwen3` | `skipped` | 0 | - | - | - | - | `qwen_asr` 依赖导入失败，需单独修复环境后复测。 |

证据文件：

- `data/asr_eval/reports/asr_dependency_check.md`
- `data/asr_eval/reports/hardware_profile.json`
- `data/asr_eval/reports/funasr_report.csv`
- `data/asr_eval/reports/sensevoice_report.csv`
- `data/asr_eval/reports/local_asr_benchmark_run.md`
- `data/asr_eval/reports/local_model_benchmark.md`

阶段结论：

- 当前可以把 FunASR 和 SenseVoice 作为 `v0.5.2` 本地 ASR 真实 baseline。
- 不能把 Whisper 和 Qwen3 判为“效果差”，因为本轮分别是系统依赖和 Python 包导入阻塞。
- 下一轮应优先补 `ffmpeg`、修复 Qwen-ASR 依赖问题，并在普通医院 Windows PC 上复跑同一组命令。

## v0.5.3 非医疗公开音频 ASR 冒烟测试

本轮新增公开非医疗音频 smoke 测试，用于验证 ASR 引擎可用性、Whisper/ffmpeg 解阻塞和通用转写稳定性。该结果不替代医疗问诊样本，也不用于证明医生/患者角色区分正确。

环境与样本：

| 项目 | 结果 |
| --- | --- |
| 便携 ffmpeg | 已安装到 `tools/ffmpeg/bin/ffmpeg.exe`，来源标记为 `project_portable` |
| Qwen-ASR | `nagisa_v001.model` 读取失败；`.venv-asr` 重装命令超时后复查仍阻塞 |
| Python 3.12 | 当前机器未检测到，`.venv-qwen-asr` 暂未创建 |
| 公开样本 | Qwen 官方 `asr_zh.wav`、`asr_en.wav`；Mini LibriSpeech 3 条英文有标注样本 |

公开 smoke 运行摘要：

| 引擎 | 状态 | 样本数 | Smoke 样本 | 失败样本 | 平均耗时 | 平均 RTF | 结论 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `mock` | `measured_with_smoke` | 5 | 2 | 0 | 2.5130s | 0.1005 | 仅工程链路参考，非真实 ASR。 |
| `funasr` | `measured_with_smoke` | 5 | 2 | 0 | 2.9120s | 0.7058 | 能完成公开样本转写，英文质量不作为模型结论。 |
| `sensevoice` | `measured_with_smoke` | 5 | 2 | 0 | 1.2128s | 0.2142 | 能完成公开样本转写。 |
| `whisper` | `measured_with_smoke` | 5 | 2 | 0 | 2.8428s | 0.6754 | 已通过便携 ffmpeg 解阻塞并完成 smoke 转写。 |
| `qwen3` | `skipped` | 0 | 0 | 0 | - | - | 仍为 Qwen-ASR/nagisa 环境阻塞，不评价模型效果。 |

证据文件：

- `data/asr_eval/reports/ffmpeg_portable_setup.md`
- `data/asr_eval/reports/qwen_asr_env_check.md`
- `data/asr_eval/reports/public_smoke/public_samples_manifest.md`
- `data/asr_eval/reports/public_smoke/local_asr_benchmark_run.md`
- `data/asr_eval/reports/public_smoke/local_model_benchmark.md`

角色边界：

- 非医疗样本不进入医学关键词召回或诊断结论。
- 未在 `data/asr_eval/manifest.json` 注册的公开样本不会应用医生/患者角色映射。
- 自动多说话人分离仍需后续 FunASR speaker pipeline 或 pyannote diarization 评测。

## v0.5.4 中文优先评测与医院 PC 配置基线

本轮将评测口径从“公开非医疗 smoke”收束回中文医患主场景。英文公开样本继续保留，但只用于可选多语种冒烟测试，不进入中文医患效果结论。

评测分层：

| 分层 | 样本 | 用途 | 是否进入主结论 |
| --- | --- | --- | --- |
| `course_medical_cn` | `fever_01`、`chest_pain_01`、`snakebite_01` | 中文医患场景主评测，计算 CER、医学关键词召回、耗时和 RTF。 | 是 |
| `public_cn_smoke` | Qwen 官方 `asr_zh.wav` | 中文公开非医疗 smoke，只验证中文 ASR 可用性。 | 辅助证据 |
| `public_en_smoke` | Qwen 官方 `asr_en.wav`、Mini LibriSpeech 英文样本 | 可选多语种 smoke，验证 Whisper/ffmpeg 和多语种链路。 | 否 |

普通医院 Windows PC 配置基线：

| 档位 | 建议配置 | 说明 |
| --- | --- | --- |
| 最低可验证档 | Windows 10/11，Intel i3/i5 或 Ryzen 3/5，8-16 GB 内存，256-512 GB SSD，集成显卡 | 只保证工程流程可跑，真实 ASR 延迟需实测。 |
| 普通医院办公 PC 基线 | Windows 10/11，Intel i5-12500 / Ryzen5 5600G 或近似 6 核以上 CPU，16 GB 内存，512 GB SSD，集成显卡 | 作为本项目最低交付假设，优先评测 FunASR、SenseVoice、Whisper CPU-only。 |
| 推荐门诊工作站 | 8-16 核 CPU，32 GB 内存，1 TB SSD，NVIDIA 8-12 GB VRAM | 用于本地 ASR、长音频、Qwen3-ASR 和小型 LLM 试点。 |
| 边缘端/高配试点 | 8-16 核 CPU，32-64 GB 内存，1 TB NVMe，NVIDIA 12-16 GB 以上 VRAM 或边缘 GPU/NPU | 用于方言、多语种、多人物分离和隐私隔离部署验证。 |

证据文件：

- `docs/普通医院Windows电脑配置基线.md`
- `data/asr_eval/reports/v0_5_4_chinese_priority_asr_report.md`
- `data/asr_eval/reports/qwen_asr_py312_check.md`（Python 3.12 复测后生成）
- `data/asr_eval/reports/qwen_py312/local_model_benchmark.md`（Qwen3 smoke 复测后生成）

## 医院 PC 配置采集表

| 字段 | 采集值 |
| --- | --- |
| 医院电脑类型 | 待填写：门诊普通办公 PC / 护士站 PC / 工作站 |
| OS | 待填写 |
| CPU 型号与核心数 | 待填写 |
| 内存 | 待填写 |
| 是否有独显 | 待填写 |
| GPU 型号与显存 | 待填写 |
| 是否允许安装 Python/模型依赖 | 待填写 |
| 是否允许离线模型缓存 | 待填写 |
| 是否允许连接外网下载模型 | 待填写 |
| 麦克风/音频输入方式 | 待填写 |
| 本地部署限制 | 待填写 |

## 边缘端配置建议初稿

| 档位 | 建议配置 | 适用结论 |
| --- | --- | --- |
| CPU-only 最低档 | 4-8 核 CPU，16 GB 内存，Windows 10/11 | 适合 mock、轻量规则、短音频离线流程；真实 ASR 需实测延迟。 |
| 门诊工作站档 | 8-16 核 CPU，32 GB 内存，8-12 GB VRAM | 适合本地 ASR + 小型 LLM 或 Qwen3-ASR 轻量评测。 |
| 边缘 GPU/NPU 档 | 16-32 GB 内存，边缘 GPU/NPU，离线模型缓存 | 适合隐私隔离、门诊端本地转写和稳定运行试点。 |

## 验收标准

- 至少完成 `mock` 与一个真实本地 ASR 引擎对比。
- 至少记录一台普通医院 PC 基线配置。
- 每条结论必须有测试命令、样本名称和数据表支撑。
- 不提交真实患者音频、模型权重、API Key 或大体积评测产物。

## 推荐命令

```powershell
$env:PYTHONPATH = (Get-Location).Path
python scripts/collect_hardware_profile.py --output data/asr_eval/reports/hardware_profile.json
python scripts/check_funasr_env.py
python scripts/setup_ffmpeg_portable.py
python scripts/check_asr_dependencies.py --json-output data/asr_eval/reports/asr_dependency_check.json --md-output data/asr_eval/reports/asr_dependency_check.md
python scripts/check_qwen_asr_env.py
python scripts/run_local_asr_benchmark.py --engines mock funasr sensevoice whisper qwen3 --audio-dir video --truth-dir data/asr_eval/ground_truth --reports-dir data/asr_eval/reports
python scripts/prepare_public_asr_smoke_samples.py --limit 5
python scripts/run_local_asr_benchmark.py --engines mock funasr sensevoice whisper qwen3 --audio-dir data/asr_eval/public_smoke/audio --truth-dir data/asr_eval/public_smoke/ground_truth --reports-dir data/asr_eval/reports/public_smoke --mode smoke --evaluation-profile mixed_public_smoke
py -3.12 -m venv .venv-qwen-asr
.\.venv-qwen-asr\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.venv-qwen-asr\Scripts\python -m pip install -r requirements-qwen3-asr.txt
.\.venv-qwen-asr\Scripts\python scripts\check_qwen_asr_env.py --json-output data\asr_eval\reports\qwen_asr_py312_check.json --markdown-output data\asr_eval\reports\qwen_asr_py312_check.md
.\.venv-qwen-asr\Scripts\python scripts\run_local_asr_benchmark.py --engines qwen3 --audio-dir data\asr_eval\public_smoke\audio --truth-dir data\asr_eval\public_smoke\ground_truth --reports-dir data\asr_eval\reports\qwen_py312 --mode smoke --evaluation-profile public_cn_smoke
python scripts/evaluate_asr.py --engine mock --audio-dir data/asr_eval/audio --truth-dir data/asr_eval/ground_truth --output data/asr_eval/reports/mock_report.csv
python scripts/summarize_asr_benchmark.py --reports-dir data/asr_eval/reports --output data/asr_eval/reports/local_model_benchmark.md
pytest -q tests/test_asr_evaluator.py tests/test_asr_factory.py
```
