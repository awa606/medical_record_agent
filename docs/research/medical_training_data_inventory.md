# 医学语音与病历理解数据资格清单

更新：2026-09-27。结论：优先复用已授权课程录音和用户确认真值。新增数据训练 Gate 为 **NEEDS MORE EVIDENCE**；没有数据下载、付费采购或训练行为。

## 候选对照

| 数据 | 来源／许可证据 | 语言与标注 | 重复／隔离状况 | 当前允许用途与缺口 |
| --- | --- | --- | --- | --- |
| 三段课程录音 | 用户授权本地工程验证；[历史审计](../asr/evidence/20260914/asr_baseline_audit.md) | 中文；人工转写、部分角色标注 | 历史审计只有3份独立录音；改名／切片不得扩大独立样本数 | 本地 ASR 错误定位；扩展训练用途与说话人覆盖不能从工程授权推断 |
| Realtek 13.397秒样本 | 本会话用户录制并确认固定合成句；SHA `c58c6ff5b5437a2152a2472d2cd8e10be64b42dc213bb3157611ee4333fa732c` | 中文单人，明确逐字真值 | 原始会话只有1个；所有副本同组 | 当前配对实验输入，不充当多说话人或临床评测 |
| [MultiMed-ST](https://huggingface.co/datasets/leduckhai/MultiMed-ST) | 数据卡MIT标记；仍需核查素材来源及具体子集权利 | 多语言医疗语音／转写，中文可选 | 未下载，未去重或划分核验 | ASR补充候选；数据卡标签不替代素材来源、人工转写质量抽查 |
| [IMCS-21](https://github.com/lemuria-wchen/imcs21) | 本轮仓库根目录未见明确LICENSE；需许可确认 | 中文儿科咨询；症状极性与报告等标注 | 未下载；作者划分也需按原始会话查交叉重复 | 学习标签结构；不作为已获训练许可的数据 |
| [PriMock57](https://github.com/babylonhealth/primock57) | [CC BY 4.0](https://github.com/babylonhealth/primock57/blob/main/LICENSE.md)，保留署名和修改说明 | 英文模拟问诊音频、人工转写、医生记录 | 未下载，独立性未实测 | 成对数据组织及英文工程评测候选；不作为中文ASR真值；翻译必须单独标注 |
| [MTS-Dialog／ACI-Bench](https://github.com/microsoft/clinical_visit_note_summarization_corpus) | 检查仓库LICENSE及各子集NOTICE；保留第三方要求 | 英文合成临床对话与记录 | 未下载，未对照其他公开集去重 | 结构与完整性评测候选；不是未经复核的中文临床标签 |

“候选”不表示已经采集、可直接商用或完成资格审查。教学视频字幕、网络问答与书本不自动成为患者事实真值。书籍、指南用于检索入库与用于模型训练是两种用途。

## 训练前的数据契约

每个原始会话记录：`source_url / rights_basis / language / original_session_id / speaker_group / input_sha256 / transcript_sha256 / annotation_version / reviewer / allowed_use / split`。

训练配对应包含输入对话、显式事实、否定／主体／时间／数值单位、原文位置、目标字段及缺失信息。模型可以辅助候选标注，但不能独自确认临床真值。当前没有医学复核人员，因此仅作工程验证。

按原始患者、说话人和会话分组隔离；先以文件SHA和规范化文本去重，再检查近重复。相同录音不同切片、不同容器副本不得跨集合。病例41–60保留为历史回归；新数据另留封存测试，不用于调参。

## 为什么目前不训练

旧Qwen2.5-0.5B LoRA不是当前Ollama Qwen3:4b的升级依据。新路线应匹配Qwen3-4B基础权重，并依次证明许可、标注、单样本前反向、保存重载、资源峰值及量化部署一致性。[PEFT官方量化训练方法](https://huggingface.co/docs/peft/developer_guides/quantization)

先用同一病例的人工转写与真实ASR输入定位错误。当前模型首次输出、校验拦截和医生修正分开报告；Schema合法不代表事实完整。只有独立测试事实召回改善、危险错误为0、既有安全不退化后，训练候选才进入隔离部署验证；仍不能据此宣称临床安全。

## 交互参考

参考[EMA的医生任务与角色研究](https://ux-design-awards.com/winners/ema-the-specialty-specific-and-cloud-based-electronic-health-records-ehr-system)和[Philips Lumify Manager](https://www.red-dot.org/project/philips-lumify-manager-67027)：减少核对、修改、保存之间的切换。当前落地为字段直达修改、待处理事项优先、显式版本反馈及可恢复冲突；不重新设计转写框架，不以奖项证明本项目达到医院验收。
