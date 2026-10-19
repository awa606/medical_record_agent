# 2026-10-20 音频标识脱敏误伤：定位、修复与验收

## 当前结论

8798的e1版本在真实授权音频验收中出现“身份确认保存成功，但继续生成报`Transcript not found`”。本轮已确认是**响应脱敏破坏音频资源标识**，原音频和转写文件仍在，且关联一致；失败发生在创建任务和调用DeepSeek之前。

代码已完成限定范围修复和124项定向回归。**完整回归、修复镜像、实际部署及同版本音频闭环仍为PENDING，不能记为故障已在运行版修复。** 本次不改变模型、提示词、七字段结构、业务数据库或审核门禁。

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

## 5．尚待验收与放行边界

| 项目 | 状态 | 下一最小验证 |
| --- | --- | --- |
| 真实故障定位 | 已确认 | 保留E16原失败，不删除会话或转写 |
| 定向回归 | PASS | 124项通过；不作为完整回归或临床质量结论 |
| 完整pytest及CI | PENDING | 按最终修复提交执行，记录实际结果 |
| 镜像与部署 | PENDING | 锁定修复SHA、核对生产差异，备份后升级并保留e1回退 |
| 8798现有E16续接 | PENDING | 通过可见页面恢复同一会话／角色，确认真实资源ID正确；明确操作一次生成，不自动重试 |
| 同版本音频闭环 | PENDING | 首次字段、规则拦截与人工修改分开记录，再保存、审核、导出、重开并核对调用次数 |
| 恢复材料 | PENDING | 对应修复版更新清单并验证，不能用e1旧包替代新版本恢复 |
| 正式放行 | 未放行 | 5.1保持VERIFY，5.3不启动；物理录音和实际缩放保留各自版本边界 |

只提交完成且通过验证的代码与匿名证据摘要。原音频、数据库、原始模型诊断、身份映射和凭据均留本机；本批修复不会把既有医生修订结果重新计为模型首次正确。

## 6．本机证据索引

以下文件位于项目内`.artifacts/demo-sprint-20261019-final/`，路径仅用于本机核验：

- `audio-e16-asr-before-role-20261020.png`、`audio-e16-transcript-not-found-20261020.png`：实际转写及失败界面。
- `calls-8798-audio-before-20261019.json`、`calls-8798-E16-before-role-20261020.json`、`calls-8798-E16-transcript-not-found-20261020.json`：调用、费用及数据库计数。
- `E16-session-before-role-20261020.json`、`E16-transcript-association-failure-20261020.json`：保存前状态、保存后文件关联及角色质量。
- `E16-opaque-id-anonymization-pure-repro-20261020.json`：不访问应用数据库或模型的内存复现；同时证明真实文本仍应脱敏。
- `privacy-audio-id-red.log`、`privacy-audio-id-green.log`：红测试及124项定向回归原始输出。
- `privacy-audio-id-full.log`：完整回归执行日志；本文件编写时尚未结束，**不能据日志存在宣称通过**。

此前展示、知识管理与运行恢复证据见[10月19日验收记录](20261019_demo_sprint_acceptance.md)。该记录中的原版本结果不覆盖本次新发现的e1失败。
