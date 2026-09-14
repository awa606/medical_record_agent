from __future__ import annotations

import re

from app.schemas import (
    CandidateDiagnosis,
    MedicalField,
    MedicalRecordFields,
    SafetyCheckResult,
    SourceSpan,
)
from app.services.clinical_facts import (
    build_fields_from_clinical_facts,
    validate_field_evidence,
)
from app.services.knowledge_rules import infer_common_cold_candidates


def _split_segments(conversation: str) -> list[str]:
    parts = re.split(r"[。！？!?\n]+", conversation)
    return [part.strip(" ，,") for part in parts if part.strip(" ，,")]


def _contains(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _source_spans(segments: list[str], keywords: list[str]) -> list[SourceSpan]:
    spans = [
        SourceSpan(index=index, text=segment)
        for index, segment in enumerate(segments)
        if _contains(segment, keywords)
    ]
    return spans


def _merge_spans(*span_groups: list[SourceSpan]) -> list[SourceSpan]:
    merged: list[SourceSpan] = []
    seen: set[tuple[int | None, str]] = set()
    for spans in span_groups:
        for span in spans:
            key = (span.index, span.text)
            if key not in seen:
                seen.add(key)
                merged.append(span)
    return merged


def _field(value: str, source_spans: list[SourceSpan], confidence: float = 0.85) -> MedicalField:
    return MedicalField(
        value=value,
        missing=False,
        hint=None,
        confidence=confidence,
        source_spans=source_spans,
    )


def _required_spans(segments: list[str], keywords: list[str], conversation: str) -> list[SourceSpan]:
    spans = _source_spans(segments, keywords)
    if spans:
        return spans
    fallback_text = segments[0] if segments else conversation
    return [SourceSpan(index=0, text=fallback_text)]


_PHYSICAL_EXAM_REQUIRED_PATTERNS = [
    re.compile(r"\bT\s*\d", re.IGNORECASE),
    re.compile(r"\bP\s*\d", re.IGNORECASE),
    re.compile(r"\bR\s*\d", re.IGNORECASE),
    re.compile(r"\bBP\s*\d", re.IGNORECASE),
    re.compile(r"(体温|血压|脉搏|心率|呼吸)\s*[:：]?\s*\d"),
]

_PHYSICAL_EXAM_FINDING_KEYWORDS = [
    "查体见",
    "查体提示",
    "体格检查",
    "生命体征",
    "神清",
    "咽部",
    "双肺",
    "心肺",
    "心律",
    "压痛",
    "反跳痛",
    "肿胀",
    "可见伤口",
    "局部",
    "皮温",
    "瞳孔",
    "意识",
]

_PHYSICAL_EXAM_REJECT_KEYWORDS = [
    "请问",
    "有没有",
    "是否",
    "什么",
    "哪里",
    "之前",
    "既往",
    "过敏",
    "糖尿病",
    "高血压",
    "家里人",
    "工作",
    "年龄",
    "胸痛",
    "呼吸困难",
]

_SUBJECTIVE_TEMPERATURE_KEYWORDS = ["最高体温", "体温多", "发热", "退热", "反复发热"]
_OBJECTIVE_EXAM_ANCHORS = ["查体", "体格检查", "生命体征", "T ", "P ", "R ", "BP"]
_CLINICAL_FACT_PRIORITY_TEMP_RE = re.compile(
    r"(?:3[5-9](?:\.\d)?|4[0-2](?:\.\d)?)\s*(?:°\s*)?(?:C|c|℃|度)"
)
_CLINICAL_FACT_DANGER_KEYWORDS = ["胸闷", "胸痛", "气促", "呼吸困难"]


def _looks_like_physical_exam(text: str) -> bool:
    if not text:
        return False
    normalized = re.sub(r"\s+", "", text)
    if "？" in text or "?" in text:
        return False
    if any(keyword in normalized for keyword in _SUBJECTIVE_TEMPERATURE_KEYWORDS):
        if not any(anchor.replace(" ", "") in normalized for anchor in _OBJECTIVE_EXAM_ANCHORS):
            return False
    if any(keyword in normalized for keyword in _PHYSICAL_EXAM_REJECT_KEYWORDS):
        if not any(pattern.search(text) for pattern in _PHYSICAL_EXAM_REQUIRED_PATTERNS):
            return False
    if any(pattern.search(text) for pattern in _PHYSICAL_EXAM_REQUIRED_PATTERNS):
        return True
    return any(keyword in normalized for keyword in _PHYSICAL_EXAM_FINDING_KEYWORDS)


def _should_prioritize_clinical_fact_fields(
    conversation: str,
    fields: MedicalRecordFields,
) -> bool:
    if not fields.candidate_diagnoses:
        return False
    if _looks_like_physical_exam(conversation) and any(anchor in conversation for anchor in _OBJECTIVE_EXAM_ANCHORS):
        return False
    has_temperature_value = bool(_CLINICAL_FACT_PRIORITY_TEMP_RE.search(conversation))
    has_fever_context = _contains(conversation, ["发热", "发烧", "体温"])
    has_danger_signal = _contains(conversation, _CLINICAL_FACT_DANGER_KEYWORDS)
    return has_temperature_value or (has_fever_context and has_danger_signal)


def _extract_physical_exam_field(segments: list[str]) -> MedicalField:
    spans = [
        SourceSpan(index=index, text=segment)
        for index, segment in enumerate(segments)
        if _looks_like_physical_exam(segment)
    ]
    if not spans:
        return MedicalField.missing_field("待医生查体补充")
    value = "；".join(span.text for span in spans[:2])
    return _field(value, spans, 0.72)


def _is_fever_case(conversation: str) -> bool:
    if not _contains(conversation, ["发热", "发烧", "体温"]):
        return False
    full_case_markers = [
        "淋雨受凉",
        "最高体温",
        "体温多",
        "咳嗽",
        "咳痰",
        "铁锈色痰",
        "卫生院",
        "布洛芬",
        "反复发热",
        "食欲不佳",
        "既往体健",
    ]
    return sum(1 for marker in full_case_markers if marker in conversation) >= 4


def _extract_fever_fields(conversation: str, segments: list[str]) -> MedicalRecordFields:
    fever_spans = _required_spans(
        segments,
        ["发热", "发烧", "体温", "40", "39", "淋雨", "受凉"],
        conversation,
    )
    treatment_spans = _required_spans(
        segments,
        ["卫生院", "感冒", "布洛芬", "退热", "反复发热"],
        conversation,
    )
    symptom_spans = _required_spans(
        segments,
        ["咳嗽", "咳痰", "铁锈色痰", "食欲不佳"],
        conversation,
    )
    history_spans = _required_spans(
        segments,
        ["既往体健", "肺结核", "肝炎", "传染病", "预防接种"],
        conversation,
    )
    allergy_spans = _required_spans(
        segments,
        ["过敏", "食物", "药品"],
        conversation,
    )
    diagnosis_spans = _merge_spans(fever_spans, symptom_spans, treatment_spans)

    return MedicalRecordFields(
        chief_complaint=_field("发热3天", fever_spans, 0.9),
        present_illness=_field(
            "3天前淋雨受凉后发热，最高体温约40℃，体温多在39~40℃，伴咳嗽、咳痰，"
            "曾有铁锈色痰；当地卫生院考虑感冒，服用布洛芬后可退热但反复发热；"
            "病程中食欲不佳，睡眠尚可，大小便正常。",
            _merge_spans(fever_spans, treatment_spans, symptom_spans),
            0.88,
        ),
        previous_treatment=_field("当地卫生院就诊，服用布洛芬", treatment_spans, 0.88),
        accompanying_symptoms=_field("咳嗽、咳痰、铁锈色痰、食欲不佳", symptom_spans, 0.86),
        past_history=_field(
            "既往体健，否认肺结核、肝炎等传染病史，按计划预防接种",
            history_spans,
            0.84,
        ),
        allergy_history=_field("未发现食物或药品过敏史", allergy_spans, 0.84),
        physical_exam=_extract_physical_exam_field(segments),
        candidate_diagnoses=[
            CandidateDiagnosis(
                name="发热待查",
                evidence=diagnosis_spans,
                reason="反复发热、最高体温约40℃，需医生结合查体和检查进一步明确原因。",
                rule_id="FEVER_WORKUP_001",
                confidence=0.72,
                suggested_checks=[
                    "复测体温并记录热型。",
                    "由医生判断是否完善血常规、CRP 或病原学检查。",
                ],
                medication_notes=["退热和抗感染等处理需医生确认；系统不生成处方。"],
                risk_warnings=["持续高热或反复发热需医生评估感染、脱水等风险。"],
                follow_up_questions=["是否伴寒战、皮疹、胸痛或呼吸困难？"],
            ),
            CandidateDiagnosis(
                name="肺部感染可能/肺炎待排",
                evidence=diagnosis_spans,
                reason="发热伴咳嗽、咳痰及铁锈色痰，提示需排查肺部感染可能。",
                rule_id="PULMONARY_INFECTION_001",
                confidence=0.82,
                suggested_checks=[
                    "肺部听诊并记录阳性/阴性体征。",
                    "由医生判断是否完善胸部影像学检查。",
                    "必要时完善血常规、CRP 或痰液病原学检查。",
                ],
                medication_notes=["抗感染、止咳化痰等治疗需医生确认；系统不生成处方。"],
                risk_warnings=["如出现气促、胸痛、持续高热或精神差，应由医生进一步评估。"],
                follow_up_questions=["是否有胸痛、气促、寒战或痰量增多？"],
            ),
        ],
    )


def _extract_treatments(conversation: str) -> list[str]:
    treatments: list[str] = []
    if _contains(conversation, ["酒精"]):
        treatments.append("酒精冲洗")
    if _contains(conversation, ["绷带", "包扎"]):
        treatments.append("绷带包扎")
    if _contains(conversation, ["季德胜", "蛇药片", "蛇药"]):
        treatments.append("口服季德胜蛇药片")
    return treatments


def _extract_symptoms(conversation: str) -> list[str]:
    symptom_rules = [
        ("畏寒", ["畏寒", "胃寒"]),
        ("寒战", ["寒战"]),
        ("头晕", ["头晕"]),
        ("胸闷", ["胸闷"]),
        ("心慌", ["心慌"]),
        ("牙龈出血", ["牙龈", "出血"]),
    ]
    return [name for name, keywords in symptom_rules if _contains(conversation, keywords)]


def _extract_common_cold_fields(
    conversation: str,
    segments: list[str],
    candidate_diagnoses: list[CandidateDiagnosis],
) -> MedicalRecordFields:
    evidence_spans = _merge_spans(*(diagnosis.evidence for diagnosis in candidate_diagnoses))
    if not evidence_spans:
        evidence_spans = [SourceSpan(index=0, text=segments[0] if segments else conversation)]

    return MedicalRecordFields(
        chief_complaint=_field("发热伴外感相关症状，证候待医生确认", evidence_spans, 0.78),
        present_illness=_field(
            "对话提示发热、怕冷或咽鼻咳痰等外感相关表现；知识库规则仅生成候选证候和补问建议，需医生确认。",
            evidence_spans,
            0.76,
        ),
        accompanying_symptoms=_field(
            "外感相关症状见转写原文，需医生结合查体补充确认",
            evidence_spans,
            0.72,
        ),
        previous_treatment=MedicalField.missing_field(),
        past_history=MedicalField.missing_field(),
        allergy_history=MedicalField.missing_field(),
        physical_exam=MedicalField.missing_field("待医生查体补充舌象、脉象、咽部和肺部情况"),
        candidate_diagnoses=candidate_diagnoses,
    )


def mock_extract_fields(conversation: str) -> MedicalRecordFields:
    segments = _split_segments(conversation)
    if _is_fever_case(conversation):
        return validate_field_evidence(_extract_fever_fields(conversation, segments), conversation)

    clinical_fact_fields = build_fields_from_clinical_facts(conversation)
    if clinical_fact_fields is not None and _should_prioritize_clinical_fact_fields(conversation, clinical_fact_fields):
        return validate_field_evidence(clinical_fact_fields, conversation)

    knowledge_candidates = infer_common_cold_candidates(conversation, segments)
    if knowledge_candidates:
        return validate_field_evidence(
            _extract_common_cold_fields(conversation, segments, knowledge_candidates),
            conversation,
        )

    physical_exam = _extract_physical_exam_field(segments)
    if not physical_exam.missing:
        return MedicalRecordFields(physical_exam=physical_exam)

    treatments = _extract_treatments(conversation)
    symptoms = _extract_symptoms(conversation)

    bite_spans = _source_spans(segments, ["咬", "肿痛", "两个小时", "两小时", "2小时"])
    treatment_spans = _source_spans(segments, ["酒精", "绷带", "包扎", "季德胜", "蛇药"])
    symptom_spans = _source_spans(segments, ["畏寒", "寒战", "头晕", "胸闷", "心慌", "牙龈", "出血"])

    has_bite = _contains(conversation, ["咬"])
    has_hand = _contains(conversation, ["左手", "手掌"])
    has_two_hours = _contains(conversation, ["两个小时", "两小时", "2小时"])

    chief_complaint = MedicalField.missing_field()
    if has_bite and has_hand:
        duration = "约2小时" if has_two_hours else "时间未提及"
        chief_complaint = _field(f"左手手掌被咬伤后肿痛{duration}", bite_spans, 0.9)

    previous_treatment = MedicalField.missing_field()
    if treatments:
        previous_treatment = _field("、".join(treatments), treatment_spans, 0.88)

    accompanying_symptoms = MedicalField.missing_field()
    if symptoms:
        accompanying_symptoms = _field("、".join(symptoms), symptom_spans, 0.86)

    present_parts: list[str] = []
    if chief_complaint.value:
        onset = "患者约2小时前" if has_two_hours else "患者"
        present_parts.append(f"{onset}左手手掌被咬伤，伤后局部肿痛。")
    if treatments:
        present_parts.append(f"伤后自行{previous_treatment.value}。")
    if symptoms:
        present_parts.append(f"后出现{accompanying_symptoms.value}等不适。")
    if _contains(conversation, ["直接来", "来咱们医院", "来我们医院"]):
        present_parts.append("后直接来院就诊。")

    present_illness = MedicalField.missing_field()
    if present_parts:
        present_illness = _field(
            "".join(present_parts),
            _merge_spans(bite_spans, treatment_spans, symptom_spans),
            0.84,
        )

    candidate_diagnoses: list[CandidateDiagnosis] = []
    if has_bite and (_contains(conversation, ["蛇", "蛇药"]) or symptoms):
        candidate_diagnoses.append(
            CandidateDiagnosis(
                name="毒蛇咬伤",
                evidence=_merge_spans(bite_spans, symptom_spans),
                reason="存在咬伤史、局部肿痛及全身不适，需医生进一步判断是否为毒蛇咬伤。",
                rule_id="SNAKE_BITE_001",
                confidence=0.84,
                suggested_checks=[
                    "检查伤口部位、肿胀范围和远端血运感觉。",
                    "监测生命体征，并由医生评估神经毒、血循毒等表现。",
                    "必要时完善血常规、凝血功能、肝肾功能等检查。",
                ],
                medication_notes=["抗蛇毒血清、止血或镇痛等治疗需医生确认；系统不生成处方。"],
                risk_warnings=["蛇咬伤可能进展较快，需医生评估是否急诊处置或上级医院会诊。"],
                follow_up_questions=["是否看清蛇的种类、颜色或咬伤环境？", "肿胀范围是否继续扩大？"],
            )
        )
    if _contains(conversation, ["牙龈", "出血"]):
        candidate_diagnoses.append(
            CandidateDiagnosis(
                name="凝血功能异常",
                evidence=symptom_spans,
                reason="牙龈出血提示需排查凝血功能异常或毒蛇咬伤相关出血风险。",
                rule_id="COAGULATION_RISK_001",
                confidence=0.7,
                suggested_checks=[
                    "完善凝血功能、血小板计数等检查由医生判断。",
                    "观察皮下瘀斑、伤口渗血、尿色等出血表现。",
                ],
                medication_notes=["止血、抗凝相关处理需医生确认；系统不生成处方。"],
                risk_warnings=["出现进行性出血、头晕乏力或生命体征异常时需医生立即评估。"],
                follow_up_questions=["是否还有鼻出血、黑便、血尿或皮下瘀斑？"],
            )
        )

    if (
        clinical_fact_fields is not None
        and not has_bite
        and chief_complaint.missing
        and previous_treatment.missing
        and accompanying_symptoms.missing
        and not candidate_diagnoses
    ):
        return validate_field_evidence(clinical_fact_fields, conversation)

    return MedicalRecordFields(
        chief_complaint=chief_complaint,
        present_illness=present_illness,
        previous_treatment=previous_treatment,
        accompanying_symptoms=accompanying_symptoms,
        allergy_history=MedicalField.missing_field(),
        past_history=MedicalField.missing_field(),
        physical_exam=_extract_physical_exam_field(segments),
        candidate_diagnoses=candidate_diagnoses,
    )


from app.services.record_rules import render_draft as mock_generate_draft, check_draft_safety as mock_safety_check


class MockLLM:
    def extract_fields(self, conversation: str) -> MedicalRecordFields:
        return mock_extract_fields(conversation)

    def generate_draft(self, fields: MedicalRecordFields | dict) -> str:
        return mock_generate_draft(fields)

    def safety_check(
        self,
        draft_text: str,
        fields: MedicalRecordFields | dict,
        *,
        allow_export: bool = False,
    ) -> SafetyCheckResult:
        return mock_safety_check(draft_text, fields, allow_export=allow_export)
