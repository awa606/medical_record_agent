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

## v0.5.5 Qwen-ASR ASCII 运行区修复

本轮没有移动仓库，也没有修改第三方包源码。修复方式是把 Qwen-ASR 的 Python 3.12 虚拟环境、音频副本和模型缓存放到 ASCII 路径 `C:\mra_qwen_runtime`，避开 Windows 中文路径下 `nagisa/DyNet` 读取 `nagisa_v001.model` 失败的问题。

| 项目 | 结果 |
| --- | --- |
| ASCII 运行区 | `C:\mra_qwen_runtime` |
| Python | CPython 3.12.10 |
| Qwen-ASR 导入 | `nagisa=True`、`qwen_asr=True`、`model_init=import_ok` |
| 公开 smoke | `qwen3=measured_with_smoke`，5 条公开样本完成运行 |
| 课程中文短样本 | `snakebite_01.wav` 完成实测 |

课程中文短样本结果：

| 样本 | 引擎 | CER | 关键词召回 | 耗时 | RTF | 结论 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `snakebite_01.wav` | `qwen3-asr-0.6b` | 0.144531 | 0.6 | 66.233s | 0.591740 | Qwen-ASR 依赖阻塞已解除，但仍需全样本对比。 |

证据文件：

- `data/asr_eval/reports/qwen_ascii_runtime_setup.md`
- `data/asr_eval/reports/qwen_ascii_runtime_check.md`
- `data/asr_eval/reports/qwen_ascii_runtime/local_asr_benchmark_run.md`
- `data/asr_eval/reports/qwen_ascii_runtime_course_sample/local_model_benchmark.md`

## v0.5.7 中文医患样本多模型对比与长音频稳定性

本轮在当前开发机 CPU-only 环境下，用同一组三条中文医患课程样本对比 FunASR、SenseVoice 和 Qwen3-ASR。Qwen3-ASR 使用 `C:\mra_qwen_runtime` ASCII 运行区，通过分样本子进程补测，避免长音频崩溃导致全部结果丢失。

| 模型 | 成功样本 | 平均 CER | 平均关键词召回 | 平均 RTF | 平均 CPU% | 峰值 RSS | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| FunASR | 3 | 0.195247 | 0.766667 | 0.182726 | 345.684 | 4626.28 MB | 稳定完成三样本，适合作为 fallback。 |
| SenseVoice | 3 | 0.166945 | 0.733333 | 0.155381 | 357.653 | 4297.01 MB | 本轮综合最优，建议作为 v0.6 默认候选。 |
| Qwen3-ASR | 3 | 0.550381 | 0.588889 | 0.485806 | 1380.968 | 10502.26 MB | 能跑通但资源重、长音频 CER 高，暂不作为默认交付模型。 |

长音频稳定性：
- `fever_01.wav` 约 310 秒，三模型均完成；Qwen3 CER `0.550416`，RSS 峰值 `8290.41 MB`。
- `chest_pain_01.wav` 约 496 秒，三模型均完成；Qwen3 CER `0.956197`，RSS 峰值 `10502.26 MB`。
- FunASR/SenseVoice 在两条长音频上 RTF 均小于 `0.20`，更适合普通医院 PC 的 CPU-only 交付路线。

当前没有普通医院 Windows PC 实机，因此配置建议仍按公开采购资料和合理推断处理：普通办公 PC 以 Windows 10/11、i5/Ryzen5 档 CPU、16GB 内存、512GB SSD、集显为最低参考；推荐本地 ASR PC 使用 32GB 内存；Qwen3、本地 LLM 和说话人分离建议放到 32GB+ 内存、NVIDIA 8-12GB+ 显存的边缘端或工作站复测。

证据文件：
- `data/asr_eval/reports/v0_5_6_cn_medical_compare/local_model_benchmark.md`
- `data/asr_eval/reports/v0_5_6_cn_medical_compare/qwen3/qwen3_report.csv`
- `data/asr_eval/reports/v0_5_6_cn_medical_compare/qwen3/qwen3_split_run.md`
- `data/asr_eval/reports/v0_5_7_long_audio_stability/long_audio_stability.md`

## v0.5.8 16/30 分钟长音频稳定性

本轮补齐 16 分钟和 30 分钟拼接长音频样本。样本来自课程中文医患音频拼接和静音补齐，仅用于稳定性和资源压力测试，不代表中国门诊平均问诊时长。

