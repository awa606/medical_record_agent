# v0.8.10 真实公开多说话人样本记录

## 样本来源

- 数据集：AliMeeting Eval
- 来源：<https://openslr.org/119/>
- 许可证：CC BY-SA 4.0
- 数据说明：中文真实会议语音，Eval 集包含 2-4 人会议片段，适合用于说话人分离评测。
- 本地数据包：`data/asr_eval/public_diarization/cache/Eval_Ali.tar.gz`
- 本地抽取音频：`data/asr_eval/public_diarization/audio/three_speaker_alimeeting_01.wav`

> 原始压缩包、解压目录和音频文件均为本地忽略目录，不提交 GitHub。

## 抽样结果

- 样本 ID：`three_speaker_alimeeting_01`
- 抽样窗口：`6.9s -> 246.9s`
- 片段长度：约 240 秒
- RTTM：`data/asr_eval/diarization_ground_truth/three_speaker_alimeeting_01.rttm`
- 官方标注来源：`TextGrid` 转换，不手工编造说话人标签。
- RTTM 中 speaker 数：4
- speaker id：`N_SPK8013`、`N_SPK8014`、`N_SPK8015`、`N_SPK8016`

## 当前评测状态

- `FunASR CAM++`：`skipped`
- 原因：当前 `funasr_campp` 评测适配器读取已有 `ASRResult`；新公开样本已具备音频和人工 RTTM，但尚未生成对应 ASRResult。
- `pyannote`：未安装，记录为 `skipped`。
- `3D-Speaker`：未配置独立环境，记录为 `skipped`。

## 后续处理

1. 用真实 ASR 流程生成 `three_speaker_alimeeting_01` 的 `ASRResult`。
2. 再用 `scripts/evaluate_diarization.py --engine funasr_campp` 对齐 RTTM 计算边界和混合语句指标。
3. 如后续安装 pyannote 或 3D-Speaker，再以同一 RTTM 做横向比较。
