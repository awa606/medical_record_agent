# 2026-10-20 音频标识脱敏误伤：定位、修复与验收

## 当前结论

8798的e1版本在真实授权音频验收中出现“身份确认保存成功，但继续生成报`Transcript not found`”。本轮已确认是**响应脱敏破坏音频资源标识**，原音频和转写文件仍在，且关联一致；失败发生在创建任务和调用DeepSeek之前。

修复已锁定提交`ab8b0c5a1084b8378f58f96278a228a95778972d`，124项定向回归及完整pytest均通过，修复镜像的独立ASGI检查通过。**00:31:16已升级8798；原E16复用已有转写完成一次生成、人工修订、审核导出及工作台重开，资源标识故障已在这条实际路径修复。** 本次不改变模型、提示词、七字段结构、业务数据库或审核门禁。

首次草稿仍有缺失和引用冲突，人工处理后的流程成功不等于模型首次质量通过。CI、重启持久化及8797新快照关联已核验通过；新SHA完整三路径与独立恢复尚未齐全，当前交付为审核候选，5.1保持VERIFY。本轮实际操作者为助手，使用测试账号完成人工修订及审核流程，不是真人医师参与或临床签署。

## 1．实际失败及保留证据

| 项目 | 已核实事实 |
| --- | --- |
| 环境 | 8798，运行`e1a8bce2fac2fdf1f57e51580899ed6e712326bb`；不是19003隔离恢复库 |
| 输入 | 原库匿名患者14的新就诊E16，已有授权60秒WAV；与历史隔离候选同号E16不是同一记录 |
| 转写 | 页面出现21个片段；保存前会话状态`stream_ready`，无病历任务 |
| 角色确认 | 页面将A确认为患者、B确认为医生，保存请求返回200；落盘会话变为`reviewed`，角色质量为`passed` |
| 失败 | 保存身份后自动继续正式生成，请求返回404及`Transcript not found`；没有新建任务或病历版本 |
| 文件核验 | 会话、会话结果和音频转写中的`audio_id`一致；转写文件存在；`result.json`与转写JSON各24745字节，SHA-256一致 |
| 调用与费用 | 00:05:29角色确认前及00:06:39失败后，与23:42起点相比，新增模型调用0、费用0、任务0、Revision 0、批准0、导出0；仅新增待输入就诊E16 |

本例会话ID为`fbdb8465b84d4b789de77f8933ee88f4`，真实音频资源ID为`253b9c625940408081798193e500f717`。它是系统生成的UUID4，不是患者身份信息；其中18位连续数字被原脱敏规则误识别为身份证，从而将响应中的标识改为`253b9c[已脱敏-身份证-…]e500f717`。

原文件、失败截图、会话和首次失败记录保留。未通过重新上传、更换患者或重复模型调用掩盖错误；本例没有进入模型生成阶段，不能作为DeepSeek字段质量失败样本。

## 2．调用链与原因

1. `app/api/asr_sessions.py`的`update_asr_session_result()`保存角色后的会话结果及转写，返回包含`audio_id`、`session_id`和`asr_result`的JSON。
2. `app/services/privacy.py`的`AnonymousResponses`在ASGI响应边界调用`_anonymous_json_body()`与`anonymize_payload()`。原实现只对少数64位摘要作例外保护，其他字符串递归进入`anonymize_text()`。
3. 身份正则只排除数字相邻边界，没有区分中文原文与UUID技术字段。UUID中`625940408081798193`匹配18位数字，写入身份映射后被替换；已有同段映射也会再次触发替换。相同问题影响JSON及SSE中的资源ID，以及包含该ID的资源URL。
4. `static/doctor.js`的`saveRoleReview()`使用返回的`response.audio_id`覆盖`currentAudioId`，随后`startRecordGenerationFromAudio()`用该ID发起请求。
5. `app/api/audio.py`的`generate_record_from_audio()`先调用`_read_transcript()`；损坏ID无法对应原转写文件，直接404。此时尚未检查Provider、创建任务或调用模型。

这解释了“转写看得见、身份保存成功，生成却说找不到转写”。问题位于响应序列化与资源关联，不是转写丢失、角色未确认或模型理解能力。

## 3．最小修复边界

仅在`anonymize_payload()`处理明确技术字段时保留匹配值：

