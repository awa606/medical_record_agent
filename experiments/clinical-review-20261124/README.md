# 六场合成门诊听录材料的离线封装

本目录的构建器从六份经逐案核验的本地 HTML 生成一个 ZIP，内含中性病例目录和六个可独立打开的听录页。目录只列编号和原音时长。录音、模板和首次模型响应由资料持有人在本地保管。

对接收者，请打开“从这里开始听录.html”，按组织者分配的编号听原音，记录并保存第一阶段答卷。能返回草稿的病例支持继续评阅草稿。组件拒绝生成时保留仅听录表。正式使用时由组织者核对受邀者资历、此前是否接触题材和实际收回的记录。

## 重新构建

准备 UTF-8 JSON 对象，键使用 `zh_original_001` 至 `zh_original_006`，每例填写三个字段。

| 字段 | 来源 |
| --- | --- |
| `source` | 该例已核验的单文件 HTML 的绝对路径或相对于 JSON 的路径 |
| `sha256` | 独立逐页验证记录中的完整 SHA-256 |
| `seconds` | 同一例原音 WAV 的实际秒数 |

在 Python 3.11 或更高版本用新的输出路径执行命令。

```powershell
python -B -X utf8 experiments/clinical-review-20261124/build_packet.py 已核验听录页.json 合成问诊听录.zip
Get-FileHash -Algorithm SHA256 -LiteralPath '.\合成问诊听录.zip'
```

构建器先核对编号、页面摘要及声音存在性，写入临时压缩包后逐项回读核对，再公开新的 ZIP 路径。运行前的逐案验证负责确认真实音频摘要、首次转写输入、模型原始回复、是否有待评稿，以及断网后的锁定、恢复与错病例拒绝。听录页仅用于本地工程协作；它不认证使用者身份。

## 两份三人合成问诊音轨

在装有 Microsoft Huihui、Kangkang、Yaoyao 简体中文语音的 Windows 电脑，用 Python 3.11 或更高版本从仓库根目录执行。目标选择一个新目录。

~~~powershell
python -X utf8 experiments/clinical-review-20261124/render_visit_audio.py 三人合成问诊
~~~

输出为 `SYN-TM-B.wav`、`SYN-TM-C.wav` 和逐句时间轴 `timeline.json`。每个音频为 16 kHz 单声道 16 位 PCM，各句间隔 300 毫秒。角色参考来自既有原创脚本。经验证的本机语音版本中，B、C 文件 SHA-256 分别为 `1f8a5348cdd81e80c652e74eb211605edd6083723779eeefb02ca19a46b9f278` 与 `5ed37c62cb21ca1e8bb49cba44fe21a20c6a9e4b4e6ee2512309de6ff84d925a`。若系统语音版本不同，请按实际生成文件记录摘要。[三人原始台词](../../data/clinical_e2e/synthetic_visit_timeline_v1/spoken_input.json) · [首次识别与人工订正记录](../../docs/evidence/20261124_portable_session_review.md)
