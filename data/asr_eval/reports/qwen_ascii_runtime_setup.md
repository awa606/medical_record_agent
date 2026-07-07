# Qwen-ASR ASCII 运行区修复报告

本报告用于 `v0.5.5`，记录 Qwen-ASR 依赖阻塞的修复过程。结论是：原仓库路径包含中文字符，`nagisa/DyNet` 无法读取 `nagisa_v001.model`；将 Qwen-ASR 运行环境移到 `C:\mra_qwen_runtime` 后，`nagisa` 和 `qwen_asr` 可以正常导入，并完成公开 smoke 与课程中文短样本实测。

## 修复动作

| 项目 | 结果 |
| --- | --- |
| ASCII 运行区 | `C:\mra_qwen_runtime` |
| Python | CPython 3.12.10 |
| 虚拟环境 | `C:\mra_qwen_runtime\.venv-qwen-asr` |
| `nagisa` | 可导入，版本 `0.2.11` |
| `qwen_asr` | 可导入，版本 `0.0.6` |
| 模型缓存 | `C:\mra_qwen_runtime\model_cache` |
| Git 提交边界 | 不提交虚拟环境、模型缓存、音频副本 |

## 验证命令

```powershell
C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe -c "import nagisa; import qwen_asr; print('ok')"

$env:HF_HOME='C:\mra_qwen_runtime\model_cache'
$env:MODELSCOPE_CACHE='C:\mra_qwen_runtime\model_cache\modelscope'
$env:QWEN3_ASR_DEVICE='cpu'

C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe scripts\check_qwen_asr_env.py --json-output data\asr_eval\reports\qwen_ascii_runtime_check.json --markdown-output data\asr_eval\reports\qwen_ascii_runtime_check.md
C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe scripts\run_local_asr_benchmark.py --engines qwen3 --mode smoke --evaluation-profile public_cn_smoke --audio-dir C:\mra_qwen_runtime\public_smoke\audio --truth-dir C:\mra_qwen_runtime\public_smoke\ground_truth --reports-dir data\asr_eval\reports\qwen_ascii_runtime
C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe scripts\run_local_asr_benchmark.py --engines qwen3 --mode strict --evaluation-profile course_medical_cn --audio-dir C:\mra_qwen_runtime\course_medical_cn\audio --truth-dir C:\mra_qwen_runtime\course_medical_cn\ground_truth --reports-dir data\asr_eval\reports\qwen_ascii_runtime_course_sample
```

## 当前实测结果

| 样本集 | 状态 | 样本数 | 关键结果 |
| --- | --- | ---: | --- |
| 公开 smoke | `measured_with_smoke` | 5 | `qwen_asr_zh.wav` 完成转写；英文样本只作为多语种 smoke，不进入中文医患结论。 |
| 课程中文短样本 | `measured` | 1 | `snakebite_01.wav`：CER `0.144531`，关键词召回 `0.6`，RTF `0.591740`。 |

## 结论

- Qwen-ASR 的依赖阻塞已解除，根因指向中文路径下 `nagisa/DyNet` 读取包内模型失败。
- 当前 Qwen3-ASR 已可进入真实 ASR 评测阶段。
- 下一步不直接替换默认模型，而是进入 `v0.5.6`：对比 Qwen3-ASR、FunASR、SenseVoice 在中文医患样本上的准确率、关键词召回、RTF 和资源占用。
