# v0.5.8 长音频稳定性样本清单

> 本清单只说明稳定性测试样本如何生成。16 分钟是待验证的场景假设，30 分钟是压力测试场景；二者都不代表中国门诊平均问诊时长。

## 生成策略

- 生成时间：2026-07-08T10:25:07+08:00
- 源音频目录：`video`
- 源标注目录：`data/asr_eval/ground_truth`
- 样本来源：课程演示中文医患音频拼接，必要时补静音。
- 使用边界：只用于 ASR 吞吐、内存、CPU、失败恢复和长音频流程稳定性。
- Qwen ASCII 运行区副本：`C:\mra_qwen_runtime\long_audio_stability`

## 源样本

| 样本 | 音频 | 标注 | 时长秒 |
| --- | --- | --- | ---: |
| fever_01 | `video/fever_01.wav` | `data/asr_eval/ground_truth/fever_01.txt` | 309.94 |
| chest_pain_01 | `video/chest_pain_01.wav` | `data/asr_eval/ground_truth/chest_pain_01.txt` | 496.303 |
| snakebite_01 | `video/snakebite_01.wav` | `data/asr_eval/ground_truth/snakebite_01.txt` | 111.924 |

## 长音频样本

| 样本 | 目标秒 | 实际秒 | 音频 | 标注 | 拼接段数 |
| --- | ---: | ---: | --- | --- | ---: |
| long_16min_course_cn | 960 | 960.0 | `data/asr_eval/long_audio_stability/audio/long_16min_course_cn.wav` | `data/asr_eval/long_audio_stability/ground_truth/long_16min_course_cn.txt` | 4 |
| long_30min_course_cn | 1800 | 1799.999 | `data/asr_eval/long_audio_stability/audio/long_30min_course_cn.wav` | `data/asr_eval/long_audio_stability/ground_truth/long_30min_course_cn.txt` | 6 |

## 注意事项

- CER 可作为同一拼接标注下的粗略参考，但本轮更关注完成状态、RTF、RSS、CPU 和失败原因。
- 音频文件不提交 GitHub；脚本、报告和轻量清单可提交。
