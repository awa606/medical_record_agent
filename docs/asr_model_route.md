# ASR 模型路线

本文记录 `v0.3 -> v0.5` 的模型选择策略。当前阶段先做好角色校正和产品流程，不立即替换核心 ASR 模型；模型升级必须通过本地评测数据决定。

## 当前决策

| 阶段 | 决策 | 原因 |
| --- | --- | --- |
| v0.3 | 不换模型，继续使用 `mock / funasr / qwen3 / online` 工厂结构 | 角色校正属于交互和结果保存问题，不依赖新模型。 |
| v0.4 | 强化医学知识库、热词和后处理 | 医疗术语准确率不能只靠换模型。 |
| v0.5 | 做本地模型和边缘端评测 | 用 CER、关键词召回、延迟和资源占用决定模型路线。 |

## v0.5.0 / v0.5.3 当前结论

`v0.5.0` 先完成评测框架和配置采集，不切换默认模型。

- 当前机器已完成硬件 profile：24 逻辑核心、31.43 GB 内存；早前主环境检测到 CUDA 可用，但本轮 `.venv-asr` 安装的是 CPU 版 torch，因此 v0.5.2 实测按 CPU-only 基线解释。
- `mock` 基线已跑通，但当前样本是 `fever_01.wav`，mock 引擎固定输出蛇咬伤脚本，因此只证明评测链路可用，不代表 ASR 模型效果。
- `v0.5.1` 新增 `scripts/run_local_asr_benchmark.py`，统一记录 `mock/funasr/qwen3` 的 `measured/skipped/failed` 状态。
- `v0.5.2` 在 `.venv-asr` 中完成 `mock/funasr/sensevoice/whisper/qwen3` 同样本运行记录。
- FunASR 和 SenseVoice 已在 `fever_01`、`chest_pain_01`、`snakebite_01` 三条课程样本上完成 CPU-only 实测。
- Whisper Python 包已安装，但系统缺少 `ffmpeg`，本轮记录为 `skipped`。
- Qwen-ASR 依赖安装后导入失败，错误为 `nagisa_v001.model` 读取失败，本轮记录为 `skipped`。
- `v0.5.3` 安装项目本地便携 ffmpeg 后，Whisper 已在公开非医疗样本上完成 smoke 复测。
- Qwen-ASR 在 `.venv-asr` 中重装 `nagisa/qwen-asr` 后仍失败；当前机器未检测到 Python 3.12，`.venv-qwen-asr` 暂未创建。
- Ollama CLI 可检测到，但 LLM provider 所需环境变量尚未配置。
- 模型选择仍以本地评测数据决定；当前不切换默认模型，FunASR/SenseVoice 先作为本地真实 baseline。

## v0.5.2 实测结果摘要

| 引擎 | 状态 | 平均 CER | 平均关键词召回 | 平均 RTF | 当前结论 |
| --- | --- | ---: | ---: | ---: | --- |
| `mock` | `measured` | 0.8786 | 0.3778 | 0.1326 | 只用于工程链路验证。 |
| `funasr` | `measured` | 0.1952 | 0.7667 | 0.2605 | 可作为普通话本地 baseline，需医院 PC 复测。 |
| `sensevoice` | `measured` | 0.1669 | 0.7333 | 0.1614 | 当前本机 CPU-only 下速度较好，需补方言/多语种样本。 |
| `whisper` | `skipped` | - | - | - | 缺少系统 `ffmpeg`，不评价效果。 |
| `qwen3` | `skipped` | - | - | - | 依赖导入失败，需修复环境后复测。 |

证据文件见 `data/asr_eval/reports/local_model_benchmark.md` 和 `data/asr_eval/reports/local_asr_benchmark_run.md`。

## v0.5.3 公开非医疗 smoke 结果

| 引擎 | 状态 | 样本数 | 平均 RTF | 当前结论 |
| --- | --- | ---: | ---: | --- |
| `funasr` | `measured_with_smoke` | 5 | 0.7058 | 能完成公开样本转写，英文效果不作为医疗模型结论。 |
| `sensevoice` | `measured_with_smoke` | 5 | 0.2142 | 能完成公开样本转写。 |
| `whisper` | `measured_with_smoke` | 5 | 0.6754 | 便携 ffmpeg 已解阻塞，可继续用于多语种评测。 |
| `qwen3` | `skipped` | 0 | - | 仍为 Qwen-ASR/nagisa 环境阻塞，需 Python 3.12 隔离环境后复测。 |

公开非医疗样本只验证 ASR 可用性和通用转写，不替代医疗问诊样本，也不证明医生/患者角色自动区分正确。

## 候选模型

| 场景 | 候选 | 说明 |
| --- | --- | --- |
| 普通话本地 baseline | FunASR / SenseVoice | 适合本地部署和中文语音识别验证。 |
| 方言与多语种 | Qwen3-ASR-0.6B / Qwen3-ASR-1.7B、SenseVoice、Whisper | 先以 Qwen3-ASR-0.6B 做轻量评测，高配机器再测 1.7B。 |
| 多人物转写 | FunASR speaker pipeline、pyannote.audio | ASR 文本识别和说话人分离要分开评测。 |
| 低资源边缘端 | FunASR 小模型、SenseVoice-small、whisper.cpp / faster-whisper | 重点看 CPU-only 延迟、内存和部署复杂度。 |

## v0.5 评测指标

- ASR：CER、关键词召回、总耗时、单段延迟、CPU/内存/GPU 占用。
- 角色与说话人：说话人切分准确率、医生/患者角色修正成本。
- 方言：四川话、粤语、东北话等样本的可懂度和医学关键词保留率。
- 多语种：中文、英文及混合问诊样本识别质量。
- 医学后处理：热词命中率、术语纠错前后差异。

## 工程边界

- `v0.3` 不引入新的模型依赖，避免把角色校正功能和模型切换风险绑定在一起。
- `v0.5` 评测不提交模型权重、真实患者音频或大体积评测产物。
- 多人物转写必须保留人工校正入口，不能把 diarization 结果作为最终事实。

## 参考资料

- [FunASR 官方文档](https://modelscope.github.io/FunASR/)
- [SenseVoice GitHub](https://github.com/FunAudioLLM/SenseVoice)
- [Qwen3-ASR-0.6B 模型卡](https://huggingface.co/Qwen/Qwen3-ASR-0.6B)
- [OpenAI Whisper GitHub](https://github.com/openai/whisper)
- [pyannote.audio GitHub](https://github.com/pyannote/pyannote-audio)
