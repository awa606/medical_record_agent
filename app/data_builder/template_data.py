"""Excel 模板字段和示例数据。

这里的数据全部为课程项目模拟数据，不包含真实患者身份信息。模板以“感冒”
为示例病种，覆盖常见中医证候、症状、问诊路径、规则库和模拟对话案例。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TemplateSpec:
    """一个 Excel 模板的结构描述。"""

    filename: str
    title: str
    fields: list[dict[str, str]]
    rows: list[dict[str, Any]]


def field(name: str, description: str, required: str, example: str) -> dict[str, str]:
    """简化字段说明的书写。"""

    return {
        "字段名": name,
        "字段说明": description,
        "是否必填": required,
        "示例": example,
    }


TEMPLATE_SPECS: dict[str, TemplateSpec] = {
    "disease": TemplateSpec(
        filename="disease.xlsx",
        title="疾病基础表",
        fields=[
            field("disease_id", "疾病唯一编号，供规则和证候关联使用", "是", "D_COMMON_COLD"),
            field("disease_name", "疾病名称", "是", "感冒"),
            field("category", "所属医学分类或课程分类", "否", "中医内科"),
            field("aliases", "常见别名，多个值用竖线分隔", "否", "伤风|冒风"),
            field("description", "疾病简要说明，用于展示和检索", "否", "外感风邪或时行病毒引起的常见外感病"),
            field("common_symptoms", "常见症状编号，多个值用竖线分隔", "否", "SYM_FEVER|SYM_CHILLS"),
            field("safety_note", "数据安全说明", "是", "仅课程模拟，不含真实患者身份信息"),
        ],
        rows=[
            {
                "disease_id": "D_COMMON_COLD",
                "disease_name": "感冒",
                "category": "中医内科",
                "aliases": "伤风|冒风",
                "description": "外感风邪或时行病毒引起，以发热、恶寒、鼻塞、流涕、咳嗽等为常见表现的外感病。",
                "common_symptoms": "SYM_FEVER|SYM_CHILLS|SYM_HEADACHE|SYM_NASAL_DISCHARGE|SYM_COUGH",
                "safety_note": "仅课程模拟，不含真实患者身份信息",
            }
        ],
    ),
    "syndrome": TemplateSpec(
        filename="syndrome.xlsx",
        title="中医证候表",
        fields=[
            field("syndrome_id", "证候唯一编号", "是", "S_WIND_COLD"),
            field("disease_id", "所属疾病编号", "是", "D_COMMON_COLD"),
            field("syndrome_name", "证候名称", "是", "风寒束表证"),
            field("pathogenesis", "病机概要", "否", "风寒外束，卫阳被郁"),
            field("key_symptoms", "核心症状编号，多个值用竖线分隔", "是", "SYM_CHILLS|SYM_NO_SWEAT"),
            field("tongue", "舌象提示", "否", "舌苔薄白"),
            field("pulse", "脉象提示", "否", "脉浮紧"),
            field("treatment_principle", "治法原则，课程展示用", "否", "辛温解表"),
            field("course_note", "课程项目备注，不作为处方建议", "是", "仅模拟知识库，不用于真实诊疗"),
        ],
        rows=[
            {
                "syndrome_id": "S_WIND_COLD",
                "disease_id": "D_COMMON_COLD",
                "syndrome_name": "风寒束表证",
                "pathogenesis": "风寒外束，卫阳被郁，腠理闭塞。",
                "key_symptoms": "SYM_CHILLS|SYM_MILD_FEVER|SYM_NO_SWEAT|SYM_HEADACHE|SYM_CLEAR_NASAL_DISCHARGE|SYM_BODY_ACHE|SYM_THIN_WHITE_COATING|SYM_FLOAT_TIGHT_PULSE",
                "tongue": "舌苔薄白",
                "pulse": "脉浮紧",
                "treatment_principle": "辛温解表",
                "course_note": "仅模拟知识库，不用于真实诊疗",
            },
            {
                "syndrome_id": "S_WIND_HEAT",
                "disease_id": "D_COMMON_COLD",
                "syndrome_name": "风热犯表证",
                "pathogenesis": "风热犯表，肺卫失宣。",
                "key_symptoms": "SYM_HIGHER_FEVER|SYM_SLIGHT_CHILLS|SYM_SORE_THROAT|SYM_YELLOW_NASAL_DISCHARGE|SYM_COUGH|SYM_YELLOW_SPUTUM|SYM_THIN_YELLOW_COATING|SYM_FLOAT_RAPID_PULSE",
                "tongue": "舌边尖红，苔薄黄",
                "pulse": "脉浮数",
                "treatment_principle": "辛凉解表",
                "course_note": "仅模拟知识库，不用于真实诊疗",
            },
            {
                "syndrome_id": "S_SUMMER_DAMP",
                "disease_id": "D_COMMON_COLD",
                "syndrome_name": "暑湿伤表证",
                "pathogenesis": "暑湿郁表，清阳不展，中焦气机受阻。",
                "key_symptoms": "SYM_FEVER|SYM_HEAVY_HEAD|SYM_CHEST_OPPRESSION|SYM_NAUSEA|SYM_GREASY_COATING|SYM_SOFT_RAPID_PULSE",
                "tongue": "舌苔白腻或黄腻",
                "pulse": "脉濡数",
                "treatment_principle": "清暑祛湿解表",
                "course_note": "仅模拟知识库，不用于真实诊疗",
            },
            {
                "syndrome_id": "S_QI_DEF_COLD",
                "disease_id": "D_COMMON_COLD",
                "syndrome_name": "气虚感冒证",
                "pathogenesis": "正气不足，卫外不固，外邪乘虚而入。",
                "key_symptoms": "SYM_RECURRENT_COLD|SYM_FATIGUE|SYM_SHORT_BREATH|SYM_SPONTANEOUS_SWEAT|SYM_PALE_TONGUE|SYM_FLOAT_WEAK_PULSE",
                "tongue": "舌淡，苔白",
                "pulse": "脉浮无力",
                "treatment_principle": "益气解表",
                "course_note": "仅模拟知识库，不用于真实诊疗",
            },
        ],
    ),
    "symptom": TemplateSpec(
        filename="symptom.xlsx",
        title="症状词典表",
        fields=[
            field("symptom_id", "症状唯一编号", "是", "SYM_FEVER"),
            field("symptom_name", "标准症状名称", "是", "发热"),
            field("symptom_type", "症状类别，如主症、伴随症状、舌象、脉象", "是", "主症"),
            field("normalized_value", "标准化取值或描述", "否", "有发热"),
            field("synonyms", "患者可能表达，多个值用竖线分隔", "否", "发烧|身热"),
            field("polarity", "阳性、阴性或待补充", "是", "阳性"),
            field("description", "用于抽取和规则说明的解释", "否", "体温升高或患者自觉发热"),
        ],
        rows=[
            {"symptom_id": "SYM_FEVER", "symptom_name": "发热", "symptom_type": "主症", "normalized_value": "有发热", "synonyms": "发烧|身热|体温高", "polarity": "阳性", "description": "体温升高或患者自觉发热。"},
            {"symptom_id": "SYM_MILD_FEVER", "symptom_name": "发热较轻", "symptom_type": "主症", "normalized_value": "发热轻", "synonyms": "低热|发热不重", "polarity": "阳性", "description": "风寒束表证常见。"},
            {"symptom_id": "SYM_HIGHER_FEVER", "symptom_name": "发热较重", "symptom_type": "主症", "normalized_value": "发热重", "synonyms": "明显发热|热得厉害", "polarity": "阳性", "description": "风热犯表证常见。"},
            {"symptom_id": "SYM_CHILLS", "symptom_name": "恶寒", "symptom_type": "主症", "normalized_value": "怕冷", "synonyms": "怕冷|畏寒|恶寒", "polarity": "阳性", "description": "患者自觉寒冷。"},
            {"symptom_id": "SYM_SLIGHT_CHILLS", "symptom_name": "微恶风", "symptom_type": "主症", "normalized_value": "轻微怕风", "synonyms": "微怕风|有点怕冷", "polarity": "阳性", "description": "风热犯表证可见。"},
            {"symptom_id": "SYM_NO_SWEAT", "symptom_name": "无汗", "symptom_type": "伴随症状", "normalized_value": "没有出汗", "synonyms": "不出汗|汗不出来", "polarity": "阳性", "description": "腠理闭塞时常见。"},
            {"symptom_id": "SYM_SPONTANEOUS_SWEAT", "symptom_name": "自汗", "symptom_type": "伴随症状", "normalized_value": "自汗", "synonyms": "容易出汗|动一下就出汗", "polarity": "阳性", "description": "气虚感冒证常见。"},
            {"symptom_id": "SYM_HEADACHE", "symptom_name": "头痛", "symptom_type": "伴随症状", "normalized_value": "头痛", "synonyms": "头疼|头胀", "polarity": "阳性", "description": "外感常见症状。"},
            {"symptom_id": "SYM_HEAVY_HEAD", "symptom_name": "头身困重", "symptom_type": "伴随症状", "normalized_value": "头身困重", "synonyms": "头昏沉|身体沉重", "polarity": "阳性", "description": "暑湿伤表证常见。"},
            {"symptom_id": "SYM_BODY_ACHE", "symptom_name": "肢体酸痛", "symptom_type": "伴随症状", "normalized_value": "肢体酸痛", "synonyms": "全身酸痛|身上酸", "polarity": "阳性", "description": "风寒束表证常见。"},
            {"symptom_id": "SYM_SORE_THROAT", "symptom_name": "咽痛", "symptom_type": "伴随症状", "normalized_value": "咽喉疼痛", "synonyms": "嗓子疼|咽喉痛", "polarity": "阳性", "description": "风热犯表证常见。"},
            {"symptom_id": "SYM_NASAL_DISCHARGE", "symptom_name": "流涕", "symptom_type": "伴随症状", "normalized_value": "流鼻涕", "synonyms": "流涕|鼻涕", "polarity": "阳性", "description": "感冒常见症状。"},
            {"symptom_id": "SYM_CLEAR_NASAL_DISCHARGE", "symptom_name": "清涕", "symptom_type": "伴随症状", "normalized_value": "鼻涕清稀", "synonyms": "清鼻涕|鼻涕清", "polarity": "阳性", "description": "风寒束表证常见。"},
            {"symptom_id": "SYM_YELLOW_NASAL_DISCHARGE", "symptom_name": "黄涕", "symptom_type": "伴随症状", "normalized_value": "鼻涕黄稠", "synonyms": "黄鼻涕|鼻涕黄", "polarity": "阳性", "description": "风热犯表证常见。"},
            {"symptom_id": "SYM_COUGH", "symptom_name": "咳嗽", "symptom_type": "伴随症状", "normalized_value": "咳嗽", "synonyms": "咳|咳嗽", "polarity": "阳性", "description": "肺卫失宣可见。"},
            {"symptom_id": "SYM_YELLOW_SPUTUM", "symptom_name": "黄痰", "symptom_type": "伴随症状", "normalized_value": "痰黄", "synonyms": "黄痰|痰色黄", "polarity": "阳性", "description": "风热犯表证常见。"},
            {"symptom_id": "SYM_FATIGUE", "symptom_name": "乏力", "symptom_type": "伴随症状", "normalized_value": "乏力", "synonyms": "没劲|疲乏", "polarity": "阳性", "description": "气虚感冒证常见。"},
            {"symptom_id": "SYM_SHORT_BREATH", "symptom_name": "气短", "symptom_type": "伴随症状", "normalized_value": "气短", "synonyms": "说话懒|气不够", "polarity": "阳性", "description": "气虚表现之一。"},
            {"symptom_id": "SYM_RECURRENT_COLD", "symptom_name": "反复感冒", "symptom_type": "病史", "normalized_value": "反复感冒", "synonyms": "容易感冒|经常感冒", "polarity": "阳性", "description": "气虚感冒证重要线索。"},
            {"symptom_id": "SYM_CHEST_OPPRESSION", "symptom_name": "胸闷", "symptom_type": "伴随症状", "normalized_value": "胸闷", "synonyms": "胸口闷|胸部发闷", "polarity": "阳性", "description": "暑湿困阻可见。"},
            {"symptom_id": "SYM_NAUSEA", "symptom_name": "恶心", "symptom_type": "伴随症状", "normalized_value": "恶心", "synonyms": "想吐|胃里不舒服", "polarity": "阳性", "description": "暑湿伤表证常见。"},
            {"symptom_id": "SYM_THIN_WHITE_COATING", "symptom_name": "苔薄白", "symptom_type": "舌象", "normalized_value": "舌苔薄白", "synonyms": "薄白苔", "polarity": "阳性", "description": "风寒束表证舌象提示。"},
            {"symptom_id": "SYM_THIN_YELLOW_COATING", "symptom_name": "苔薄黄", "symptom_type": "舌象", "normalized_value": "舌苔薄黄", "synonyms": "薄黄苔", "polarity": "阳性", "description": "风热犯表证舌象提示。"},
            {"symptom_id": "SYM_GREASY_COATING", "symptom_name": "苔腻", "symptom_type": "舌象", "normalized_value": "舌苔腻", "synonyms": "腻苔|白腻苔", "polarity": "阳性", "description": "暑湿证候舌象提示。"},
            {"symptom_id": "SYM_PALE_TONGUE", "symptom_name": "舌淡", "symptom_type": "舌象", "normalized_value": "舌淡", "synonyms": "舌质淡", "polarity": "阳性", "description": "气虚证候舌象提示。"},
            {"symptom_id": "SYM_FLOAT_TIGHT_PULSE", "symptom_name": "脉浮紧", "symptom_type": "脉象", "normalized_value": "脉浮紧", "synonyms": "浮紧脉", "polarity": "阳性", "description": "风寒束表证脉象提示。"},
            {"symptom_id": "SYM_FLOAT_RAPID_PULSE", "symptom_name": "脉浮数", "symptom_type": "脉象", "normalized_value": "脉浮数", "synonyms": "浮数脉", "polarity": "阳性", "description": "风热犯表证脉象提示。"},
            {"symptom_id": "SYM_SOFT_RAPID_PULSE", "symptom_name": "脉濡数", "symptom_type": "脉象", "normalized_value": "脉濡数", "synonyms": "濡数脉", "polarity": "阳性", "description": "暑湿伤表证脉象提示。"},
            {"symptom_id": "SYM_FLOAT_WEAK_PULSE", "symptom_name": "脉浮无力", "symptom_type": "脉象", "normalized_value": "脉浮无力", "synonyms": "浮弱脉", "polarity": "阳性", "description": "气虚感冒证脉象提示。"},
        ],
    ),
    "question_template": TemplateSpec(
        filename="question_template.xlsx",
        title="问诊路径模板表",
        fields=[
            field("question_id", "问题唯一编号", "是", "Q_FEVER"),
            field("question_order", "建议问诊顺序，数值越小越靠前", "是", "10"),
            field("target_field", "问题要补全的结构化字段", "是", "发热"),
            field("question_text", "医生侧问句模板", "是", "有没有发热？最高体温大概多少？"),
            field("followup_when_positive", "患者阳性回答后的追问", "否", "什么时候开始的？"),
            field("maps_to_symptom_ids", "可映射症状编号，多个值用竖线分隔", "是", "SYM_FEVER|SYM_HIGHER_FEVER"),
            field("required", "是否为感冒问诊基础问题", "是", "是"),
            field("notes", "用于课程展示的说明", "否", "先问主症，再问伴随症状"),
        ],
        rows=[
            {"question_id": "Q_CHIEF", "question_order": 1, "target_field": "主诉", "question_text": "这次主要哪里不舒服？大概持续多久了？", "followup_when_positive": "症状是突然出现还是逐渐加重？", "maps_to_symptom_ids": "SYM_FEVER|SYM_CHILLS|SYM_COUGH", "required": "是", "notes": "获取主诉和病程。"},
            {"question_id": "Q_FEVER", "question_order": 10, "target_field": "发热", "question_text": "有没有发热？最高体温大概多少？", "followup_when_positive": "发热是持续的还是一阵一阵的？", "maps_to_symptom_ids": "SYM_FEVER|SYM_MILD_FEVER|SYM_HIGHER_FEVER", "required": "是", "notes": "区分发热轻重。"},
            {"question_id": "Q_CHILLS", "question_order": 20, "target_field": "恶寒/怕风", "question_text": "怕冷或怕风明显吗？", "followup_when_positive": "是怕冷明显，还是只是有点怕风？", "maps_to_symptom_ids": "SYM_CHILLS|SYM_SLIGHT_CHILLS", "required": "是", "notes": "辅助区分风寒与风热。"},
            {"question_id": "Q_SWEAT", "question_order": 30, "target_field": "出汗", "question_text": "这几天出汗情况怎么样？", "followup_when_positive": "是没有汗，还是容易自己出汗？", "maps_to_symptom_ids": "SYM_NO_SWEAT|SYM_SPONTANEOUS_SWEAT", "required": "是", "notes": "关注无汗或自汗。"},
            {"question_id": "Q_THROAT", "question_order": 40, "target_field": "咽喉", "question_text": "咽喉疼不疼？有没有口干口渴？", "followup_when_positive": "咽痛是轻微还是比较明显？", "maps_to_symptom_ids": "SYM_SORE_THROAT", "required": "是", "notes": "风热常见咽痛。"},
            {"question_id": "Q_NOSE", "question_order": 50, "target_field": "鼻部症状", "question_text": "有没有鼻塞、流鼻涕？鼻涕是清的还是黄的？", "followup_when_positive": "鼻涕量多不多？是否黏稠？", "maps_to_symptom_ids": "SYM_NASAL_DISCHARGE|SYM_CLEAR_NASAL_DISCHARGE|SYM_YELLOW_NASAL_DISCHARGE", "required": "是", "notes": "鼻涕颜色辅助辨证。"},
            {"question_id": "Q_COUGH", "question_order": 60, "target_field": "咳嗽咳痰", "question_text": "有没有咳嗽、咳痰？痰是什么颜色？", "followup_when_positive": "痰量多不多？是否黏稠？", "maps_to_symptom_ids": "SYM_COUGH|SYM_YELLOW_SPUTUM", "required": "是", "notes": "记录咳嗽和痰色。"},
            {"question_id": "Q_BODY", "question_order": 70, "target_field": "头身不适", "question_text": "有没有头痛、全身酸痛，或者头身困重？", "followup_when_positive": "是酸痛明显，还是觉得头身沉重？", "maps_to_symptom_ids": "SYM_HEADACHE|SYM_BODY_ACHE|SYM_HEAVY_HEAD", "required": "是", "notes": "外感常见伴随症状。"},
            {"question_id": "Q_DIGESTIVE", "question_order": 80, "target_field": "脘腹/恶心", "question_text": "有没有胸闷、胃里不舒服或恶心想吐？", "followup_when_positive": "有没有腹胀、食欲下降？", "maps_to_symptom_ids": "SYM_CHEST_OPPRESSION|SYM_NAUSEA", "required": "否", "notes": "暑湿证候重点追问。"},
            {"question_id": "Q_HISTORY", "question_order": 90, "target_field": "既往易感", "question_text": "平时是不是比较容易感冒，或者最近明显乏力气短？", "followup_when_positive": "这种情况持续多久了？", "maps_to_symptom_ids": "SYM_RECURRENT_COLD|SYM_FATIGUE|SYM_SHORT_BREATH", "required": "否", "notes": "气虚感冒证重点追问。"},
            {"question_id": "Q_TONGUE_PULSE", "question_order": 100, "target_field": "舌脉", "question_text": "请医生查体时补充舌象、脉象。", "followup_when_positive": "记录舌苔颜色厚薄和脉象。", "maps_to_symptom_ids": "SYM_THIN_WHITE_COATING|SYM_THIN_YELLOW_COATING|SYM_GREASY_COATING|SYM_PALE_TONGUE|SYM_FLOAT_TIGHT_PULSE|SYM_FLOAT_RAPID_PULSE|SYM_SOFT_RAPID_PULSE|SYM_FLOAT_WEAK_PULSE", "required": "是", "notes": "模拟数据不替代真实查体。"},
        ],
    ),
    "rule_base": TemplateSpec(
        filename="rule_base.xlsx",
        title="辨证规则表",
        fields=[
            field("rule_id", "规则唯一编号", "是", "R_WIND_COLD_001"),
            field("disease_id", "疾病编号", "是", "D_COMMON_COLD"),
            field("syndrome_id", "目标证候编号", "是", "S_WIND_COLD"),
            field("positive_symptom_ids", "支持该证候的阳性症状，多个值用竖线分隔", "是", "SYM_CHILLS|SYM_NO_SWEAT"),
            field("negative_symptom_ids", "不支持该证候的症状，多个值用竖线分隔", "否", "SYM_SORE_THROAT"),
            field("weight", "规则权重，便于简单评分", "是", "0.85"),
            field("decision_hint", "规则命中后的解释提示", "是", "候选风寒束表证"),
            field("confidence_hint", "置信度说明，供展示用", "否", "中等偏高，仍需医生确认"),
            field("explanation", "课程展示说明", "否", "恶寒重、无汗、清涕支持风寒"),
        ],
        rows=[
            {"rule_id": "R_WIND_COLD_001", "disease_id": "D_COMMON_COLD", "syndrome_id": "S_WIND_COLD", "positive_symptom_ids": "SYM_CHILLS|SYM_MILD_FEVER|SYM_NO_SWEAT|SYM_CLEAR_NASAL_DISCHARGE|SYM_BODY_ACHE", "negative_symptom_ids": "SYM_SORE_THROAT|SYM_YELLOW_NASAL_DISCHARGE", "weight": 0.86, "decision_hint": "候选风寒束表证", "confidence_hint": "中等偏高，仍需医生确认", "explanation": "恶寒明显、无汗、清涕、身痛支持风寒束表。"},
            {"rule_id": "R_WIND_HEAT_001", "disease_id": "D_COMMON_COLD", "syndrome_id": "S_WIND_HEAT", "positive_symptom_ids": "SYM_HIGHER_FEVER|SYM_SLIGHT_CHILLS|SYM_SORE_THROAT|SYM_YELLOW_NASAL_DISCHARGE|SYM_YELLOW_SPUTUM", "negative_symptom_ids": "SYM_NO_SWEAT|SYM_CLEAR_NASAL_DISCHARGE", "weight": 0.88, "decision_hint": "候选风热犯表证", "confidence_hint": "中等偏高，仍需医生确认", "explanation": "发热较重、咽痛、黄涕或黄痰支持风热犯表。"},
            {"rule_id": "R_SUMMER_DAMP_001", "disease_id": "D_COMMON_COLD", "syndrome_id": "S_SUMMER_DAMP", "positive_symptom_ids": "SYM_FEVER|SYM_HEAVY_HEAD|SYM_CHEST_OPPRESSION|SYM_NAUSEA|SYM_GREASY_COATING", "negative_symptom_ids": "SYM_BODY_ACHE", "weight": 0.8, "decision_hint": "候选暑湿伤表证", "confidence_hint": "中等，需结合季节和查体", "explanation": "头身困重、胸闷恶心、苔腻提示暑湿。"},
            {"rule_id": "R_QI_DEF_001", "disease_id": "D_COMMON_COLD", "syndrome_id": "S_QI_DEF_COLD", "positive_symptom_ids": "SYM_RECURRENT_COLD|SYM_FATIGUE|SYM_SHORT_BREATH|SYM_SPONTANEOUS_SWEAT|SYM_PALE_TONGUE", "negative_symptom_ids": "SYM_HIGHER_FEVER", "weight": 0.78, "decision_hint": "候选气虚感冒证", "confidence_hint": "中等，需医生确认体质和舌脉", "explanation": "反复感冒、乏力气短、自汗支持气虚。"},
        ],
    ),
    "dialogue_cases": TemplateSpec(
        filename="dialogue_cases.xlsx",
        title="模拟医患对话测试集",
        fields=[
            field("case_id", "模拟病例编号", "是", "CASE_WIND_COLD_001"),
            field("disease_id", "疾病编号", "是", "D_COMMON_COLD"),
            field("expected_syndrome_id", "期望证候编号", "是", "S_WIND_COLD"),
            field("patient_profile_type", "模拟患者类型，不含姓名、证件号等身份信息", "是", "成人模拟患者"),
            field("chief_complaint", "模拟主诉", "是", "发热怕冷、流清涕2天"),
            field("dialogue_text", "模拟医患对话文本", "是", "医生：这次哪里不舒服？..."),
            field("expected_symptom_ids", "期望抽取到的症状编号，多个值用竖线分隔", "是", "SYM_CHILLS|SYM_NO_SWEAT"),
            field("expected_missing_fields", "期望仍需补问或查体的字段，多个值用竖线分隔", "否", "舌象|脉象"),
            field("expected_fields_json", "期望结构化字段 JSON，供评估脚本使用", "否", "{\"主诉\":\"发热怕冷、流清涕2天\"}"),
            field("safety_note", "数据安全说明", "是", "模拟对话，不包含真实个人身份信息"),
        ],
        rows=[
            {
                "case_id": "CASE_WIND_COLD_001",
                "disease_id": "D_COMMON_COLD",
                "expected_syndrome_id": "S_WIND_COLD",
                "patient_profile_type": "成人模拟患者",
                "chief_complaint": "发热怕冷、流清涕2天",
                "dialogue_text": "医生：这次主要哪里不舒服？\n患者：这两天有点发热，怕冷明显，鼻涕是清的。\n医生：有没有出汗？\n患者：基本不出汗，还全身酸痛。\n医生：咽喉疼不疼？\n患者：咽喉不怎么疼。",
                "expected_symptom_ids": "SYM_MILD_FEVER|SYM_CHILLS|SYM_CLEAR_NASAL_DISCHARGE|SYM_NO_SWEAT|SYM_BODY_ACHE",
                "expected_missing_fields": "舌象|脉象|过敏史",
                "expected_fields_json": "{\"主诉\":\"发热怕冷、流清涕2天\",\"发热\":\"发热较轻\",\"恶寒\":\"怕冷明显\",\"鼻涕\":\"清涕\",\"出汗\":\"无汗\"}",
                "safety_note": "模拟对话，不包含真实个人身份信息",
            },
            {
                "case_id": "CASE_WIND_HEAT_001",
                "disease_id": "D_COMMON_COLD",
                "expected_syndrome_id": "S_WIND_HEAT",
                "patient_profile_type": "成人模拟患者",
                "chief_complaint": "发热咽痛、黄涕1天",
                "dialogue_text": "医生：这次主要哪里不舒服？\n患者：昨天开始发热比较明显，嗓子疼，鼻涕有点黄。\n医生：怕冷吗？\n患者：只是有点怕风，不算特别怕冷。\n医生：有没有咳嗽咳痰？\n患者：有点咳，痰偏黄。",
                "expected_symptom_ids": "SYM_HIGHER_FEVER|SYM_SLIGHT_CHILLS|SYM_SORE_THROAT|SYM_YELLOW_NASAL_DISCHARGE|SYM_COUGH|SYM_YELLOW_SPUTUM",
                "expected_missing_fields": "舌象|脉象|过敏史",
                "expected_fields_json": "{\"主诉\":\"发热咽痛、黄涕1天\",\"发热\":\"发热较重\",\"咽喉\":\"咽痛\",\"鼻涕\":\"黄涕\",\"咳痰\":\"黄痰\"}",
                "safety_note": "模拟对话，不包含真实个人身份信息",
            },
        ],
    ),
}


LIST_FIELDS_BY_TEMPLATE: dict[str, set[str]] = {
    "disease": {"aliases", "common_symptoms"},
    "syndrome": {"key_symptoms"},
    "symptom": {"synonyms"},
    "question_template": {"maps_to_symptom_ids"},
    "rule_base": {"positive_symptom_ids", "negative_symptom_ids"},
    "dialogue_cases": {"expected_symptom_ids", "expected_missing_fields"},
}


JSON_FIELDS_BY_TEMPLATE: dict[str, set[str]] = {
    "dialogue_cases": {"expected_fields_json"},
}


NUMBER_FIELDS_BY_TEMPLATE: dict[str, set[str]] = {
    "question_template": {"question_order"},
    "rule_base": {"weight"},
}
