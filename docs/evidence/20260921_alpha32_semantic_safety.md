# Alpha 3.2 临床语义安全与本地模型证据

> 工程验证证据。240条均为合成语句，不含患者数据，不是临床有效性证据。

## 结果

| 项目 | Before | After |
|---|---:|---:|
| 对照语句 | 240 | 240 |
| 精确通过 | 24（10.00%） | 240（100.00%） |
| 缺失事实 | 160 | 0 |
| 无依据事实 | 30 | 0 |
| 医生问句泄漏 | 26 | 0 |
| 主体错误 | 46 | 0 |
| 时间错误 | 46 | 0 |
| 确定性错误 | 46 | 0 |
| 数值/单位错误 | 0 | 0 |
| 危险极性翻转 | 0 | 0 |

数据集为`data/semantic_safety/clinical_assertion_v1.jsonl`，SHA256：
`7740b320f06b2f7df801052d6be5522eb4451c7463e79f33863d822c3fdfa82e`。

## 真实本地模型

- Provider：`ollama`，无Mock、云端或固定文本回退。
- 模型：`qwen3:4b`。
- 摘要：`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`。
- 输入：已匿名的2.1真实麦克风转写句，内容SHA256为
  `214ac7f07d47c7a9770684e1f2b910737a94c85b8a7009e388164ca0b83976aa`。
- 本次热模型字段抽取耗时：7.187秒。
- “没有药物过敏史”保持否定，状态为`complete`。
- 候选方向由确定性发热/呼吸规则包生成：`FEVER_RESP_V1_FEVER_WORKUP`、
  `FEVER_RESP_V1_PULMONARY_INFECTION`；两者均有关联患者事实及来源引用，仍为待医生确认。
- 主诉和伴随症状仍有两个证据冲突字段；因此本轮不能宣布3.2或Alpha语义门禁通过。

## Gate

- 语义规则Spike：**PASS**。
- 本地Provider链路：**PASS / ADAPT**。
- Alpha Semantic Gate：**NEEDS MORE EVIDENCE**。

仍缺一份通过角色门禁的双人真实ASR输入、独立冻结语义集和字段级完整验收。本证据不支持自动诊断、治疗建议或处方。

## 可重复验证

- 语义数据集重新生成后的SHA256与冻结文件一致。
- 语义安全、字段grounding、本地闭环和病历API定向回归：90 passed、4 subtests passed。
- 完整回归：522 passed、8 subtests passed。
- `node --check static/doctor.js`、`git diff --check`与Python编译检查通过。
- `/health`返回`ok`，CI演示配置下`/ready`返回`ready`；该Smoke不替代真实本地Provider就绪证据。
- 敏感文件检查未发现音频、数据库、模型权重、密钥或身份数据进入提交。

机器可重算结果见[同名JSON](20260921_alpha32_semantic_safety.json)。
