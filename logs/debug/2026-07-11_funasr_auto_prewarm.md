# FunASR 自动后台预热记录

## Problem

真实 ASR 首次上传时，FunASR 需要加载 Paraformer、VAD、标点和 CAM++ 等模型。此前必须通过手动上传音频触发冷启动，医生端容易表现为长时间等待，评审现场也容易被误判为页面卡住。

## Steps to Reproduce

1. 启动本地或 Docker 服务。
2. 首次选择 `FunASR` 上传中文音频。
3. 前端进入转写状态，但模型下载/加载期间没有即时文本输出。

## Expected vs Actual

- Expected：服务启动后后台预热模型，医生端能看到“模型准备中/模型已就绪/预热失败”。
- Actual：首次上传音频时才开始加载模型，真实 ASR 首段输出延迟明显。

## Root Cause

FunASR 模型加载位于请求路径中，缺少服务启动后的非阻塞预热机制和可查询状态接口。

## Fix

- 新增 `app/services/asr/prewarm.py`：后台线程预热 Paraformer Streaming、离线 Paraformer、VAD、标点和 CAM++。
- 新增 `GET /api/asr/prewarm/status`：返回 `idle/warming/ready/failed`、错误信息和加载耗时。
- Docker 默认设置 `ASR_PREWARM_ENABLED=1`，服务启动后自动后台预热，不阻塞 `/health`。
- 医生端顶部 ASR Engine 下方显示简洁模型状态。

## Verification

- `pytest -q tests/test_asr_prewarm.py`：通过
- `node --check static/doctor.js`：通过
- 预热失败时不影响文本生成和 Mock ASR，医生端会提示可继续使用 Mock ASR。
