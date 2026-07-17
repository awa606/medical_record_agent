from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.schemas import CandidateDiagnosis, MedicalField, MedicalRecordFields, SourceSpan


FactType = Literal["symptom", "measurement", "duration", "treatment"]
Assertion = Literal["present", "absent", "resolved"]


@dataclass(frozen=True)
class ClinicalFact:
    fact_id: str
    type: FactType
    name: str
    assertion: Assertion = "present"
    value: str | None = None
    unit: str | None = None
    evidence: str = ""
    source_span: SourceSpan = field(default_factory=lambda: SourceSpan(text=""))


_SPLIT_RE = re.compile(r"[。！？!?\n]+")
_TEMP_RE = re.compile(r"(?P<value>3[5-9](?:\.\d)?|4[0-2](?:\.\d)?)\s*(?:°\s*)?(?:C|c|℃|度)")
_NEGATIVE_FEVER_RE = re.compile(r"(?:没有|没|无|不|否认).{0,4}(?:发热|发烧)")
_QUESTION_NEGATIVE_FEVER_RE = re.compile(
    r"(?:有没有|是否).{0,8}(?:发热|发烧).{0,12}(?:患者|病人)?[：:，,\s]*(?:没有|没|无|不)"
)
_RESOLVED_FEVER_RE = re.compile(
    r"(?:昨天|之前|先前|前面|曾经|曾有|发过)?.{0,6}(?:发热|发烧|体温).{0,14}(?:退了|退热|退烧|降下|降下来|不烧|已经退)"
)
_DURATION_RE = re.compile(
    r"(?:(?:持续|病程|已经|有|发热|发烧|咳嗽|头痛|头疼|痛了|疼了)?\s*)"
    r"(?P<duration>(?:半天|一天|两天|三天|四天|五天|六天|七天|一周|两周|昨天开始|今天开始|昨晚开始|"
    r"\d+\s*(?:天|周|小时)))"
)

_CHINESE_TEMPERATURES = {
    "三十五": "35",
    "三十六": "36",
    "三十七": "37",
    "三十八": "38",
    "三十九": "39",
    "四十": "40",
    "四十一": "41",
    "四十二": "42",
}


def split_clinical_segments(text: str) -> list[str]:
    parts = _SPLIT_RE.split(text)
    return [part.strip(" ，,；;") for part in parts if part.strip(" ，,；;")]


def has_extractable_clinical_fact(text: str) -> bool:
    return bool(extract_clinical_facts(text))


def extract_clinical_facts(text: str) -> list[ClinicalFact]:
    facts: list[ClinicalFact] = []
    segments = split_clinical_segments(text)
    next_id = 1

    def add(
        *,
        type_: FactType,
        name: str,
        assertion: Assertion = "present",
        value: str | None = None,
        unit: str | None = None,
        evidence: str,
        index: int | None,
    ) -> None:
        nonlocal next_id
        facts.append(
            ClinicalFact(
                fact_id=f"fact-{next_id}",
                type=type_,
                name=name,
                assertion=assertion,
                value=value,
                unit=unit,
                evidence=evidence,
                source_span=SourceSpan(index=index, text=evidence),
            )
        )
        next_id += 1

    if _QUESTION_NEGATIVE_FEVER_RE.search(text):
        add(type_="symptom", name="发热", assertion="absent", evidence=_QUESTION_NEGATIVE_FEVER_RE.search(text).group(0), index=0)

    for index, segment in enumerate(segments):
        normalized = _normalize_text(segment)
        if not normalized:
            continue

        temp = _extract_temperature(normalized)
        if temp:
            add(
                type_="measurement",
                name="体温",
                value=temp,
                unit="℃",
                evidence=segment,
                index=index,
            )

        duration = _extract_duration(normalized)
        if duration:
            add(type_="duration", name="病程", value=duration, evidence=segment, index=index)

        if _contains_treatment(normalized):
            add(type_="treatment", name="既往处理", value=_treatment_value(normalized), evidence=segment, index=index)

        if _NEGATIVE_FEVER_RE.search(normalized):
            add(type_="symptom", name="发热", assertion="absent", evidence=segment, index=index)
        elif _RESOLVED_FEVER_RE.search(normalized):
            add(type_="symptom", name="发热", assertion="resolved", evidence=segment, index=index)
        elif "发热" in normalized or "发烧" in normalized or temp:
            add(type_="symptom", name="发热", assertion="present", evidence=segment, index=index)

        if any(keyword in normalized for keyword in ["头很痛", "头痛", "头疼", "脑袋疼", "脑袋痛"]):
            add(type_="symptom", name="头痛", assertion="present", evidence=segment, index=index)

        if "咳嗽" in normalized or re.search(r"有点咳|一直咳|咳了", normalized):
            add(type_="symptom", name="咳嗽", assertion="present", evidence=segment, index=index)

    return _dedupe_facts(facts)