| 字段 | 允许原样保留的完整格式 |
| --- | --- |
| `audio_id`、`session_id`、`live_session_id` | 小写32位UUID4 hex，含版本4及RFC 4122变体限制 |
| `media_url` | `/api/audio/<UUID4 hex>/media` |
| `events_url` | `/api/asr/sessions/<UUID4 hex>/events` |
| `result_url` | `/api/asr/sessions/<UUID4 hex>/result` |

URL必须完整匹配本地既有路由，不接受外域、查询参数、fragment或额外路径。不全局豁免UUID、任意`id`字段或任意URL；`request_id`等不在本次范围。正文、患者姓名、联系方式及无效技术值继续执行原脱敏规则，原有摘要保护保持不变。

不删除身份映射，不改写原转写，不根据错误ID猜测文件，不关闭脱敏中间件。访问日志原有脱敏方式不变；该修复保护业务响应中资源关联所需的确切值。

## 4．回归过程与结果

### 先保留失败

新增`tests/test_privacy_audio_identifiers.py`，在临时数据库和上传目录中使用同一匿名UUID，覆盖新映射和已有映射。修改生产代码前运行结果为**3失败、45通过，6.44秒**：

- 新映射和已有映射两种状态下的JSON／分块SSE组合测试失败；首个失败断言均是JSON中的标识被改写，修复后两种响应均单独核对。
- 完整ASGI链中，真实角色保存接口返回200及`passed`；测试直接取返回的`audio_id`调用真实生成接口，复现404 `Transcript not found`。
- 非技术正文、非法ID以及越界URL的原脱敏保护用例通过。

链路测试仅替换Provider可用性边界及后台生成执行，真实执行角色保存、响应中间件、转写读取和任务创建代码；没有调用ASR或在线模型。测试生成结果不能作为真实模型验收成绩。

### 修复后定向验证

```powershell
python -X utf8 -m pytest tests/test_privacy_audio_identifiers.py tests/test_privacy_revision_hash.py tests/test_privacy_deployment_metadata.py tests/test_privacy_concurrency.py tests/test_audio_api.py tests/test_asr_sessions_api.py -q --disable-warnings
```

结果为**124通过，24.44秒**。角色响应中的原ID能够找到同一转写，进入一次任务创建；后台测试替身接收原转写和已确认角色。正文PII、非法标识、外域和附加参数仍被处理；既有Revision摘要、部署版本及并发脱敏检查通过。`py_compile`和`git diff --check`通过。

### 完整回归与镜像检查

