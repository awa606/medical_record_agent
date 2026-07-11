# 公开三说话人样本目录

本目录只保存公开数据集的轻量 manifest、来源说明和必要占位文件。原始音频、下载压缩包、解压数据和模型缓存不得提交 GitHub。

默认数据源：

- AliMeeting Eval: <https://openslr.org/119/>
- 备选 AISHELL-5 Dev: <https://openslr.org/159/>

生成命令：

```powershell
python scripts\prepare_three_speaker_public_sample.py --dataset alimeeting --download --materialize
```

如果下载失败，脚本会记录失败原因；不能手工伪造三说话人成绩。
