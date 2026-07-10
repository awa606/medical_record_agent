# FunASR 句级时间戳单位识别错误

## Problem

真实 Docker 音频冒烟测试完成后，4.2 秒音频的第一段开始时间显示为 `480` 秒，导致播放器定位和证据回放位置错误。

## Steps to reproduce

1. 在 Docker `2601` 医生端上传短中文 WAV。
2. 等待 Paraformer Streaming 和离线 CAM++ 校准完成。
3. 获取 ASR session 最终结果。
4. 检查 `sentence_info` 映射后的 `start_time`。

## Expected vs actual

- 预期：FunASR `sentence_info.start=480` 应映射为 `0.48` 秒。
- 实际：旧逻辑根据数值大小猜测单位，小于 1000 时没有除以 1000，得到 `480` 秒。

## Root cause

FunASR 句级 `sentence_info` 时间戳使用毫秒。旧实现把时间戳当作“可能是秒、也可能是毫秒”，导致短音频中的小毫秒值被误判为秒。

## Fix

- `app/services/asr/funasr_engine.py` 对 `sentence_info.start/end` 统一除以 1000。
- `app/services/asr/sensevoice_engine.py` 同步修正相同映射逻辑。
- 增加单元测试，固定验证 `480 ms -> 0.48 s`。

## Verification

```powershell
$env:PYTHONPATH=(Get-Location).Path
pytest -q tests/test_asr_factory.py tests/test_funasr_diarization_engine.py
```

结果：时间戳单位测试通过；镜像重建后，4.204 秒真实中文短音频的第一段时间戳为 `0.48s-3.775s`，媒体拖动 Range 请求返回 `206 Partial Content`。
