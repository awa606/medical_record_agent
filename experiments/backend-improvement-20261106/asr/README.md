# ASR与在线说话人分离：隔离研究准备

本目录包含影子实验的事件契约、文件预检及获准后的独立CPU兼容脚本，不接入生产，不发送音频。研究日期：2026-11-06；检查起点：`36f4de7`。基础接口检查不加载模型；Nemotron下载和兼容验证单独记录如下。**Research Gate：NEEDS MORE EVIDENCE；尚未选择生产候选。**

## 本次实际交付

- `shadow_contract.py`：独立事件账本、Sortformer时间区间适配、复用既有说话人评分器的保存结果适配。
- `test_shadow_contract.py`：14项合成接口控制；本轮全部通过。测试不表示模型准确率。
- `preflight.py`：仅读取包元数据、选定音频和标注的哈希，输出JSON，不导入推理框架。
- `nemotron_compatibility.py`和`measured_summary.json`：获准后的隔离CPU兼容执行器与不含原文的实际结果；原始分段保留在D盘私有实验目录。
- 已完成独立功能／契约复核。复核发现“撤回角色后仍计作当前已接受”和非法speaker类型的问题，修复后新增回归；未改生产ASR或角色门槛。

在仓库根目录执行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m unittest discover -s experiments/backend-improvement-20261106/asr -p 'test_*.py' -v
python -B experiments/backend-improvement-20261106/asr/preflight.py --audio 'C:/Users/AWA007/Desktop/MediListen 真实测试26327/authorized_fever_60s.wav'
python -B experiments/backend-improvement-20261106/asr/shadow_contract.py --help
```

14项测试在本机Python 3.13.5运行，耗时0.813秒；这组接口检查的真实模型调用为0。后续Nemotron实际推理另表记录，不能混为零调用。未重跑10秒／2秒旧实验，仅受本次接口改变影响的检查再次执行。

## 数据与环境盘点：哪些能用

| 资产 | 本轮结果 | 允许的用途与缺口 |
|---|---|---|
| 桌面`authorized_fever_60s.wav` | 60秒、16kHz单声道；SHA匹配既有授权输入`e0d16a…f74a4` | 已在原Alpha2.3证据目录找回配套裁剪RTTM，两个SHA均与9月19日冻结记录一致；可进行该历史样本的声学回归，不套用完整RTTM |
| `fever_01.rttm` | 74段，末尾309.94秒；SHA `3a9b437152daa53665054a8d51220dd3edd9f5dd6537314ba6040d74de04c6a6` | 人工标注说明存在，但对应完整WAV当前目录缺失 |
| `chest_pain_01.rttm` | 68段，末尾496.303秒；SHA `9cac59991c1e1198190d86e11eb27ef8e44731a0cce2f6a7b9c8c2a522681a8a` | 同上；不能套到另一段录音 |
| `three_speaker_alimeeting_01.rttm` | 60段、240秒；SHA `d958683409acb33002d95c1c04d0282e5380bfb53e33d0d99c04c4c28a809fe6` | 官方公开数据派生记录保留，原文件和裁剪音频当前目录缺失；记录实际为4位说话人，不按旧文件名猜3人 |
| `executable_clinical_v1` | 23例：12校准、11封存测试；12份校准WAV哈希与清单一致；没有打开测试集正文 | **不可当多人声学真值**：生成脚本把所有角色台词一次TTS朗读，按总时长等分标注；保留为文本／接口控制，不把脚本角色当真实声音 |
| 主机Python | 3.13.5；torch／torchaudio 2.10.0，transformers 5.12.1 | FunASR、diart、pyannote.audio、pyannote.metrics、nemo_toolkit均未安装；这只是当前解释器状态，不代表容器中没有FunASR |
| 新说话人模型权重 | 已获准下载Nemotron一种396954592字节权重到独立D盘目录，哈希通过；diart未下载 | Nemotron兼容经过一次缓存定位修复后可运行，但2CPU下60秒RTF2.262，未达到实时目标 |

随后主流程恢复Docker后，获准只读检查活动容器`mra-full-acceptance-20261102-app-1`。其环境与主机不同：Python 3.11.15、FunASR 1.3.29、torch／torchaudio 2.11.0+cpu、transformers 5.14.1；diart、pyannote.audio／metrics、nemo_toolkit均未安装。检查只使用包元数据和文件SHA，没有导入推理框架。

只读模型卷`mra_candidate_models`挂载于`/app/model_cache`，已核验：

| 已有权重 | 大小 | SHA256 |
|---|---:|---|
| Paraformer online `model.pt` | 880716041字节 | `4fdfb48ed4471777c9a511e96a2acae17f77cac9d709cc756634622769192a64`，与10月19日实验一致 |
| CAM++ `campplus_cn_common.bin` | 28036335字节 | `3388cf5fd3493c9ac9c69851d8e7a8badcfb4f3dc631020c4961371646d5ada8` |

两者位于`/app/model_cache/modelscope/models/iic--<对应模型>/snapshots/master/`。目录名`master`不是不可变模型版本，后续使用上表哈希锁定。没有向生产安装新diarization依赖和权重，不需要重新下载FunASR。

已找回`medical_record_agent_alpha23_role_gate/.artifacts/alpha23-role-gate-20260919_144634/clips/fever_120_180.wav`及同名RTTM；`run_role_gate_spike.py`明确将两者配对，原ASR结果SHA也匹配`d7425b…b9c271`。RTTM SHA为`3cb3a3cc9c9634b9b74e75a3abff039d944d11c92023ac9c4e8c6eebcc0c057b`。这消除了当前60秒样本的配对阻塞，未恢复其他缺失录音。`preflight.py --reference-rttm`只接受明确提供且匹配的原件；实际正控制通过，错误完整RTTM被判为不匹配，两项均零模型调用。

对应完整音频应从已有授权归档按哈希恢复，或提供有原音SHA和起止偏移的裁剪记录；不重新下载整套公开数据。不得用ASR输出生成自己的真值。旧报告中的推理速度与仅读取保存结果的评分耗时必须区分。

TTS风险源码位置：`scripts/prepare_executable_speaker_role_dataset.py`的`build_dataset`将所有台词拼接后单次调用`synthesize_wav`，`_build_annotation`平均分配时间。此记录不改变旧评分；新声学实验拒绝此标注来源。

## 已有医生声纹校准：可复用，但未获质量放行

`app/api/speaker_profiles.py`与`app/services/asr/speaker_profiles.py`已经实现医生声纹登记、CAM++ embedding和说话人相似度匹配，不必重新创建同类模块。

仍需验证：

1. 最少8秒检查调用`_audio_duration`，当前是整段文件时长，并非VAD计算的有效语音；8秒静音不能因此视为合格。
2. 医生匹配后，唯一剩余说话人被`_lock_doctor_assignment`提议为患者；“医生＋家长、患儿未发言”反例必须保留。
3. 相似度只取最大者，未检验第一、第二名间隔；相似声线、重叠与错误聚类的误认率需要校准。
4. 已有声纹匹配按完整音频片段工作，不能当作实时声纹识别已经通过。
5. `speaker_role_classifier`可选LLM结果封顶0.88，策略校准为0.86且自动门槛0.90；这条分支不能自动通过。修复需要重新验证置信契约，不降低既有门槛换取通过。

本次不修改以上生产行为。一次医生校准可以减少重复确认，但说话人身份、医患角色、症状属于谁仍是三个不同问题。

## 事件和评分契约

影子JSONL每行是一次**实际观察**：

```json
{"session_id":"synthetic-control","clock":"capture_relative_monotonic_ms","observed_ms":2500,"segment":{"segment_id":"s1","revision":1,"provisional":false,"start_time":0,"end_time":2,"text":"接口控制文本","speaker_id":"streaming","role":null}}
```

- 同一个采音相对单调时钟；不能把服务器Unix时间减客户端相对时间。
- 同一segment的修订递增。重复幂等忽略、迟到旧版本忽略、同版本不同内容拒绝、跨会话拒绝。
- 保留首次文字、首次稳定文字和首次可信角色实际到达时间；结束后获得角色不能倒填到录音时。
- 当前角色覆盖从最新快照计算。后续撤回身份会重新计入未解决，但不抹除早先曾出现角色的历史。
- acoustic speaker仅是匿名声音编号；适配器不自动设为医生／患者，不生成临床事实。
- `current_stable_segments_without_accepted_role`是事件完整性计数，不是角色准确率。精度指标没有真值时保持`null`。
- `score_saved_turns`复用现有`evaluate_turns`，要求明确人工／官方声学标注、RTTM SHA、同一音频SHA、时长边界、单文件与单通道；拒绝平均分配的TTS标注及错误裁剪。
- DER/JER依赖`pyannote.metrics`；当前缺少依赖时写明不可计算。评分旧结果不伪造RTF、峰值内存、医患身份准确率。

真实日志、完整转写和模型输出留在`.artifacts`，不提交。生产尚未发出上述影子包装事件；目前测试验证的是适配契约，不能称浏览器实时功能已接通。

## 研究问题、少数候选与Unknown

| 研究问题 | 当前证据 | 下一最小验证 |
|---|---|---|
| U01：2秒分块能否兼顾端到端速度和文字正确 | 10月19日单引擎60秒实验首字2.597秒，未测浏览器／CER | 复用结果；补浏览器同钟指标及人工真值，不重复引擎10／2秒对照 |
| U02：在线分离是否比结束后CAM++更适合本机 | 新候选尚无本机质量／资源证据 | 同一有真值录音，只替换影子分离器，不影响生产角色 |
| U03：一次医生声纹能否减少确认且不误认家属 | 代码已有、真实质量未验 | 医生＋患者正例；医生＋家长、静音登记和相似声线反例 |

候选仅保留现有FunASR基线、diart与NVIDIA Nemotron-3-Diarization。FunASR保留中文ASR，不同时替换；diart使用增量聚类，可调0.5–5秒等待但需隔离旧依赖；Nemotron官方当前模型支持最多8人、100M参数，Linux优先，输入缓冲0.32秒不包括计算。没有本机数据，不给总分、不选择赢家。sherpa-onnx核验到的官方分离例子为离线，不当作现成在线角色方案。

许可证也分层记录：FunASR源码MIT而模型许可单独；diart源码MIT且pyannote权重需各自条款；Nemotron当前模型卡OpenMDW1.1。最终需要锁定具体权重和运行依赖版本；本目录未新增生产依赖。

## 下一次模型Spike协议与停止条件

由主流程先预留单模型资源窗口，恢复原环境方案固定后才执行：

1. **输入门**：找回与现存人工RTTM完全匹配的授权录音；或者核验短录音的原文件SHA、裁剪起止并派生对应标注。未匹配则只做接口测试。
2. **兼容门**：创建独立Linux环境，核对模型许可、精确版本、断网加载、卸载、结果保存重读；一份60秒材料只执行一次。安装或缓存缺失明确停止，不改主机全局Python。
3. **对照门**：保持ASR与输入不变，两个分离器顺序执行；不并行加载模型、不自动重试、不用候选结果作真值。原始speaker、临时角色、医生修订三者分开。
4. **时延与资源**：沿用既有研究目标首字≤4秒、稳定文字p95≤5秒、RTF<1、漏块／重复／乱序0；资源预算先登记，参考旧实验RSS≤5120MiB、可用内存≥2048MiB、积压≤15秒。本机不同模型预算不得事后改为通过。
5. **质量**：同样本固定DER/JER评价的collar及overlap设置，比较边界和混合语句；识别CER、医疗词、否定／数字另报。不用“检测到2人”替代分段正确。
6. **角色放行**：继续遵守Issue #41的自动准确率≥95%、高置信错误0、自动覆盖≥70%；少量Spike只决定继续研究，不能替正式样本量。
7. **停止**：OOM、持续积压、标签串会话、时钟不一致、真值不匹配、输出丢失或许可缺失即停；保留日志，恢复原流程。失败不扩展成训练或换第三种ASR。

现有10月19日实验复用说明：首字10秒组12.686秒、2秒组2.597秒；两组文本有差异、全部角色为空。此结果只支持继续端到端研究。完整性能证据见`docs/evidence/20261019_realtime_latency_spike.md`。

当前**接口最小适配通过**，60秒数据配对和Nemotron基本兼容已核实；其CPU实时目标未过，完整端到端与角色质量Unknown尚未消除，因此整体Research不为PASS，尚无ADAPT／REUSE决策，不安排生产接入。

## 独立Nemotron兼容验证：许可、下载与失败保留

diart默认依赖`pyannote/segmentation`和`pyannote/embedding`；官方页面要求用户登录并接受模型使用／信息共享条件，MIT源码不能替代权重访问条件。本轮没有代用户接受，没有绕行获取权重，也没有把diart装进生产。

Nemotron官方元数据为`gated=false`，权重固定revision `f667ed73aee57d40cc39428eb768b4fd87a0a29e`，许可OpenMDW1.1，分发时保留许可及来源通知。源码与权重不是同一份许可。只下载transformers路线必要的一份权重，未下载.nemo、GGUF或在线示例音频：

| 文件 | 字节 | SHA256 |
|---|---:|---|
| model.safetensors | 396954592 | `c074d86335b3b794f8fa5edc25594558f128bdb3914d27806a3a5a2e44963cb6` |
| config.json | 1458 | `dd795ec07ffa09acf18d231aa3fa8642aa5c521760953754e02559a7413b6873` |
| processor_config.json | 623 | `91726746788a024a2f0f2f699a6c3667f0d74e6a0e9288fc44fe3018e23af68e` |

固定官方transformers源码提交`6df64031b9fa0ecebe50161df8ad42ed8d36595c`（5.23.0.dev0），源码压缩包SHA `49135a328a2d5ce418b462983159780ed5796d7ca6bc45c02d09df742826c496`，仅独立目录覆盖模块搜索路径。原生产5.14.1及主机5.12.1均不含该模型模块。新增独立tokenizers0.23.1 Linux wheel的SHA为`5075b405006415ea148a992d093699c66eb01952bf59f4d5727089a98bda45a4`；无全局安装。

隔离缓存和原始结果位于`D:/MediListen_research/backend-20261106/nemotron`。研究容器复用固定镜像`sha256:a548073f34f99ed7a26252c119047f02991e217d3e832d4e8fc4788aae6a12f1`，`network=none`、只读根文件系统、2CPU、5GiB内存、`/tmp`512MiB可写；没有端口、业务库、密钥或生产模型卷。先与知识研究互斥；没有暂停当前医生入口。

实际结果：类导入成功；随后一次processor初始化在44.288秒失败，RSS峰值450.41MiB，`model_load_count=0`、推理0次。错误是librosa/numba缓存定位失败：`cannot cache function '__o_fold': no locator available`。保留`output/compatibility.json`和退出容器，不改为模型质量失败；下一最小验证仅将Numba缓存指向可写tmpfs，先检查processor，不重试全量模型。另一次评分依赖获取出现PyPI TLS EOF，已下载文件保留，无DER/JER结果。

在主流程明确授权后，只增加`NUMBA_CACHE_DIR=/tmp/numba-cache`，其他隔离条件不变。无权重processor验证通过（2.539秒），随后新容器完成一次权重加载和两段顺序输入；首失败文件不覆盖，结果保存至`output/compatibility-r2.json`。

| 同一实例、固定CPU配置 | 10秒兼容输入 | 完整60秒输入 |
|---|---:|---:|
| 单次权重加载 | 3.524秒 | 复用同一实例，未再次加载 |
| 计算耗时 | 9.263秒 | 135.708秒 |
| 仅计算RTF | 0.926 | **2.262，未达小于1目标** |
| 单块计算p95 | 2.121秒 | 3.711秒 |
| 进程RSS峰值 | 868.5MiB | 1029.0MiB |
| 输出片段／匿名speaker数 | 6／2 | 32／2 |

这是快速送入已有音频的分块计算，不含真实采音节奏与网络，不是端到端稳定文本时延。1040ms仅为输入缓冲，不能将它宣传成实际角色到达时间。容器完成后`exited`、`OOMKilled=false`，未修改或停止医生服务。

对保存的60秒结果使用`score_saved_turns`及项目原评分器，边界容差0.5秒：边界F1为0.4444、混合语句比例0.125、最佳映射标签一致性0.8783。对应旧CAM++同音频历史结果分别为0.5294、0.2857、0.8838；新结果混合片段减少，但边界F1下降，不能用单项改善宣布整体更优。旧速度记录并未使用本轮2CPU配置，不做公平速度排名。此处的`role_consistency`是旧评分器字段名，实际衡量匿名speaker映射一致性，**不是医患身份准确率**。

DER/JER仍为`null`：research环境缺`sortedcontainers`等评分依赖，主机缺`pyannote.metrics`。没有为获得数字自制替代公式，也未据候选输出修改RTTM。原评分器保存结果评分为零新增模型调用。当前结论为**基本兼容可运行，固定2CPU实时研究目标失败，整体研究保持NEEDS MORE EVIDENCE**；不自动调线程数、换GPU或扩大样本。

完整性代理已独立只读复核实际执行器：固定本地输入、单次加载、计算速度口径、缺失DER、角色与患者主体不推断及失败保留未发现新增阻断。该审查不代替真实角色质量或产品发布验收。

`nemotron_compatibility.py`预注册一次加载、先10秒，再在时间预算允许时复用同实例处理60秒；离线分块计算速度不冒充浏览器实时延迟。医患角色和患者事实主体准确率始终单列，不由匿名speaker聚类推导。

## 参考资料

- [FunASR官方代码及独立模型许可](https://github.com/modelscope/FunASR)
- [FunASR实时通信协议](https://raw.githubusercontent.com/modelscope/FunASR/main/runtime/docs/websocket_protocol_zh.md)
- [diart官方增量分离、安装与模型条款](https://github.com/juanmc2005/diart)
- [NVIDIA Nemotron-3-Diarization官方模型卡](https://huggingface.co/nvidia/Nemotron-3-Diarization)
- [固定Nemotron权重清单](https://huggingface.co/nvidia/Nemotron-3-Diarization/tree/f667ed73aee57d40cc39428eb768b4fd87a0a29e)
- [OpenMDW1.1许可](https://openmdw.ai/license/1-1/)
- [Transformers原生流式说话人分离](https://huggingface.co/docs/transformers/en/model_doc/nemotron3_diarization)
- [pyannote分段权重访问条件](https://huggingface.co/pyannote/segmentation)
- [pyannote嵌入权重访问条件](https://huggingface.co/pyannote/embedding)
- [sherpa-onnx明确为离线的说话人分离例子](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/offline-speaker-diarization.py)
