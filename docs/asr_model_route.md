# ASR 模型路线

本文记录 `v0.3 -> v0.5` 的模型选择策略。当前阶段先做好角色校正和产品流程，不立即替换核心 ASR 模型；模型升级必须通过本地评测数据决定。

## 当前决策

| 阶段 | 决策 | 原因 |
| --- | --- | --- |
| v0.3 | 不换模型，继续使用 `mock / funasr / qwen3 / online` 工厂结构 | 角色校正属于交互和结果保存问题，不依赖新模型。 |
| v0.4 | 强化医学知识库、热词和后处理 | 医疗术语准确率不能只靠换模型。 |
| v0.5 | 做本地模型和边缘端评测 | 用 CER、关键词召回、延迟和资源占用决定模型路线。 |

## v0.5.0 / v0.5.9 当前结论

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
- `v0.5.4` 明确中文医患样本是主评测，英文公开样本只保留为可选多语种 smoke，不进入中文医患模型结论。
- `v0.5.4` 开始按 Qwen 官方建议准备 Python 3.12 独立环境 `.venv-qwen-asr`，复测结果必须区分依赖、模型下载、资源和真实转写效果。
- 普通医院 Windows PC 基线按 16GB 内存、512GB SSD、集成显卡的办公电脑假设处理；更高阶边缘端配置单独评测。
- `v0.5.5` 已定位 Qwen-ASR 阻塞为 Windows 中文路径下 `nagisa/DyNet` 读取模型失败；迁移到 `C:\mra_qwen_runtime` ASCII 运行区后，`nagisa/qwen_asr` 导入成功。
- Qwen3-ASR 已完成公开 smoke 和 `snakebite_01.wav` 课程中文短样本实测，进入可对比评测阶段。
- `v0.5.7` 已通过分样本子进程补齐 Qwen3-ASR 三条中文医患样本同口径主评测；Qwen3 能跑完，但长音频 CER 和资源占用明显高于 FunASR/SenseVoice。
- `v0.5.8` 已补 16 分钟和 30 分钟拼接长音频稳定性测试：FunASR 两条均完成，SenseVoice 完成 16 分钟但 30 分钟失败，Qwen3 两条均完成但 CER 高、RSS 峰值接近 19GB。
- `v0.5.9` 已增加 5 分钟切片转写和合并评测：SenseVoice 30 分钟从整文件失败变为切片 `measured`，FunASR 切片模式也保持 `measured`。
- 当前 v0.6 默认建议：SenseVoice/FunASR 作为交付候选；长音频开启切片策略，FunASR 继续作为稳定 fallback，Qwen3-ASR 保留为研究路线和边缘端/GPU 复测候选。
- Ollama CLI 可检测到，但 LLM provider 所需环境变量尚未配置。
- 模型选择仍以本地评测数据决定；当前不切换默认模型，FunASR/SenseVoice 先作为稳定 baseline，Qwen3-ASR 进入 `v0.5.6` 对比评测。

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

## v0.5.4 中文优先与 Qwen-ASR 复测路线

| 项目 | 决策 |
| --- | --- |
| 主评测样本 | `video/fever_01.wav`、`video/chest_pain_01.wav`、`video/snakebite_01.wav`。 |
| 中文公开 smoke | Qwen 官方 `asr_zh.wav`，只验证中文 ASR 可用性。 |
| 英文公开 smoke | Qwen 官方 `asr_en.wav`、Mini LibriSpeech，只验证多语种/ffmpeg/Whisper 链路。 |
| Qwen 环境 | 安装 Python 3.12，创建 `.venv-qwen-asr`，不污染 `.venv-asr`。 |
| 医院 PC 基线 | 普通 Windows 办公 PC：i5/Ryzen5 级 CPU、16GB 内存、512GB SSD、集成显卡；最终以实机采集为准。 |

证据文件：

- `data/asr_eval/reports/v0_5_4_chinese_priority_asr_report.md`
- `docs/普通医院Windows电脑配置基线.md`
- `data/asr_eval/reports/qwen_asr_py312_check.md`

