# 发热/呼吸知识库检索基线

- 生成时间：2026-09-14T12:59:41+08:00
- Git SHA：`71f3f46d0650aa6307cb19da97a5c1d5a249db51`
- 数据集：`fever-respiratory-query-mvp-v1`（20条开发查询）
- 模式：`hybrid_v1`
- Recall@5：**95.0%**（19/20）
- 引用完整率：**100.0%**（100/100）
- 无来源引用：**0**
- 边界：这是20条开发MVP的来源级标签；尚未达到最终120条、40条冻结测试集要求。

| 查询 | 相关来源 | Top-5命中 | 前三结果（来源/页码） |
|---|---|---:|---|
| KQ01 流行性感冒常见的临床表现有哪些？ | nhc-influenza-2020 | PASS | nhc-child-mpp-2025/p.7；nhc-influenza-2020/p.4；nhc-influenza-2020/p.8 |
| KQ02 哪些人属于流感重症高危人群？ | nhc-influenza-2020 | PASS | nhc-covid19-trial-v10/p.11；nhc-influenza-2020/p.6；nhc-influenza-2020/p.9 |
| KQ03 流感诊断需要哪些病原学检查？ | nhc-influenza-2020 | PASS | nhc-influenza-2020/p.9；nhc-influenza-2020/p.8；nhc-influenza-2020/p.6 |
| KQ04 流感患者出现哪些情况需要警惕重症？ | nhc-influenza-2020 | PASS | nhc-child-mpp-2025/p.7；nhc-influenza-2020/p.6；nhc-influenza-2020/p.4 |
| KQ05 流感发热咳嗽头痛肌肉酸痛的表现 | nhc-influenza-2020 | PASS | nhc-covid19-trial-v10/p.4；nhc-influenza-2020/p.4；nhc-influenza-2020/p.3 |
| KQ06 流感与普通感冒的鉴别要点 | nhc-influenza-2020 | PASS | nhc-influenza-2020/p.8；nhc-covid19-trial-v10/p.10；nhc-influenza-2020/p.2 |
| KQ07 流感抗病毒治疗的适用人群 | nhc-influenza-2020 | PASS | nhc-covid19-trial-v10/p.11；nhc-influenza-2020/p.7；nhc-influenza-2020/p.9 |
| KQ08 新型冠状病毒感染常见临床表现 | nhc-covid19-trial-v10 | PASS | nhc-child-mpp-2025/p.7；nhc-covid19-trial-v10/p.2；nhc-covid19-trial-v10/p.7 |
| KQ09 新冠感染重症高风险因素有哪些？ | nhc-covid19-trial-v10 | PASS | nhc-covid19-trial-v10/p.11；nhc-covid19-trial-v10/p.7；nhc-covid19-trial-v10/p.10 |
| KQ10 新冠核酸检测和抗原检测的意义 | nhc-covid19-trial-v10 | PASS | nhc-covid19-trial-v10/p.6；nhc-covid19-trial-v10/p.7；nhc-influenza-2020/p.5 |
| KQ11 新冠重型和危重型诊断标准 | nhc-covid19-trial-v10 | PASS | nhc-covid19-trial-v10/p.6；nhc-influenza-2020/p.9；nhc-influenza-2020/p.8 |
| KQ12 儿童感染新冠可能有哪些症状？ | nhc-covid19-trial-v10 | PASS | nhc-covid19-trial-v10/p.5；nhc-covid19-trial-v10/p.10；nhc-covid19-trial-v10/p.8 |
| KQ13 新冠患者呼吸困难和低氧血症风险 | nhc-covid19-trial-v10 | PASS | nhc-covid19-trial-v10/p.4；nhc-child-mpp-2025/p.9；nhc-covid19-trial-v10/p.9 |
| KQ14 新型冠状病毒感染的诊断依据 | nhc-covid19-trial-v10 | PASS | nhc-child-mpp-2025/p.7；nhc-covid19-trial-v10/p.2；nhc-covid19-trial-v10/p.3 |
| KQ15 儿童肺炎支原体肺炎有哪些临床表现？ | nhc-child-mpp-2025 | FAIL | nhc-covid19-trial-v10/p.10；nhc-influenza-2020/p.8；nhc-influenza-2020/p.4 |
| KQ16 大环内酯类药物无反应性肺炎支原体肺炎如何定义？ | nhc-child-mpp-2025 | PASS | nhc-child-mpp-2025/p.6；nhc-covid19-trial-v10/p.10；nhc-child-mpp-2025/p.8 |
| KQ17 重症肺炎支原体肺炎的早期识别指标 | nhc-child-mpp-2025 | PASS | nhc-child-mpp-2025/p.8；nhc-covid19-trial-v10/p.10；nhc-influenza-2020/p.8 |
| KQ18 支原体肺炎咳嗽有什么特征？ | nhc-child-mpp-2025 | PASS | nhc-influenza-2020/p.8；nhc-covid19-trial-v10/p.10；nhc-covid19-trial-v10/p.7 |
| KQ19 儿童肺炎支原体肺炎的诊断标准 | nhc-child-mpp-2025 | PASS | nhc-covid19-trial-v10/p.10；nhc-covid19-trial-v10/p.6；nhc-influenza-2020/p.8 |
| KQ20 肺炎支原体病原学和抗体检测 | nhc-child-mpp-2025 | PASS | nhc-covid19-trial-v10/p.10；nhc-influenza-2020/p.6；nhc-influenza-2020/p.8 |