完整pytest已结束：**1134通过、3跳过、1条警告、8个subtest通过，682.91秒**。这些是工程回归结果，不合并成模型准确率或临床安全结论。独立静态审阅未发现阻断项；对应ab8提交的[CI 39284314530](https://github.com/awa606/medical_record_agent/actions/runs/39284314530)为`completed / success`，结果文件更新时间为00:37:52。

修复镜像ID为`sha256:300325caeca7b5060533e005d3ec675b77185a159ae0bc7820439089af20d3cb`。与e1运行基线逐项比较234个生产文件，232个不变，仅`app/services/privacy.py`及`static/deployment.json`变化；`pip check`通过。模型、提示词和前端业务脚本未随镜像改变。

在新镜像中以只读根文件系统、临时`/tmp`和禁用网络运行独立ASGI探测，不挂载生产runtime或凭据：新／已有身份映射各检查JSON与7字节分块SSE，共**4个场景、44项检查通过**。技术标识及严格本地URL保持准确，正文身份证样式文本和电话仍脱敏。网络尝试0、真实模型调用0；该检查没有启动正式业务服务，不能替代8798部署后的可见操作验收。

## 5．8798部署与E16续接结果

2026-10-20 00:31:16，经既有升级流程将修复镜像登记到8798正式启动配置；原runtime和Cookie保留，没有复制新库或改动8795入口。FunASR冷启动预热期间就绪检查503，预热后200；不将这段过程写成持续就绪。e1旧镜像、原配置和升级前一致性备份保留。

E16沿用e1已完成的同一授权60秒音频、21段转写及人工确认角色，没有重新上传或重新识别。修复后通过页面继续生成，记录如下：

| 阶段 | 实际结果 | 解释边界 |
| --- | --- | --- |
| 正式生成 | 任务13，Rev20／#1；DeepSeek调用1次、6042毫秒、自动重试0 | 修复恢复资源关联，没有改变模型能力 |
| 首次字段校验 | 3项完整、3项缺失、1项冲突；主诉缺失，伴随症状的短引文“没有”匹配多个片段 | 校验冲突指证据定位不唯一，不代表患者陈述互相矛盾；安全检查阻断、不能导出 |
| 人工修订 | 通过可见编辑操作修改主诉、现病史、伴随症状；伴随症状按医生补录声明处理，保存Rev21／#2 | 新内容明确人工来源；原模型结果及错误引用保留在Rev20，不算模型首次正确 |
| 分项审核 | 批准9绑定Rev21；5项内容确认，过敏史和查体按缺失接受 | 接受缺失不等于否认、正常或已询问；新版本保存时的`pending`快照与后续批准记录分开 |
| 导出及重开 | 导出11绑定批准9和Rev21；工作台重开恢复21段、#2和已导出状态 | 这是同一原库E16，不能与隔离候选同号病例混用 |
| 知识与帮助 | 实际“查依据”返回5条，包括《病历书写基本规范》及流感2020资料；内嵌帮助正常打开关闭 | 流感2020明确为旧版，不称最新指南；本次查询不替代完整检索评测 |

DOCX内容核对为**26／26段与批准版本投影一致**，1937字节，SHA-256为`041c2407c0b733218e0fffa6e9a4a7be0e46f0a90aa3ac4fcb17dd697e5864ed`；Markdown投影、七字段批准、就诊／任务／版本／批准／导出关联均通过。服务端副本经LibreOffice 26.2.4.2和Poppler渲染为2页A4，逐页查看中文可读、七字段齐全，无截断或重叠；第二页仅候选诊断与安全摘要、留白较多，记录为非阻断改进，不在本次改文件。**浏览器下载和Word原生打开未验证。** 导出事件保存路径而非历史文件哈希，同任务文件名可能被后续导出覆盖，因此本轮哈希另存证据。

8797于**00:38:43**从实际8798源库刷新ab8只读快照：14患者、16就诊、12个关联任务、21个病历版本、9条批准、11条导出；4份文档、78片段及78条索引元数据。源库有13个任务，快照只保留白名单患者关联任务，不将两者数量混写。通过实际浏览器登录并沿E16→导出11→Rev21／批准9查看；独立ASGI检查认证后读取、排序分页和关联成功，匿名访问、任意SQL、整库下载及写入被拒绝，敏感账号表不存在；刷新和读取不改源库／旧快照，模型调用0。

00:44:04.839的重启后核验通过：**12张表、E16相关8个文件及费用账本指纹与重启前一致**，镜像、版本、runtime挂载保持ab8；活动任务和ASR会话均0。页面刷新E16仍恢复21段、#2及已导出状态，重启新增生成0。冷启动预热不就绪与后续恢复分开记录，不据一次重启推断长期稳定。

E16本次生成增量为**1次、0.008396元**，共享账本累计**16次、0.299696元**，均为内部估算，不是服务商最终账单；20元预算不变。首次失败前后的调用增量0事实仍保留，不能与修复后的1次调用混算。

以上证明已有音频结果在修复版本中可以继续完成审核流程，**没有重新执行ab8的物理采集或ASR，也没有完成新版本全部三路径验收**。19日22:00冻结目标未达成；两次Docker中断原因、23:35 TLS失败的稳定复现与根因仍未解决，随后恢复不删除这些失败事实。

## 6．尚待验收与放行边界

| 项目 | 状态 | 下一最小验证 |
| --- | --- | --- |
| 真实故障定位 | 已确认 | 保留E16原失败，不删除会话或转写 |
| 定向回归 | PASS | 124项通过；不作为完整回归或临床质量结论 |
| 完整pytest | PASS | 1134通过、3跳过、1警告、8个subtest通过；682.91秒 |
| CI | PASS | ab8对应39284314530为completed／success，不沿用旧e1成绩 |
| 修复镜像 | PASS（隔离检查） | 234文件差异核验、依赖检查、4场景44项ASGI检查通过；没有启动正式业务服务 |
| 8798部署 | PASS | 00:31:16登记ab8，原runtime保留；预热503后200，e1回退保留 |
| 8798现有E16续接 | PASS | 同一转写进入任务13，一次生成；人工修订为Rev21／#2、批准9、导出11，重开正常 |
| 首次模型质量 | 未通过完整质量门 | 3完整／3缺失／1冲突，仍需人工处理；不把修订后的成功算作首次正确 |
| 新版完整三路径 | PENDING | 已有ASR结果的续接不替代ab8从输入开始的全部三路径；历史麦克风和缩放保留各自SHA |
| 8797刷新与关联 | PASS | 00:38:43采样ab8，实际E16→导出11→Rev21／批准9；只读及权限检查通过 |
| 8798重启持久化 | PASS | 12表、8文件、账本及版本一致；页面刷新恢复21段、#2和已导出，新增调用0 |
| 导出文件 | PASS（服务端副本） | 26段与批准投影一致，2页A4可读；浏览器下载及Word原生打开未验证 |
| 恢复材料 | PENDING | 对应修复版更新清单并验证，不能用e1旧包替代新版本恢复 |
| 正式放行 | 未放行 | 5.1保持VERIFY，5.3不启动；物理录音和实际缩放保留各自版本边界 |

只提交完成且通过验证的代码与匿名证据摘要。原音频、数据库、原始模型诊断、身份映射和凭据均留本机；本批修复不会把既有医生修订结果重新计为模型首次正确。

## 7．本机证据索引

以下文件位于项目内`.artifacts/demo-sprint-20261019-final/`，路径仅用于本机核验：

- `audio-e16-asr-before-role-20261020.png`、`audio-e16-transcript-not-found-20261020.png`：实际转写及失败界面。
- `calls-8798-audio-before-20261019.json`、`calls-8798-E16-before-role-20261020.json`、`calls-8798-E16-transcript-not-found-20261020.json`：调用、费用及数据库计数。
- `E16-session-before-role-20261020.json`、`E16-transcript-association-failure-20261020.json`：保存前状态、保存后文件关联及角色质量。
- `E16-opaque-id-anonymization-pure-repro-20261020.json`：不访问应用数据库或模型的内存复现；同时证明真实文本仍应脱敏。
- `privacy-audio-id-red.log`、`privacy-audio-id-green.log`：红测试及124项定向回归原始输出。
- `privacy-audio-id-full.log`：完整回归原始输出，1134通过、3跳过、1警告及8个subtest通过；先前PENDING状态已由完成结果替换。
- `privacy-audio-identifiers-independent-review.json`：独立静态审阅，生产者UUID约束、字段范围、正文保护及既有摘要分支核验，无阻断项。

新镜像、部署与续接证据位于`.artifacts/audio-id-hotfix-20261020/`：

- `release-ab8b0c5a1084/image-verification.json`：精确镜像及234文件比较；`image-asgi-result-ab8b0c5a.json`：4场景44项独立ASGI结果。这两项不代替正式操作验收。
- `backup-before-upgrade/backup-safe-summary.json`及`release-ab8b0c5a1084/upgrade-8798/promotion-20261019T163116Z-7e09d9/result.json`：一致性备份摘要与00:31:16正式登记结果。
- `calls-E16-before-generation-ab8b0c5a.json`、`calls-E16-after-first-generation-ab8b0c5a.json`：运行镜像、调用和数据库计数。
- `E16-first-generation/first-generation-safe-summary.json`：首次字段、规则拒绝、耗时和费用；原响应仅留本机同目录。
- `E16-first-vs-doctor-safe-summary.json`：三字段人工修改、不可变保存版本与后续批准状态的区分。
- `E16-docx-approved-revision-verification.json`：26段、文件SHA及关联核对；`E16-export/render-review.json`：两页实际渲染检查及留白限制，浏览器下载未验证。
- `E16-first-draft-ab8.png`、`E16-export-success-ab8.png`、`E16-history-reopened-ab8.png`、`E16-knowledge-evidence-ab8.png`：首次草稿、导出、重开与知识查询截图。
- `viewer8797-execute-ab8.json`、`viewer8797-readonly-ab8.json`：00:38:43新快照、来源与只读权限核验；`viewer-E16-relations-ab8.png`、`viewer-E16-export-chain-ab8.png`：实际关联操作。
- `restart-before-source-readonly.json`、`restart-after-source-readonly.json`、`calls-E16-final-after-restart-ab8b0c5a.json`及`E16-after-restart-ab8.png`：重启前后指纹、账本及页面恢复。
- `ci-ab8-success.json`：对应修复提交的CI完成结果。

此前展示、知识管理与运行恢复证据见[10月19日验收记录](20261019_demo_sprint_acceptance.md)。该记录中的原版本结果不覆盖本次新发现的e1失败。
