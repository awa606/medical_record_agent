# 发热/呼吸道疾病包来源追溯说明

本文记录 `fever_respiratory_v1` 候选诊断参考所关联的外部来源。来源链接已核对，但规则与来源之间的医学映射仍标记为 `needs_medical_review`；链接存在不代表规则已通过临床验证。

## 数据边界

- 对话中的 `SourceSpan` 说明“这条候选参考由哪段问诊内容触发”。
- `ClinicalReference` 说明“规则设计参考了哪些公开权威资料”。
- 两者都不能把候选参考升级为最终诊断。
- 处方、用药选择和最终诊断仍由医生完成。

## 首批来源

| 编号 | 来源 | 版本/日期 | 当前映射范围 |
| --- | --- | --- | --- |
| `NHC_FLU_2025` | [国家卫生健康委、国家中医药局《流行性感冒诊疗方案》](https://www.nhc.gov.cn/ylyjs/zcwj/202501/f8fcecca59a048bebc4a71847ce57594/files/1741764832851_94226.pdf) | 2025年版，2025-01-22 | 流感临床表现、分型和重症风险复核 |
| `CDC_FLU_SIGNS_2026` | [CDC Clinical Signs and Symptoms of Influenza](https://www.cdc.gov/flu/hcp/clinical-signs/index.html) | 2026-02-04 网页修订 | 流感样症状及症状不能单独确诊的边界 |
| `NICE_NG250_2025` | [NICE Pneumonia: diagnosis and management](https://www.nice.org.uk/guidance/ng250) | NG250，2025-09-02 | 成人肺炎评估、诊断和管理 |
| `WHO_SARI_TOOLKIT_2022` | [WHO Clinical care of severe acute respiratory infections – Tool kit](https://www.who.int/publications/i/item/clinical-care-of-severe-acute-respiratory-infections-tool-kit) | 2022-04-06 | 严重急性呼吸道感染评估和分诊 |

## 当前未完成

- 尚未由临床专家逐条审核规则与指南章节的映射。
- 产品化医生工作台尚未展示 `references` 字段。
- 尚未加入来源失效、版本更新和定期复核任务。

在完成以上三项前，本能力只用于课程演示、工程可追溯和医生复核提示。
