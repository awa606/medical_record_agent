# 5.1 病历核对候选与同病例质量定位

**结论：8795已更新为可操作核对候选；Qwen主诉引用错误已复现，尚未修复。5.1保持VERIFY，不称稳定发布。**

## 打开与体验

打开 `http://127.0.0.1:8795/static/doctor.html`，登录后搜索 `SIM-REVIEW-0927-PAIR`。可重开本轮已保存、审核、导出的合成就诊（Encounter 6／Task 5）。`SIM-DEMO-0929-NEGATION` 保留历史模型错误，不能展示成已审核的可靠结果。

候选代码：`ee0b5f0a84461fd7d531cf54de4e16c2ce6588a1`。镜像：`mra-alpha51:review-quality-20260927`，digest：`sha256:79fb4046290ec25f3c056b03ff9a4f06edb9a4fb94dd7b79ce9100feb2cbe2d1`。由精确Git archive构建；HTML、JS和工作区CSS的HTTP SHA与该提交一致。

- 字段旁直接“修改”，定位到对应输入；切换字段不重置其他修改。
- 页面显示当前Revision、未保存／保存失败／实际保存结果；服务器已接受保存但刷新失败时，禁止重复提交，先核验最新版本。
- 缺失项可以定位；证据冲突提供修正入口，不能勾选绕过。
- 已处理审核项默认折叠，仍可展开复核。
- 409保留本地修改；加载最新版本失败也保留。加载成功后可对照冲突前副本，再明确带入当前版本编辑。
- 医生改过的字段单独标注，不能计作模型首次成功。

本轮不改三栏、转写正文、Provider、数据库或公共接口。旧2626保留；2600／2666未启动。

## 同病例错误定位

固定输入是已授权Realtek真实录音的副本，13.397333秒／48kHz／PCM16／单声道；本轮不是新麦克风录制。音频SHA见[结构化证据](20260927_alpha51_record_review_quality.json)。幅度检查无削波，峰值−0.772dBFS；不能据此声称SNR或多场景语音质量通过。

| 层 | 本轮结果 | 判断与边界 |
| --- | --- | --- |
| 输入 | 原SHA一致，无覆盖原证据 | 排除本次文件错用 |
| ASR | 真实FunASR，RTF 0.4212；转写与用户确认真值一致，CER 0 | 仅单条复用音频；T09不因此通过 |
| 角色 | 单说话人仍未确认；生成API返回409 | 控制实验固定patient身份仅用于抽取对比，未绕过正式角色门禁 |
| Qwen | 人工转写和ASR输入各调用一次；原始主诉value存在，但引用出现“咽: 0”错误后缀 | 错误发生在模型引用输出；两输入原文相同，不能归因于ASR |
| 校验 | 带可信片段的控制实验将主诉丢弃为missing；正式文本API保留为conflicting并阻断 | 是不同输入元数据下的安全处理，不冒充引用修复 |
| 完整性 | 两次控制实验各有4个预期内容字段中的3个留下；现病史、伴随症状、否认药物过敏保留 | Schema合法、零conflicting不等于完整：还必须数missing |
| 工作流 | 正式文本生成首次主诉conflicting；脚本按固定匿名真值修正1字段，保存、审核、导出、重开成功 | 修正后成功与模型首次失败分开；不是医学人员临床复核 |
| 训练 | 未训练、未下载外部语料、未更换权重 | 数据资格和资源Gate仍NEEDS MORE EVIDENCE |

固定Qwen摘要：`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`；Mock／云端回退0。控制实验耗时52.934秒和10.671秒，受到冷热启动影响，不把差异解释为文本类型效果。没有可比DeepSeek真实输出，未制作虚假的在线／本地提升指标。

本轮没有通过改写原文、放宽校验或填充模板消除失败；新增针对该错误引用的回归。下一最小实验是在开发集验证引用输出的单变量修复，再独立复跑验证／冻结集。旧60例、240条规则集保持历史证据，不写成本轮模型成绩。

## 真实页面与部署验证

- `/health=200`、`/ready=200`，真实FunASR四组件及本地Qwen就绪；页面不是样稿注入。
- 更新前用SQLite Backup API备份。更新后11个业务／知识表指纹一致；随后才新增本轮合成验证记录。
- 知识仍为5个来源、7个文档版本、4个启用、116个片段、96条embedding。真实查询返回5项，模式`hybrid_v1`；医生页来源详情可读到内容SHA。
- 匿名知识接口401；未确认角色生成409；未批准导出400。
- 本轮就诊保存前Revision ID 8／版本1，医生修正后ID9／版本2；审核导出DOCX包含“三十八点二度”和“没有药物过敏史”，重开仍为ID9、exported。
- 既有Task3重启后仍为Revision7、exported。没有用知识库覆盖业务库。

回归：完整pytest **585项及8个子测试通过**；最后的编辑来源标注由4项编辑浏览器回归覆盖；新增真实引用错误回归所在文件56项通过。样稿76项通过仅作防退化，不等于真实验收。最终GitHub verify结果在PR #113可追溯。前端语法和差异检查通过。

本地证据目录：`.artifacts/alpha51-review-quality-20260927/`。保留 `before-review.png`、`after-review-same-case.png`、`first-model-conflict.png`、`knowledge-reference.png`、`review-exported-reopened.png`；已检查实际画面。截图没有更新为自动接受的新基线。原音频、原始输出、日志、数据库、导出文件均未入Git。

## 冻结与回退

[转写界面基线清单](../releases/transcription-ui-baseline-20260927.json)记录本轮起点Git SHA和资源哈希；本地有源码副本。截图来自更新前实际部署4c05a89，不冒充完整bdc24c9版本验收。其意义是保留转写布局与操作基线，**不是完整离线冻结包**。

8795回退镜像为 `mra-alpha51:demo-b-bge-4c05a89`，原环境文件在 `.artifacts/alpha51-demo-sprint-20260927/candidate-b.env`。更新前一致性备份为本轮目录的 `before-runtime.sqlite3`。优先只回退镜像、保留现有数据库；若需恢复数据库，必须先备份后来产生的数据，不能直接覆盖新增Revision。

## WBS与未通过项

同轮Project Planner为16项99h，8 DONE／3 VERIFY／1 BLOCKED／4 BACKLOG；5.1 VERIFY，未改原日期、19条技术依赖或4条资源依赖。硬件延期，5.3未启动。

仍需：模型主诉引用问题的受控修复与质量回归、最终版本物理麦克风路径、实际外屏缩放，以及对应版本三路径和新目录新端口恢复验收。本轮没有新的物理录音、实际缩放或完整恢复，因此不标DONE或稳定发布。

数据清单见[训练数据资格](../research/medical_training_data_inventory.md)；交互设计见[Design Review](../design_reviews/20260927_alpha51_record_review_quality.md)。项目专用[mra-engineering-report Skill](../engineering/skills/mra-engineering-report/SKILL.md)已安装本地并校验。
