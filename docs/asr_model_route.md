# ASR 模型路线

本文记录 `v0.3 -> v0.5` 的模型选择策略。当前阶段先做好角色校正和产品流程，不立即替换核心 ASR 模型；模型升级必须通过本地评测数据决定。

## 当前决策

| 阶段 | 决策 | 原因 |
| --- | --- | --- |
| v0.3 | 不换模型，继续使用 `mock / funasr / qwen3 / online` 工厂结构 | 角色校正属于交互和结果保存问题，不依赖新模型。 |
| v0.4 | 强化医学知识库、热词和后处理 | 医疗术语准确率不能只靠换模型。 |
| v0.5 | 做本地模型和边缘端评测 | 用 CER、关键词召回、延迟和资源占用决定模型路线。 |

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
