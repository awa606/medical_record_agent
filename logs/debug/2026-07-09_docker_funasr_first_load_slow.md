# Debug Log：Docker FunASR 首次加载耗时较长

## Problem

在 Docker `2601` 医生端上传 `snakebite_01.wav` 并选择 FunASR 后，前端长时间停留在“转写中、0段、0%”。

## Steps to Reproduce

1. 启动 Docker：`docker compose up -d --build`。
2. 打开 `http://127.0.0.1:2601/static/doctor.html`。
3. 上传 `video/snakebite_01.wav`。
4. ASR 引擎选择 `FunASR`。
5. 点击上传并观察中间转写栏。

## Expected vs Actual

- Expected：短音频在模型就绪后显示转写结果和角色校正入口。
- Actual：首次运行时前端停留在 0 段，直到模型下载和初始化完成。

## Root Cause

Docker 容器首次运行 FunASR 时需要下载并初始化模型。容器日志显示 `model.pt` 约 1.13GB，下载和初始化期间后端尚未产生 SSE segment。

## Fix

本轮不修改算法逻辑。处理方式为：

- 保留模型缓存目录 `data/asr_model_cache/`，避免每次重建后重复下载。
- 在验收和演示脚本中说明首次模型加载慢，演示前需要预热 FunASR / SenseVoice。
- 现场演示保留 Mock ASR 作为兜底路线。

## Verification

- 模型下载完成后，FunASR 短音频复测通过。
- 前端截图：`docs/final_report/images/v0_6_7_frontend_acceptance/03_funasr_short_real.png`。
- Docker 健康检查：`curl http://127.0.0.1:2601/health` 返回 `{"status":"ok"}`。
