# Enterprise Clinical Decision Support Candidate Roadmap

> 本文定义课程Beta之后的独立产品支线。当前产品仍是医生审核下的病历助手与临床决策支持候选，不是自动诊断或处方系统。

## Current Product Boundary

- **Alpha**：真实录音、ASR、角色门禁、结构化草稿、指南检索、医生审核与审计。
- **Alpha+**：长录音、恢复、幂等和可靠性。
- **Beta**：60–100例课程工程验收；不能证明企业临床安全性。
- **Enterprise Track**：医院治理、集成、独立临床验证、静默试点和发布控制。

## Work Packages

| 阶段 | 日期/依赖 | 交付 | 出口 |
|---|---|---|---|
| E0 | 2026-11-02—11-06 | 预期用途、用户、疾病范围、监管分类、风险分析 | Intended Use Gate |
| E1 | 2026-11-09—11-20 | 临床事实Schema、安全集、指标、模型比较协议 | Model Evaluation Protocol |
| E2 | 2026-11-23—12-04 | 医院内网部署、SSO/RBAC、审计、术语与HIS/EMR接口设计 | Enterprise Architecture Gate |
| E3 | 2026-12-07—12-11 | 数据使用协议、脱敏、标注规范、统计方案、医院合作材料 | Data Readiness Review |
| Gate D | 外部依赖 | 获授权医院数据与临床合作 | 未获得前BLOCKED |
| E4 | Gate D后8–12周 | 回顾性数据构建、训练/选择与独立验证 | Retrospective Validation Gate |
| E5 | E4通过后8–12周 | 科室级静默试点、人机工作流验证 | Silent Pilot Gate |
| E6 | E5通过后 | 安全、灾备、监控、变更控制、发布证据 | Enterprise Release Gate |

这些工作包不加入当前Alpha的16项/99h，也不改变现有任务ID、日期、依赖或M1–M4。

## Enterprise Architecture Direction

- 医院内网GPU推理服务运行ASR、LLM和检索；医生电脑/边缘终端承担采音、页面和本地缓冲。
- Jetson保留为边缘实验或离线降级节点，未经实机容量与持续运行验证，不承担主临床决策推理。
- SSO、岗位/科室/患者关系授权、最小权限、全流程审计、签名、Revision、加密、备份恢复、灾备、监控和SLA为必需工作包。
- HIS/EMR适配、标准数据字典、术语服务和互联互通测试单独验证。

国家卫健委《电子病历系统功能规范（试行）》要求用户授权与认证、使用审计、隐私保护、标准化存储及备份恢复；2025年电子病历信息使用管理通知进一步要求最小可用权限、分级访问和全流程可追溯：

- https://www.nhc.gov.cn/wjw/gfxwj/201101/a769b5f4b9ca4415a72fa9888bce0bc1.shtml
- https://app.www.gov.cn/govdata/gov/202507/01/531972/article.html
- https://www.nhc.gov.cn/mohwsbwstjxxzx/s8553/202008/bdd0d4fcb1c747dda000e0adec3c17b9.shtml

## Knowledge and Similar Cases

指南知识库与病例参考库必须分离。指南库继续使用SQLite＋FTS5＋BGE，并保留来源、版本、章节、页码、chunk与哈希。病例库只接收经授权、去标识、结构化并通过数据治理的历史病例。

病例检索只展示相似依据、差异、受控结局摘要和适用限制。历史治疗行为不能作为正确答案或监督标签。治疗候选必须由已确认患者事实、禁忌检查和官方指南共同支持；关键数据或指南依据缺失时拒绝生成具体方案。

## Regulatory and Clinical Evaluation Boundary

E0必须围绕实际预期用途研究中国医疗器械软件分类。2026年的多病种AI辅助决策临床评价与AI医疗器械指导原则材料仍为征求意见稿，只作为风险信号，不能当作最终规则：

- https://www.ydcmdei.org.cn/article/977
- https://www.ydcmdei.org.cn/article/975

IMDRF将科学有效性、分析有效性和临床性能区分为不同证据目标；GMLP强调代表性数据、独立测试集、临床条件下测试与人机团队表现：

- https://www.imdrf.org/documents/software-medical-device-samd-clinical-evaluation
- https://www.fda.gov/medical-devices/software-medical-device-samd/good-machine-learning-practice-medical-device-development-guiding-principles

## Gates

| Gate | 当前状态 | 解除条件 |
|---|---|---|
| Provider | PASS / ADAPT | 已有在线/本地Provider与真实本地Qwen证据 |
| Alpha Semantic | NEEDS MORE EVIDENCE | 真实角色门禁输入、冻结语义集和字段验收 |
| Knowledge Store | PASS / ADAPT | Knowledge V1已完成工程闭环 |
| Similar Case | BLOCKED | 授权去标识病例、Schema、偏差与检索协议 |
| Treatment CDS | BLOCKED | 临床方案、禁忌规则、独立验证和监管分类 |
| Enterprise Release | BLOCKED | 回顾性验证、静默试点、治理与运维证据 |
