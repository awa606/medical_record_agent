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

当前根因不是 Python 版本或未创建隔离环境。Python 3.12 和 `.venv-qwen-asr` 已验证可用，失败点稳定复现为 `nagisa_v001.model` 读取失败，属于 `nagisa/qwen-asr` 包兼容性、包内模型文件或本地权限/路径读取问题。

## Fix

本轮不强行修改第三方包，也不把 Qwen-ASR 记为模型效果差。当前修复策略是：

- 将 Qwen3-ASR 评测状态记录为 `skipped`。
- 在 `qwen_asr_py312_check.md` 中明确“Python 3.12 已满足，仍为 nagisa 包级阻塞”。
- 后续单独开 Debug 任务排查 `nagisa` 包文件、重新安装来源、上游版本或替代 Qwen-ASR 调用方式。

## Verification

```powershell
.\.venv-qwen-asr\Scripts\python scripts\check_qwen_asr_env.py --json-output data\asr_eval\reports\qwen_asr_py312_check.json --markdown-output data\asr_eval\reports\qwen_asr_py312_check.md
.\.venv-qwen-asr\Scripts\python scripts\run_local_asr_benchmark.py --engines qwen3 --mode smoke --evaluation-profile public_cn_smoke --audio-dir data\asr_eval\public_smoke\audio --truth-dir data\asr_eval\public_smoke\ground_truth --reports-dir data\asr_eval\reports\qwen_py312
```

验证结果：

- `qwen_asr_py312_check.md` 显示 Python 3.12 与 `.venv-qwen-asr` 均可用。
- `nagisa=False`、`qwen_asr=False`。
- Qwen benchmark 报告显示 `qwen3=skipped`，原因是 `nagisa_v001.model` 读取失败。