def build_fields_from_clinical_facts(text: str) -> MedicalRecordFields | None:
    facts = extract_clinical_facts(text)
    if not facts:
        return None

    positive_symptoms = [fact for fact in facts if fact.type == "symptom" and fact.assertion == "present"]
    absent_symptoms = [fact for fact in facts if fact.type == "symptom" and fact.assertion == "absent"]
    resolved_symptoms = [fact for fact in facts if fact.type == "symptom" and fact.assertion == "resolved"]
    measurements = [fact for fact in facts if fact.type == "measurement"]
    durations = [fact for fact in facts if fact.type == "duration"]
    treatments = [fact for fact in facts if fact.type == "treatment"]

    chief = _build_chief_complaint(positive_symptoms, resolved_symptoms, measurements, durations)
    present = _build_present_illness(positive_symptoms, absent_symptoms, resolved_symptoms, measurements, durations, treatments)
    accompanying = _build_accompanying_symptoms(positive_symptoms, chief)
    previous_treatment = _build_previous_treatment(treatments)

    return MedicalRecordFields(
        chief_complaint=chief,
        present_illness=present,
        previous_treatment=previous_treatment,
        accompanying_symptoms=accompanying,
        past_history=MedicalField.missing_field("既往史尚未提及"),
        allergy_history=MedicalField.missing_field("过敏史尚未提及"),
        physical_exam=MedicalField.missing_field("待医生查体补充"),
        candidate_diagnoses=[],
    )


def validate_field_evidence(
    fields: MedicalRecordFields,
    text: str,
    *,
    strict_text_match: bool = True,
) -> MedicalRecordFields:
    for key in [
        "chief_complaint",
        "present_illness",
        "previous_treatment",
        "accompanying_symptoms",
        "past_history",
        "allergy_history",
        "physical_exam",
    ]:
        field_value = getattr(fields, key)
        if field_value.missing or not field_value.value:
            continue
        if not field_value.source_spans:
            setattr(fields, key, _conflicting_field(field_value, "字段缺少原文证据"))
            continue
        if strict_text_match and not any(_span_text_supported(span.text, text) for span in field_value.source_spans):
            setattr(fields, key, _conflicting_field(field_value, "字段证据不在原文中"))
    return fields


def _normalize_text(text: str) -> str:
    return (
        text.replace("發燒", "发烧")
        .replace("發熱", "发热")
        .replace("℃", "°C")
        .strip()
    )


def _extract_temperature(text: str) -> str | None:
    match = _TEMP_RE.search(text)
    if match:
        return f"{match.group('value').rstrip('0').rstrip('.')}℃"
    for chinese, arabic in _CHINESE_TEMPERATURES.items():
        if f"{chinese}度" in text or f"{chinese}摄氏度" in text:
            return f"{arabic}℃"
    return None


def _extract_duration(text: str) -> str | None:
    match = _DURATION_RE.search(text)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group("duration"))


