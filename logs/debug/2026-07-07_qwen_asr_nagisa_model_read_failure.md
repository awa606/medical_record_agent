# Debug Log：Qwen-ASR nagisa 模型文件读取失败

## Problem

`v0.5.4` 按 Qwen-ASR 路线安装 Python 3.12 并创建 `.venv-qwen-asr` 后，`qwen_asr` 仍无法导入，错误指向 `nagisa/data/nagisa_v001.model` 读取失败。

## Steps to Reproduce

```powershell
py -3.12 -m venv .venv-qwen-asr
.\.venv-qwen-asr\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.venv-qwen-asr\Scripts\python -m pip install -r requirements-qwen3-asr.txt
.\.venv-qwen-asr\Scripts\python scripts\check_qwen_asr_env.py --json-output data\asr_eval\reports\qwen_asr_py312_check.json --markdown-output data\asr_eval\reports\qwen_asr_py312_check.md
```

## Expected vs Actual

| 项目 | 期望 | 实际 |
| --- | --- | --- |
| Python 环境 | 使用 Python 3.12 独立环境 | 已满足：CPython 3.12.10，`.venv-qwen-asr` |
| `nagisa` | 可导入 | 不可导入，无法读取 `nagisa_v001.model` |
| `qwen_asr` | 可导入并进入模型初始化检查 | 不可导入，因为依赖 `nagisa` 失败 |
| Qwen3-ASR 转写 | 至少进入 smoke 评测 | `qwen3=skipped` |

## Root Cause

当前根因不是 Python 版本或未创建隔离环境。Python 3.12 和 `.venv-qwen-asr` 已验证可用，失败点稳定复现为 `nagisa_v001.model` 读取失败。

`v0.5.5` 进一步验证后，根因收敛为 Windows 中文路径兼容问题：原仓库路径包含 `开题报告\病历`，Python 可以直接读取模型文件，但 DyNet 在 `ParameterCollection.populate()` 中读取失败；将 Qwen-ASR 虚拟环境迁移到 ASCII 路径 `C:\mra_qwen_runtime\.venv-qwen-asr` 后，`nagisa` 和 `qwen_asr` 均可导入。

## Fix

本轮不修改第三方包源码，也不移动当前仓库。采用本地 ASCII 运行区修复：

- 新建 `C:\mra_qwen_runtime`。
- 在该目录创建 `C:\mra_qwen_runtime\.venv-qwen-asr`。
- 将 Qwen smoke 音频和课程短样本复制到 ASCII 路径。
- 设置模型缓存到 `C:\mra_qwen_runtime\model_cache`。
- 保持仓库代码路径不变，通过 ASCII 运行区解释器执行评测脚本。

## Verification

```powershell
.\.venv-qwen-asr\Scripts\python scripts\check_qwen_asr_env.py --json-output data\asr_eval\reports\qwen_asr_py312_check.json --markdown-output data\asr_eval\reports\qwen_asr_py312_check.md
.\.venv-qwen-asr\Scripts\python scripts\run_local_asr_benchmark.py --engines qwen3 --mode smoke --evaluation-profile public_cn_smoke --audio-dir data\asr_eval\public_smoke\audio --truth-dir data\asr_eval\public_smoke\ground_truth --reports-dir data\asr_eval\reports\qwen_py312
C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe -c "import nagisa; import qwen_asr; print('ok')"
C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe scripts\check_qwen_asr_env.py --json-output data\asr_eval\reports\qwen_ascii_runtime_check.json --markdown-output data\asr_eval\reports\qwen_ascii_runtime_check.md
C:\mra_qwen_runtime\.venv-qwen-asr\Scripts\python.exe scripts\run_local_asr_benchmark.py --engines qwen3 --mode strict --evaluation-profile course_medical_cn --audio-dir C:\mra_qwen_runtime\course_medical_cn\audio --truth-dir C:\mra_qwen_runtime\course_medical_cn\ground_truth --reports-dir data\asr_eval\reports\qwen_ascii_runtime_course_sample
```

验证结果：

- `qwen_asr_py312_check.md` 显示 Python 3.12 与 `.venv-qwen-asr` 均可用。
- `nagisa=False`、`qwen_asr=False`。
- Qwen benchmark 报告显示 `qwen3=skipped`，原因是 `nagisa_v001.model` 读取失败。
- `C:\mra_qwen_runtime` ASCII 运行区中 `import nagisa; import qwen_asr` 成功。
- `qwen_ascii_runtime_check.md` 显示 `nagisa=True`、`qwen_asr=True`、`model_init=import_ok`。
- `qwen_ascii_runtime_course_sample` 中 `snakebite_01.wav` 完成实测：CER `0.144531`，关键词召回 `0.6`，RTF `0.591740`。
