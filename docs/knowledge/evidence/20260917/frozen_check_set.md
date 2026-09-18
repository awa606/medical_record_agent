# 发热/呼吸知识库检索基线

- 生成时间：2026-09-17T15:07:44+08:00
- Git SHA：`f89ac95b900353edae868f1ee8d7f7b088f9a0ea`
- 数据集：`knowledge-v1-frozen-check-v1`（20条冻结检查集）
- 模式：`fts5_v1`
- Recall@5：**95.0%**（19/20）
- 引用完整率：**100.0%**（100/100）
- 无来源引用：**0**
- 边界：这是20条Knowledge V1工程检查集的来源级标签；尚未达到最终T11的120条复核查询与40条片段级冻结测试要求。

| 查询 | 相关来源 | Top-5命中 | 前三结果（来源/页码） |
|---|---|---:|---|
| KF01 流感潜伏期一般多长？ | nhc-influenza-2020 | PASS | nhc-influenza-2020/p.3；nhc-influenza-2020/p.2；nhc-covid19-trial-v10/p.3 |
| KF02 流感的传染源和传播途径是什么？ | nhc-influenza-2020 | PASS | nhc-covid19-trial-v10/p.3；nhc-influenza-2020/p.2；nhc-covid19-trial-v10/p.2 |
| KF03 流感患者常见全身症状有哪些？ | nhc-influenza-2020 | PASS | nhc-influenza-2020/p.4；nhc-influenza-2020/p.8；nhc-child-mpp-2025/p.7 |
| KF04 流感重症病例可能出现哪些并发症？ | nhc-influenza-2020 | PASS | nhc-influenza-2020/p.2；nhc-influenza-2020/p.11；nhc-child-mpp-2025/p.11 |
| KF05 流感病毒核酸检测阳性有什么诊断意义？ | nhc-influenza-2020 | PASS | nhc-covid19-trial-v10/p.6；nhc-influenza-2020/p.7；nhc-covid19-trial-v10/p.7 |
| KF06 新型冠状病毒感染的潜伏期与传染性特点 | nhc-covid19-trial-v10 | PASS | nhc-covid19-trial-v10/p.2；nhc-child-mpp-2025/p.7；nhc-covid19-trial-v10/p.3 |
| KF07 新冠感染如何进行临床分型？ | nhc-covid19-trial-v10 | PASS | nhc-covid19-trial-v10/p.7；nhc-child-mpp-2025/p.11；nhc-covid19-trial-v10/p.8 |
| KF08 新冠感染患者出现低氧时应关注哪些指标？ | nhc-covid19-trial-v10 | PASS | nhc-child-mpp-2025/p.9；nhc-influenza-2020/p.11；nhc-covid19-trial-v10/p.4 |
| KF09 新冠感染诊断可参考哪些病原学证据？ | nhc-covid19-trial-v10 | PASS | nhc-influenza-2020/p.8；nhc-covid19-trial-v10/p.2；nhc-influenza-2020/p.6 |
| KF10 新冠重症患者有哪些高危因素？ | nhc-covid19-trial-v10 | PASS | nhc-influenza-2020/p.6；nhc-influenza-2020/p.9；nhc-covid19-trial-v10/p.4 |
| KF11 儿童肺炎支原体肺炎的主要症状和体征 | nhc-child-mpp-2025 | FAIL | nhc-covid19-trial-v10/p.10；nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1 |
| KF12 肺炎支原体核酸检测标本如何选择？ | nhc-child-mpp-2025 | PASS | nhc-covid19-trial-v10/p.10；nhc-child-mpp-2025/p.5；nhc-covid19-trial-v10/p.6 |
| KF13 儿童重症支原体肺炎如何早期识别？ | nhc-child-mpp-2025 | PASS | nhc-child-mpp-2025/p.11；nhc-child-mpp-2025/p.8；nhc-child-mpp-2025/p.9 |
| KF14 难治性肺炎支原体肺炎的判断依据 | nhc-child-mpp-2025 | PASS | nhc-covid19-trial-v10/p.10；nhc-influenza-2020/p.8；nhc-influenza-2020/p.11 |
| KF15 肺炎支原体肺炎影像学常见表现 | nhc-child-mpp-2025 | PASS | nhc-covid19-trial-v10/p.10；nhc-influenza-2020/p.8；nhc-influenza-2020/p.6 |
| KF16 病历书写的六项基本要求是什么？ | nhc-record-standard-2010 | PASS | nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1 |
| KF17 门急诊初诊病历应记录哪些内容？ | nhc-record-standard-2010 | PASS | nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1 |
| KF18 病历出现错字时应如何修改并留痕？ | nhc-record-standard-2010 | PASS | nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1；nhc-covid19-trial-v10/p.4 |
| KF19 病历日期和时间应采用什么格式？ | nhc-record-standard-2010 | PASS | nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1 |
| KF20 打印病历完成签名后是否可以修改？ | nhc-record-standard-2010 | PASS | nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1；nhc-record-standard-2010/p.1 |
