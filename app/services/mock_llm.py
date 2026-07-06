from __future__ import annotations

import re

from app.schemas import (
    CandidateDiagnosis,
    MedicalField,
    MedicalRecordFields,
    SafetyCheckResult,
    SourceSpan,
)


def _split_segments(conversation: str) -> list[str]:
    parts = re.split(r"[。！？?!；;\n]+", conversation)
    return [part.strip(" ，,：:") for part in parts if part.strip(" ，,：:")]


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


def _is_fever_case(conversation: str) -> bool:
    return _contains(conversation, ["发烧", "发热", "体温", "布洛芬", "铁锈色痰"])


def _extract_fever_fields(conversation: str, segments: list[str]) -> MedicalRecordFields:
    fever_spans = _required_spans(
        segments,
        ["发烧", "发热", "体温", "40", "39", "淋雨", "受凉"],
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
    physical_exam_spans = _required_spans(
        segments,
        ["查体", "体温", "发热"],
        conversation,
    )
    diagnosis_spans = _merge_spans(fever_spans, symptom_spans, treatment_spans)

    return MedicalRecordFields(
        chief_complaint=_field("发热3天", fever_spans, 0.9),
        present_illness=_field(
            "3天前淋雨受凉后发热，最高体温40℃，体温多在39~40℃，伴咳嗽、咳痰，"
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
        physical_exam=_field("待医生查体补充", physical_exam_spans, 0.6),
        candidate_diagnoses=[
            CandidateDiagnosis(
                name="发热待查",
                evidence=diagnosis_spans,
            ),
            CandidateDiagnosis(
                name="肺部感染可能/肺炎待排",
                evidence=diagnosis_spans,
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


def mock_extract_fields(conversation: str) -> MedicalRecordFields:
    segments = _split_segments(conversation)
    if _is_fever_case(conversation):
        return _extract_fever_fields(conversation, segments)

    treatments = _extract_treatments(conversation)
    symptoms = _extract_symptoms(conversation)

    bite_spans = _source_spans(segments, ["咬", "肿痛", "两个小时", "两小时", "2小时"])
    treatment_spans = _source_spans(segments, ["酒精", "绷带", "包扎", "季德胜", "蛇药"])
    symptom_spans = _source_spans(segments, ["畏寒", "胃寒", "寒战", "头晕", "胸闷", "心慌", "牙龈", "出血"])

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
            )
        )
    if _contains(conversation, ["牙龈", "出血"]):
        candidate_diagnoses.append(
            CandidateDiagnosis(
                name="凝血功能异常",
                evidence=symptom_spans,
            )
        )

    return MedicalRecordFields(
        chief_complaint=chief_complaint,
        present_illness=present_illness,
        previous_treatment=previous_treatment,
        accompanying_symptoms=accompanying_symptoms,
        allergy_history=MedicalField.missing_field(),
        past_history=MedicalField.missing_field(),
        physical_exam=MedicalField.missing_field("待医生查体补充"),
        candidate_diagnoses=candidate_diagnoses,
    )


def _field_text(field: MedicalField, *, physical_exam: bool = False) -> str:
    if field.missing:
        if physical_exam:
            return "待医生查体补充"
        return "未提及/待补充"
    return field.value or "未提及/待补充"


def mock_generate_draft(fields: MedicalRecordFields | dict) -> str:
    record = MedicalRecordFields.model_validate(fields)
    diagnosis_lines = []
    for diagnosis in record.candidate_diagnoses:
        evidence = "；".join(span.text for span in diagnosis.evidence[:3]) or "依据待医生核对"
        diagnosis_lines.append(f"- {diagnosis.name}（{diagnosis.status}）依据：{evidence}")

    candidate_text = "\n".join(diagnosis_lines) if diagnosis_lines else "未提及/待医生确认"

    return "\n".join(
        [
            "门诊病历草稿",
            f"主诉：{_field_text(record.chief_complaint)}",
            f"现病史：{_field_text(record.present_illness)}",
            f"既往处理：{_field_text(record.previous_treatment)}",
            f"伴随症状：{_field_text(record.accompanying_symptoms)}",
            f"既往史：{_field_text(record.past_history)}",
            f"过敏史：{_field_text(record.allergy_history)}",
            f"查体：{_field_text(record.physical_exam, physical_exam=True)}",
            "候选诊断：",
            candidate_text,
        ]
    )


def _line_for(label: str, draft_text: str) -> str:
    for line in draft_text.splitlines():
        if line.startswith(label):
            return line
    return ""


def mock_safety_check(
    draft_text: str,
    fields: MedicalRecordFields | dict,
    *,
    allow_export: bool = False,
) -> SafetyCheckResult:
    record = MedicalRecordFields.model_validate(fields)
    errors: list[str] = []
    warnings: list[str] = []

    allergy_line = _line_for("过敏史", draft_text)
    if record.allergy_history.missing and re.search(r"(无|否认)", allergy_line):
        errors.append("过敏史未提及时不得写成“无”或“否认”。")

    for diagnosis in record.candidate_diagnoses:
        for line in draft_text.splitlines():
            if diagnosis.name in line and diagnosis.status not in line:
                errors.append(f"候选诊断“{diagnosis.name}”未标记“候选/待医生确认”。")
                break

    if re.search(r"诊断为|确诊为|最终诊断", draft_text):
        errors.append("草稿存在把候选诊断写成最终诊断的风险。")

    fabricated_phrases = ["生命体征平稳", "查体无异常", "无明显异常"]
    if record.physical_exam.missing and _contains(draft_text, fabricated_phrases):
        errors.append("查体未提及时不得编造体征或阴性结果。")

    if allow_export:
        unconfirmed_candidates = [
            diagnosis.name
            for diagnosis in record.candidate_diagnoses
            if not diagnosis.confirmed_by_doctor
        ]
        if unconfirmed_candidates:
            errors.append("存在未确认候选诊断却允许导出的风险。")

    if record.allergy_history.missing:
        warnings.append("过敏史未提及，建议医生补问。")
    if record.physical_exam.missing:
        warnings.append("查体未提及，需医生查体补充。")

    return SafetyCheckResult(
        passed=not errors,
        blocked=bool(errors),
        errors=errors,
        warnings=warnings,
    )


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
