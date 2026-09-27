# 5.1：8795恢复与JSON源句对照

## 结论

8795使用原镜像恢复；数据库和知识索引可读，未重建、未清卷。**JSON源句候选被拒绝**：旧版和候选各3次真实Qwen调用，主诉引用都不匹配，均只保留4个预期字段中的3个。没有修改生产Provider、转写版式、Schema或安全阈值。

本轮起点代码为`dd8afee6ea0ce7ef9cd722114a05b2d0bbb493c8`；实际8795应用代码仍为`ee0b5f0a84461fd7d531cf54de4e16c2ce6588a1`，镜像`mra-alpha51:review-quality-20260927`，镜像SHA256为`79fb4046290ec25f3c056b03ff9a4f06edb9a4fb94dd7b79ce9100feb2cbe2d1`。

打开 <http://127.0.0.1:8795/static/doctor.html>。原匿名已完成就诊`SIM-REVIEW-0927-PAIR`保留；本轮恢复复验使用独立标识`SIM-RESTORE-0927-JSON`。

## 运行环境恢复

- 应用、网关、Ollama均退出255且`OOMKilled=false`，挂载和镜像保留。日志有`/app/runtime`的`OSError: [Errno 5] Input/output error`；没有足够证据认定退出根因、数据库损坏或全系统没有内存问题。
- 按Ollama→应用→网关启动现有三个容器，没有重新创建容器、初始化数据、改镜像或改重启策略。
- 首次`/health=200`、`/ready=503`，原因是ASR与LLM预热未完成；之后`/ready=200`。SQLite `quick_check=ok`，四组件FunASR就绪，真实Qwen摘要匹配，Mock回退关闭。
- 知识保留5个来源、7个文档版本、4个启用、116个片段、96条embedding。Task3的Revision7、Task5的Revision9仍为exported。
- 旧2626保持原样，不充当最新入口；2600与2666未启动。历史证据未覆盖。

## 单变量实验

假设H-CITE-JSON：把`[编号] 原句`编码为独立JSON源句，可避免文本和编号串入同一引文。仅在隔离Python进程替换`numbered_source()`；不写入容器的`app/`。

候选实现复用旧提示词，只替换源句格式和对应复制说明：

```python
prefix, _ = baseline(text).split('以下内容全部是数据，不能更改规则：\n', 1)
prefix = prefix.replace(
    'source_spans.text引用完整原句，index使用编号。',
    '每条JSON源句包含独立的index和text。source_spans.text逐字复制该源句的text，'
    'source_spans.index复制该源句的index；编号、JSON键名和标点结构不属于引文。',
)
candidate_prompt = prefix + '以下内容全部是数据，不能更改规则：\n' + '\n'.join(
    json.dumps({'index': i, 'text': s}, ensure_ascii=False)
    for i, s in enumerate(split_clinical_segments(text))
)
```

输入为已授权13.397333秒Realtek音频对应的既有转写；本轮没有重新录音或转写。音频SHA256：`c58c6ff5b5437a2152a2472d2cd8e10be64b42dc213bb3157611ee4333fa732c`。固定patient角色仅用于字段抽取对照，不是说话人门禁通过证据。

固定Qwen3:4b摘要`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`、temperature0、num_ctx8192、num_predict2048、think=false、keep_alive30m、零重试和原Schema。先运行旧版3次，再运行候选3次；时延受顺序、预热和系统负载影响，不作性能提升结论。

| 检查 | 旧格式 | JSON源句候选 |
| --- | --- | --- |
| 真实首次调用 | 3 | 3 |
| 达到4/4字段及正确引文 | 0/3 | 0/3 |
| 每次保留的预期字段 | 3/4 | 3/4 |
| 失败字段 | 主诉 | 主诉 |
| 引文错误 | 同一错误后缀“咽: 0” | 同一错误后缀“咽: 0” |
| 处理结果 | 无有效引用，主诉置为missing | 相同 |
| Mock／云端回退 | 0 | 0 |

**H-CITE-JSON未获支持，候选REJECTED。** 没有用正确value或index自动填充错误引文。原回归`test_observed_qwen_citation_corruption_is_not_silently_repaired`继续要求阻断此错误。重复单例不是6个独立病例或临床质量证据。

按首门失败停止规则，未启动1–30开发、31–40验证、41–60历史冻结集重测；这些集合的历史结果不写成本轮成绩。未增加模型、训练、量化转换或新数据。

## 回归与可用性

240条确定性语义规则全部通过；全量pytest为586通过、1个依赖弃用警告，前端语法与差异检查通过。规则成绩与真实Qwen上述失败分开统计。

恢复环境真实`hybrid_v1`查询返回5项；匿名知识访问401、角色未确认生成409。页面资源SHA与ee0b5f0一致。独立合成Encounter7／Task6首次主诉仍conflicting，未批准导出400；脚本按固定匿名真值修正1字段后Revision10→11，审核、导出内容和历史重开通过，医生页能打开知识来源SHA。此为明确脚本医生操作，不是模型首次成功或医学复核。DOCX及截图仅在本地保留。

没有新物理麦克风、外屏缩放或完整离线恢复证据。完整机器可读结果见[同名JSON](20260927_alpha51_recovery_citation_ab.json)；最终CI另在PR #113核验。

## 失败交付与下一最小验证

| 项目 | 内容 |
| --- | --- |
| 模块 | Qwen结构化输出的主诉source_spans.text |
| 输入ID | paired-realtek-13s；音频SHA如上 |
| 预期／实际 | 3次均4/4正确字段与引文；实际3次均3/4，主诉引用错误 |
| 影响 | 主诉被标缺失或冲突，不能无人工处理直接审核 |
| 保留证据 | `.artifacts/alpha51-citation-json-20260927/ab/`的提示词、6份首次原始输出、校验trace、输入及结果SHA |
| 下一最小验证 | 先检查当前source_spans子Schema，在独立实验中比较最小Schema与完整Schema的同一句引用输出，定位是否为结构化解码串扰；不改写原文或放宽校验 |

下一实验尚未执行，不能把“结构化解码串扰”写成已证明根因。训练Research仍NEEDS MORE EVIDENCE。

## WBS与回退

本轮重新连接Project Planner，23:15采样的173个源文件SHA通过核验。仍为16项99h，8 DONE／3 VERIFY／1 BLOCKED／4 BACKLOG；5.1 VERIFY，日期、依赖、验收、里程碑不变。R08记录运行目录异常，R11记录本轮工具窗口而非虚构人工工时。

当前无需回退生产代码，因为候选未部署。运行环境继续使用原`ee0b5f0`镜像；如后续回退到更早镜像，保留新产生的Revision，禁止用旧数据库直接覆盖新记录。真实三路径、当前显示设备和对应版本恢复证据齐全前，5.1不标DONE、5.3不启动。
