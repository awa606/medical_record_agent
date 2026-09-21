# WBS 3.2 临床事实、本地模型与候选诊断 Engineering Design Review

## 1. Goal

把通过角色门禁的转写转换为证据可追踪、可冲突阻断、可由医生逐项审核的结构化病历草稿；本地Qwen负责字段抽取，确定性事实层负责临床语义与候选方向安全边界。

## 2. Non-goals

不做自动确诊、治疗方案、处方、相似病例库、疾病范围扩展、模型训练、Jetson验收或企业临床发布。

## 3. Inputs and Outputs

- 输入：匿名转写、segment/role、Provider配置、知识来源版本。
- 输出：`MedicalRecordFields`、临床事实、证据span、冲突状态、待医生确认的候选方向与引用、运行追踪。

## 4. Constraints

- 无合法医院训练数据；合成集只用于安全回归。
- 公共HTTP API和数据库Schema保持兼容。
- 所有非空患者字段必须有原文证据；医生问题和家属事实不能变成患者事实。
- 本地模型失败时严格模式Fail closed。

## 5. Architecture

```text
ASR segment + role
  -> LLMProvider(DeepSeek baseline / Ollama Qwen candidate)
  -> JSON Schema + Pydantic
  -> ClinicalFact assertion/experiencer/temporality/certainty
  -> extractive grounding + conflict gate
  -> fever/respiratory deterministic candidate pack + references
  -> deterministic draft renderer
  -> doctor review / revision
```

## 6. Module Boundaries

- `ollama_provider.py`：只负责结构化字段生成，`candidate_diagnoses=[]`。
- `clinical_facts.py`：事实语义、证据身份与发热/呼吸候选输入。
- `field_grounding.py`：检查引用、角色、否定、主体、时间、确定性、数值和单位。
- `fever_respiratory_pack.py`：限定病种的候选方向和知识引用。
- `llm_record_generator.py`：组合Provider字段与确定性候选，不改变公共接口。
- `record_rules.py`：确定性草稿与最终安全门禁。

## 7. Clinical Fact Contract

事实至少包含：`type / name / assertion / experiencer / temporality / certainty / value / unit / evidence / evidence_span_id / review_status`。

`assertion`为`present / absent / uncertain / resolved`；`experiencer`明确patient/family；医生问句没有患者回答时不产生患者事实。所有事实默认`review_status=pending`。

## 8. Provider Interface

保留`LLMProvider.generate_fields_json → LLMProviderResponse`、`MedicalRecordFields`及现有业务路由。在线DeepSeek只作受控比较基线；本地候选为Ollama＋固定摘要Qwen3:4b。迁移不涉及DeepSeek权重转换。

## 9. Knowledge and Candidate Diagnosis Boundary

候选方向必须同时具备患者事实证据和版本化知识引用，状态始终为“候选/待医生确认”。知识引用不能代替患者事实；历史病例库未获授权前保持BLOCKED。治疗与处方不在本模块输出。

## 10. Storage and Traceability

继续使用现有Task、Revision、Evidence和Knowledge表。事实ID与SourceSpan随字段保存；模型Provider、模型摘要、fallback、延时和字段校验保存在运行追踪中。本轮不增加数据库迁移。

## 11. Privacy and Security

模型输入先匿名化；严格模式禁止Mock、云端和未披露回退。原始音频、患者数据、模型权重与运行数据库不进入Git。Prompt注入文本只作为数据，不能改变规则。

## 12. Failure Behavior

- 无引用、角色未确认、极性/主体/时间/确定性/数值冲突：字段`conflicting`并阻止审核。
- Provider不可用、Schema非法、超时或OOM：当前任务失败，不伪造草稿。
- 知识引用缺失：候选方向不得提升为已确认诊断。
- 关键禁忌信息缺失：治疗能力保持关闭。

## 13. Test and Acceptance Strategy

- 240条合成安全集：危险语义错误全部为0。
- 本地Qwen Smoke：真实Provider、固定摘要、结构化输出、fallback 0。
- 一份通过角色门禁的真实ASR结果：字段、证据、候选与草稿闭环。
- 完整pytest、前端语法、health/readiness、敏感文件检查。
- 3.2只有全部原验收满足才可DONE；代码完成但真实双人输入未完成时停在VERIFY。

## 14. Rollout and Rollback

先在DEV-01以候选版本运行，对同一冻结输入比较在线基线和本地Qwen。若出现危险语义错误或字段质量退化，停止提升本地模型、关闭候选诊断/治疗参考并回退到“转写＋草稿＋医生审核”。每次只替换一个Provider或规则层。

## 15. Risks, Dependencies and Estimate

- 主要风险：合成集覆盖不足、真实对话角色/断句误差、模型字段改写导致证据冲突。
- 依赖：2.3角色门禁与3.1工作流已DONE；Knowledge V1可复用。
- 6h只覆盖Alpha整合与最小安全Spike；训练、医院数据和企业验证进入后续支线。若验收未完成，记录R11并停在VERIFY。

## Fixed Five Questions

1. **如何拆分？** Provider抽取、事实语义、证据门禁、候选规则、医生审核分别验证。
2. **哪些替代方案未采用？** LLM-only、立即LoRA、新临床NLP框架和自动治疗输出。
3. **最可能失败在哪里？** 真实多说话人转写后，字段改写与原文证据不一致。
4. **最低成本验证是什么？** 240条合成语义集＋1条真实本地Qwen输入＋1条真实角色门禁输入。
5. **如何证明完成？** 可重算指标、模型摘要、fallback=0、事实/引用完整及医生审核门禁。

## Gate

**Design Review Gate: PASS**。设计边界、失败行为、验收和回退明确；这不表示3.2、Alpha Semantic Gate或临床有效性通过。
