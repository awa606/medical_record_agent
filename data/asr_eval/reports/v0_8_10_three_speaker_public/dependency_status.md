# v0.8.7 说话人分离依赖检查

| 引擎 | 状态 | 说明 |
| --- | --- | --- |
| `pyannote` | `skipped` | pyannote.audio is not installed |
| `three_d_speaker` | `skipped` | THREED_SPEAKER_PYTHON is not configured |
| `funasr_campp` | `measured_in_docker` | FunASR VAD + punctuation + CAM++ is the current production baseline. |

## 结论

- 当前交付基线仍为 FunASR VAD + CAM++。
- pyannote 需要隔离环境和本地 `HF_TOKEN`；3D-Speaker 需要独立本地运行区。
- 在人工 RTTM 完成前，不输出或宣称 DER/JER 成绩。
- 缺依赖记为 `skipped`，不解释为模型效果差。