## v0.5.5 Qwen-ASR 阻塞修复结果

| 项目 | 结果 |
| --- | --- |
| 原始阻塞 | 原仓库中文路径下 `nagisa_v001.model` 文件存在但 DyNet 读取失败。 |
| 修复方式 | 新建 `C:\mra_qwen_runtime` ASCII 运行区，不移动仓库、不改第三方包源码。 |
| 导入验证 | `import nagisa; import qwen_asr` 成功。 |
| 公开 smoke | `qwen3=measured_with_smoke`，Qwen 官方中文样本完成转写。 |
| 课程短样本 | `snakebite_01.wav` 完成实测：CER `0.144531`，关键词召回 `0.6`，RTF `0.591740`。 |
| 当前结论 | Qwen-ASR 依赖阻塞已解除，但是否适合作为默认模型仍需 `v0.5.6` 与 FunASR/SenseVoice 全样本对比。 |

证据文件：

- `data/asr_eval/reports/qwen_ascii_runtime_setup.md`
- `data/asr_eval/reports/qwen_ascii_runtime_check.md`
- `data/asr_eval/reports/qwen_ascii_runtime/local_model_benchmark.md`
- `data/asr_eval/reports/qwen_ascii_runtime_course_sample/local_model_benchmark.md`

## v0.5.7 中文医患样本同口径对比

| 引擎 | 成功样本 | 平均 CER | 平均关键词召回 | 平均 RTF | 峰值 RSS | 当前结论 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `funasr-paraformer-zh` | 3 | 0.195247 | 0.766667 | 0.182726 | 4626.28 MB | 可作为稳定 fallback，普通医院 PC 仍需实机复测。 |
| `sensevoice-small` | 3 | 0.166945 | 0.733333 | 0.155381 | 4297.01 MB | 本机 CPU-only 下综合表现最好，建议进入 v0.6 默认候选。 |
| `qwen3-asr-0.6b` | 3 | 0.550381 | 0.588889 | 0.485806 | 10502.26 MB | 分样本补测已跑通，但长音频准确率和内存压力不适合作为 v0.6 默认模型。 |

长音频结论：`fever_01.wav` 和 `chest_pain_01.wav` 均已完成 FunASR/SenseVoice/Qwen3 对比。Qwen3 没有再次崩溃，但在 5-8 分钟中文医患样本上 CER 偏高，且 RSS 峰值超过 10GB。当前应优先把 FunASR/SenseVoice 调通到可交付产品，再把 Qwen3 放入 GPU、边缘端或后处理增强路线。

证据文件：
- `data/asr_eval/reports/v0_5_6_cn_medical_compare/local_model_benchmark.md`
- `data/asr_eval/reports/v0_5_6_cn_medical_compare/qwen3/qwen3_split_run.md`
- `data/asr_eval/reports/v0_5_7_long_audio_stability/long_audio_stability.md`

## v0.5.8 16/30 分钟长音频稳定性

本轮使用课程中文医患音频拼接生成 16 分钟和 30 分钟样本，并补少量静音到目标时长。该样本只用于工程稳定性和资源压力测试，不代表中国门诊平均问诊时长。

| 引擎 | 16 分钟状态 | 30 分钟状态 | 关键结果 | 当前结论 |
| --- | --- | --- | --- | --- |
| `funasr-paraformer-zh` | measured | measured | 30 分钟 RTF `0.231400`，RSS `4819.74 MB`，CER `0.197014` | 长音频最稳，适合作为 v0.6 fallback。 |
| `sensevoice-small` | measured | failed | 16 分钟 RTF `0.175227`，RSS `2712.36 MB`；30 分钟失败 `[Errno 22] Invalid argument` | 短中音频表现好，但 30 分钟需切片或 Debug 后再作为默认。 |
| `qwen3-asr-0.6b` | measured | measured | 30 分钟 RTF `0.955827`，RSS `18909.36 MB`，CER `0.907498` | 能跑完但资源和准确率不适合普通医院 PC 默认路线。 |