| 模型 | 16 分钟 | 30 分钟 | RTF / RSS 重点 | 当前判断 |
| --- | --- | --- | --- | --- |
| FunASR | 完成 | 完成 | 30 分钟 RTF `0.231400`，RSS `4819.74 MB` | 长音频最稳，适合作为普通医院 PC fallback。 |
| SenseVoice | 完成 | 失败 | 16 分钟 RTF `0.175227`，RSS `2712.36 MB`；30 分钟 `[Errno 22] Invalid argument` | 短中音频资源占用低，但 30 分钟需要切片/Debug。 |
| Qwen3-ASR | 完成 | 完成 | 30 分钟 RTF `0.955827`，RSS `18909.36 MB` | 可跑完但接近实时且内存高，不适合 16GB 普通办公 PC 默认部署。 |

配置建议更新：
- 16GB 普通医院 PC：优先 FunASR/SenseVoice，先限制单次音频长度或采用切片。
- 32GB 本地开发/门诊工作站：可做长音频和多模型对比。
- Qwen3-ASR、本地 LLM、说话人分离：建议边缘端或独显工作站复测，当前本机 CPU-only 结果只作为研究基线。

证据文件：
- `data/asr_eval/reports/v0_5_8_long_audio_stability/long_audio_samples_manifest.md`
- `data/asr_eval/reports/v0_5_8_long_audio_stability/long_audio_stability_summary.md`
- `data/asr_eval/reports/v0_5_8_long_audio_stability/long_audio_stability.md`
- `logs/debug/2026-07-08_sensevoice_30min_long_audio_errno22.md`

## v0.5.9 长音频切片稳定性修复

本轮在不改变后端 API 和 ASR 统一输出结构的前提下，新增 5 分钟切片转写评测。目标是验证普通医院 PC 部署时的长音频降级策略：整文件转写失败时，先切片，再合并文本和时间戳。

| 模型 | 16 分钟切片 | 30 分钟切片 | 30 分钟资源与速度 | 部署判断 |
| --- | --- | --- | --- | --- |
| SenseVoice | 完成，4 个切片，0 失败 | 完成，6 个切片，0 失败 | RTF `0.173731`，RSS `3254.68 MB` | 可以作为 v0.6 默认候选，但长音频必须启用切片。 |
| FunASR | 完成，4 个切片，0 失败 | 完成，6 个切片，0 失败 | RTF `0.208204`，RSS `5024.94 MB` | 继续作为普通医院 PC 的长音频稳定 fallback。 |

与 v0.5.8 对比，SenseVoice 30 分钟从整文件 `failed` 变为切片 `measured`，说明当前失败更像长音频整文件处理边界，而不是模型完全不可用。

配置建议更新：
- 16GB 普通医院 Windows PC：可优先使用 FunASR/SenseVoice，但 30 分钟级长音频必须切片，且需要限制并发。
- 32GB 门诊工作站：更适合长音频切片、多模型评测和后续本地 LLM 联动。
- Qwen3-ASR：当前仍建议在边缘端或独显工作站复测，不作为普通办公 PC 默认路线。

证据文件：
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/long_audio_chunked_stability_summary.md`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/local_model_benchmark.md`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/chunk_status/`

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
C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe scripts\check_qwen_asr_env.py --json-output data\asr_eval\reports\qwen_ascii_runtime_check.json --markdown-output data\asr_eval\reports\qwen_ascii_runtime_check.md
C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe scripts\run_local_asr_benchmark.py --engines qwen3 --mode strict --evaluation-profile course_medical_cn --audio-dir C:\mra_qwen_runtime\course_medical_cn\audio --truth-dir C:\mra_qwen_runtime\course_medical_cn\ground_truth --reports-dir data\asr_eval\reports\qwen_ascii_runtime_course_sample
python scripts/evaluate_asr.py --engine mock --audio-dir data/asr_eval/audio --truth-dir data/asr_eval/ground_truth --output data/asr_eval/reports/mock_report.csv
python scripts/summarize_asr_benchmark.py --reports-dir data/asr_eval/reports --output data/asr_eval/reports/local_model_benchmark.md
pytest -q tests/test_asr_evaluator.py tests/test_asr_factory.py
```
