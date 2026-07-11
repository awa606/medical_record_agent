# 说话人分离人工标注目录

本目录只保存人工审核后的 RTTM 标注，不保存音频。当前已标注样本为 `fever_01` 和 `chest_pain_01` 两条两说话人课程样本。

RTTM 每行格式：

```text
SPEAKER <sample_id> 1 <start_seconds> <duration_seconds> <NA> <NA> <speaker_id> <NA> <NA>
```

当前 speaker id 固定使用 `doctor` 和 `patient`。`snakebite_01` 是单人朗读样本，不纳入说话人分离成绩；三说话人课程样本仍为 `pending_sample`。

只有经过人工播放复核的边界才能作为 ground truth。FunASR/CAM++ 自动输出不能反向充当人工真值。标注完成前，DER/JER 结果必须记为 `pending_annotation` 或 `not_available`，不得伪造测量值。