证据文件：
- `data/asr_eval/reports/v0_5_8_long_audio_stability/long_audio_stability_summary.md`
- `data/asr_eval/reports/v0_5_8_long_audio_stability/long_audio_stability.md`
- `data/asr_eval/reports/v0_5_8_long_audio_stability/qwen3/qwen3_split_run.md`
- `logs/debug/2026-07-08_sensevoice_30min_long_audio_errno22.md`

## v0.5.9 长音频切片修复结果

本轮新增 5 分钟切片转写和结果合并逻辑，不改变 `ASREngine.transcribe()`、`ASRResult`、医生端 API 或默认模型。切片评测继续使用 `long_16min_course_cn.wav` 和 `long_30min_course_cn.wav`。

| 引擎 | 16 分钟切片 | 30 分钟切片 | 关键结果 | 当前结论 |
| --- | --- | --- | --- | --- |
| `sensevoice-small-chunked` | measured，4 个切片，0 失败 | measured，6 个切片，0 失败 | 30 分钟 CER `0.170886`，RTF `0.173731`，RSS `3254.68 MB` | 5 分钟切片规避了 v0.5.8 的整文件失败，可进入 v0.6 默认候选。 |
| `funasr-paraformer-zh-chunked` | measured，4 个切片，0 失败 | measured，6 个切片，0 失败 | 30 分钟 CER `0.203343`，RTF `0.208204`，RSS `5024.94 MB` | 继续作为长音频稳定 fallback。 |

证据文件：
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/long_audio_chunked_stability_summary.md`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/chunked_asr_benchmark_run.md`
- `data/asr_eval/reports/v0_5_9_chunked_long_audio/local_model_benchmark.md`

## v0.8.3-v0.8.5 上传音频流式路线

当前交付路线不再把“先生成全部临时切片、再逐片调用离线 ASR”描述为模型原生流式。FunASR 上传音频使用 `paraformer-zh-streaming`：音频一次解码为 16 kHz PCM，并按约 600 ms 帧持续输入模型，SSE 根据模型已处理的音频秒数报告真实进度。

流式输出是临时结果，完成后再使用 `paraformer-zh + fsmn-vad + ct-punc + cam++` 做全局校准。校准可以修订文本、标点、时间戳和 `speaker_id`，但不能仅凭声纹可靠确定临床角色，因此医生/患者/其他/待确认继续保留人工校正入口。

| 能力 | 当前路线 | 结论 |
| --- | --- | --- |
| 上传音频持续出字 | Paraformer Streaming | 默认 FunASR 上传路线，模型加载后持续产生 provisional segment。 |
| 真实进度 | 已处理音频秒数 / 总时长 | 模型加载阶段不显示虚假百分比。 |
| 多说话人 | FSMN-VAD + CAM++ | 输出声学 `speaker_id`，不等同于医生/患者角色。 |
| 最终校准 | Paraformer + 标点 + CAM++ | 通过 `segment_update` 和 `reconciliation_completed` 原位修订。 |
| SenseVoice/Whisper | 分段/离线识别 | 不伪装为模型原生流式，继续作为评测和 fallback 路线。 |
| 实时结构化 | `/api/records/preview` | 只生成待医生确认的预览，不创建正式任务。 |

详细协议和前端验收见 `docs/asr_streaming_player_diarization_v0_8_5.md`。

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

- [FunASR 官方 README](https://github.com/modelscope/FunASR/blob/main/README.md)
- [SenseVoice GitHub](https://github.com/FunAudioLLM/SenseVoice)
- [Qwen3-ASR-0.6B 模型卡](https://huggingface.co/Qwen/Qwen3-ASR-0.6B)
- [OpenAI Whisper GitHub](https://github.com/openai/whisper)
- [pyannote.audio GitHub](https://github.com/pyannote/pyannote-audio)