def _contains_treatment(text: str) -> bool:
    return any(keyword in text for keyword in ["布洛芬", "退热药", "退烧药", "吃了", "服用", "用药"])


def _treatment_value(text: str) -> str:
    if "布洛芬" in text:
        if any(keyword in text for keyword in ["降下", "退了", "退热", "退烧"]):
            return "服用布洛芬后体温下降"
        return "服用布洛芬"
    if "退热药" in text:
        return "服用退热药"
    if "退烧药" in text:
        return "服用退烧药"
    return "已自行处理，具体药物待补充"


def _dedupe_facts(facts: list[ClinicalFact]) -> list[ClinicalFact]:
    deduped: list[ClinicalFact] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    for fact in facts:
        key = (fact.type, fact.name, fact.assertion, fact.value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped


def _build_chief_complaint(
    positive_symptoms: list[ClinicalFact],
    resolved_symptoms: list[ClinicalFact],
    measurements: list[ClinicalFact],
    durations: list[ClinicalFact],
) -> MedicalField:
    current_names = _unique_names(positive_symptoms)
    duration = durations[0].value if durations else None
    temp = measurements[0].value if measurements else None

    if current_names:
        status: Literal["complete", "partial"] = "complete" if duration else "partial"
        if "发热" in current_names and "头痛" in current_names:
            value = f"发热伴头痛{duration or '（病程待补问）'}"
        elif "发热" in current_names and temp and not duration and len(current_names) == 1:
            value = f"发热，体温{temp}（持续时间待补问）"
        else:
            value = "伴".join(current_names)
            value = f"{value}{duration or '（病程待补问）'}"
        missing_elements = [] if duration else ["持续时间"]
        return _field_from_facts(
            value,
            [*positive_symptoms, *measurements, *durations],
            confidence=0.74 if status == "partial" else 0.84,
            status=status,
            missing_elements=missing_elements,
            hint=None if status == "complete" else "症状持续多久了？",
        )

    if resolved_symptoms:
        value = f"曾有{'、'.join(_unique_names(resolved_symptoms))}，当前是否仍有症状待补问"
        return _field_from_facts(
            value,
            resolved_symptoms,
            confidence=0.68,
            status="partial",
            missing_elements=["当前症状", "持续时间"],
            hint="目前还有发热或其他不适吗？",
        )

    return MedicalField.missing_field("主诉尚未形成有效内容")


def _build_present_illness(
    positive_symptoms: list[ClinicalFact],
    absent_symptoms: list[ClinicalFact],
    resolved_symptoms: list[ClinicalFact],
    measurements: list[ClinicalFact],
    durations: list[ClinicalFact],
    treatments: list[ClinicalFact],
) -> MedicalField:
    parts: list[str] = []
    missing: list[str] = []
    if positive_symptoms:
        symptom_text = "、".join(_unique_names(positive_symptoms))
        duration = durations[0].value if durations else None
        duration_text = duration or ""
        parts.append(f"患者自述{symptom_text}{duration_text}")
    if measurements:
        parts.append(f"体温约{measurements[0].value}")
    if absent_symptoms:
        parts.append(f"患者否认{'、'.join(_unique_names(absent_symptoms))}")
    if resolved_symptoms:
        parts.append(f"患者自述曾有{'、'.join(_unique_names(resolved_symptoms))}，目前已缓解")
    if treatments:
        parts.append("；".join(fact.value or fact.name for fact in treatments))

    if not durations and (positive_symptoms or resolved_symptoms):
        missing.append("起病时间")
    if positive_symptoms or resolved_symptoms:
        missing.extend(["症状演变", "其他伴随症状"])
    if not treatments:
        missing.append("处理经过")
    if resolved_symptoms:
        missing.append("当前体温")

    if not parts:
        return MedicalField.missing_field("现病史尚未形成有效内容")

    if absent_symptoms and not positive_symptoms and not resolved_symptoms and not measurements and not durations and not treatments:
        return _field_from_facts(
            "患者否认" + "、".join(_unique_names(absent_symptoms)) + "。",
            absent_symptoms,
            confidence=0.78,
            status="negative",
            missing_elements=[],
            hint="如仍有其他不适，请继续补问主要症状。",
        )

    suffix = ""
    if missing:
        suffix = f"{'、'.join(_unique(missing))}尚未提及。"
    value = "，".join(parts).rstrip("，；") + "。" + suffix
    return _field_from_facts(
        value,
        [*positive_symptoms, *absent_symptoms, *resolved_symptoms, *measurements, *durations, *treatments],
        confidence=0.72,
        status="partial" if missing else "complete",
        missing_elements=_unique(missing),
        hint=_first_follow_up(missing),
    )


def _build_accompanying_symptoms(positive_symptoms: list[ClinicalFact], chief: MedicalField) -> MedicalField:
    names = _unique_names(positive_symptoms)
    accompanying = [name for name in names if name != "发热"]
    if accompanying:
        return _field_from_facts(
            "、".join(accompanying),
            [fact for fact in positive_symptoms if fact.name in accompanying],
            confidence=0.78,
            status="partial",
            missing_elements=["其他伴随症状"],
            hint="还有咳嗽、咽痛、寒战或胸闷等不适吗？",
        )
    if chief.status == "partial" and chief.value and "发热" in chief.value:
        return MedicalField.missing_field("伴随症状尚未提及")
    return MedicalField.missing_field()


def _build_previous_treatment(treatments: list[ClinicalFact]) -> MedicalField:
    if not treatments:
        return MedicalField.missing_field("既往处理尚未提及")
    return _field_from_facts(
        "；".join(_unique([fact.value or fact.name for fact in treatments])),
        treatments,
        confidence=0.8,
        status="partial",
        missing_elements=["用药剂量", "处理时间"],
        hint="用药剂量和处理时间是什么？",
    )


def _field_from_facts(
    value: str,
    facts: list[ClinicalFact],
    *,
    confidence: float,
    status: Literal["complete", "partial", "negative", "conflicting"],
    missing_elements: list[str] | None = None,
    hint: str | None = None,
) -> MedicalField:
    spans = _merge_spans([fact.source_span for fact in facts if fact.evidence])
    return MedicalField(
        value=value,
        missing=False,
        status=status,
        hint=hint,
        confidence=confidence,
        source_spans=spans,
        missing_elements=missing_elements or [],
        fact_ids=[fact.fact_id for fact in facts],
    )


def _conflicting_field(field_value: MedicalField, reason: str) -> MedicalField:
    return MedicalField(
        value=field_value.value,
        missing=False,
        status="conflicting",
        hint=reason,
        confidence=field_value.confidence,
        source_spans=field_value.source_spans,
        missing_elements=field_value.missing_elements,
        fact_ids=field_value.fact_ids,
        confirmed_by_doctor=field_value.confirmed_by_doctor,
    )


def _span_text_supported(span_text: str, source_text: str) -> bool:
    span = re.sub(r"\s+", "", span_text or "")
    source = re.sub(r"\s+", "", source_text or "")
    return bool(span and (span in source or source in span))


def _merge_spans(spans: list[SourceSpan]) -> list[SourceSpan]:
    result: list[SourceSpan] = []
    seen: set[tuple[int | None, str]] = set()
    for span in spans:
        key = (span.index, span.text)
        if key in seen:
            continue
        seen.add(key)
        result.append(span)
    return result


def _unique_names(facts: list[ClinicalFact]) -> list[str]:
    return _unique([fact.name for fact in facts])


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _first_follow_up(missing: list[str]) -> str | None:
    if "起病时间" in missing:
        return "症状持续多久了？"
    if "症状演变" in missing:
        return "症状是持续存在还是反复出现？"
    if "处理经过" in missing:
        return "是否已经服药或在其他医院就诊？"
    return None
