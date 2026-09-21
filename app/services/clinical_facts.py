from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.schemas import CandidateDiagnosis, MedicalField, MedicalRecordFields, SourceSpan
from app.services.fever_respiratory_pack import infer_fever_respiratory_candidates


FactType = Literal["symptom", "measurement", "duration", "treatment", "allergy"]
Assertion = Literal["present", "absent", "resolved", "uncertain"]
Experiencer = Literal["patient", "family", "other", "unknown"]
Temporality = Literal["current", "historical", "resolved", "unknown"]
Certainty = Literal["confirmed", "uncertain"]
ReviewStatus = Literal["pending", "confirmed", "rejected"]


@dataclass(frozen=True)
class ClinicalFact:
    fact_id: str
    type: FactType
    name: str
    assertion: Assertion = "present"
    experiencer: Experiencer = "patient"
    temporality: Temporality = "current"
    certainty: Certainty = "confirmed"
    value: str | None = None
    unit: str | None = None
    evidence: str = ""
    evidence_span_id: str | None = None
    review_status: ReviewStatus = "pending"
    source_span: SourceSpan = field(default_factory=lambda: SourceSpan(text=""))


_SPLIT_RE = re.compile(r"[。！？!?\n]+")
_TEMP_RE = re.compile(r"(?P<value>3[5-9](?:\.\d)?|4[0-2](?:\.\d)?)\s*(?:°\s*)?(?:C|c|℃|度)")
_NEGATIVE_FEVER_RE = re.compile(r"(?:没有|没|无|不|否认).{0,4}(?:发热|发烧)")
_QUESTION_NEGATIVE_FEVER_RE = re.compile(
    r"(?:有没有|是否|问).{0,8}(?:发热|发烧).{0,16}(?:患者|病人)?(?:说|回答|称)?[：:，,\s]*(?:没有|没|无|不)"
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

_NEGATION_WORDS = ("没有", "没", "无", "不", "否认", "未")
_UNCERTAINTY_WORDS = ("不确定", "不知道", "说不清", "可能", "疑似", "不清楚")
_FAMILY_WORDS = ("父亲", "母亲", "家属", "孩子", "儿子", "女儿", "丈夫", "妻子", "爷爷", "奶奶")
_HISTORICAL_WORDS = ("既往", "曾经", "以前", "过去", "小时候")
_RESOLVED_WORDS = ("已缓解", "已经好了", "现在好了", "已退热", "已经退了", "已经脱敏", "现在已经脱敏", "不再")
_COUGH_SYNONYMS = ("咳嗽", "有点咳", "一直咳", "咳了")
_RESPIRATORY_SYMPTOMS = {
    "发热": ("发热", "发烧"),
    "咳嗽": _COUGH_SYNONYMS,
    "头痛": ("头很痛", "头痛", "头疼", "脑袋疼", "脑袋痛"),
    "胸闷": ("胸闷", "胸口闷", "胸部发闷"),
    "胸痛": ("胸痛", "胸口痛", "胸部疼痛"),
    "气促": ("气促", "气短", "喘不上气", "喘不过气"),
    "呼吸困难": ("呼吸困难", "呼吸费力"),
    "咽痛": ("咽痛", "嗓子痛", "喉咙痛"),
    "咳痰": ("咳痰", "有痰"),
    "寒战": ("寒战", "打寒颤", "发冷发抖"),
    "乏力": ("乏力", "没力气", "浑身无力"),
}

_ALLERGY_CONCEPTS = tuple(
    sorted(
        {
            "碘造影剂过敏", "阿司匹林过敏", "磺胺类过敏", "青霉素过敏", "头孢过敏",
            "食物过敏", "药物过敏", "花生过敏", "海鲜过敏", "鸡蛋过敏", "牛奶过敏",
            "芒果过敏", "酒精过敏", "乳胶过敏", "尘螨过敏", "花粉过敏", "猫毛过敏",
            "大豆过敏", "小麦过敏", "芝麻过敏", "核桃过敏", "鱼类过敏", "过敏",
        },
        key=len,
        reverse=True,
    )
)


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
        experiencer: Experiencer = "patient",
        temporality: Temporality = "current",
        certainty: Certainty = "confirmed",
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
                experiencer=experiencer,
                temporality=temporality,
                certainty=certainty,
                value=value,
                unit=unit,
                evidence=evidence,
                evidence_span_id=f"transcript-segment-{index + 1}" if index is not None else None,
                source_span=SourceSpan(
                    index=index,
                    text=evidence,
                ),
            )
        )
        next_id += 1

    question_negative_fever = _QUESTION_NEGATIVE_FEVER_RE.search(text)
    if question_negative_fever:
        add(type_="symptom", name="发热", assertion="absent", evidence=question_negative_fever.group(0), index=0)

    for fact_type, name, match in _answered_question_facts(text):
        if fact_type == "symptom" and name == "发热" and question_negative_fever:
            continue
        add(type_=fact_type, name=name, assertion="absent", evidence=match, index=0)

    for index, segment in enumerate(segments):
        normalized = _normalize_text(segment)
        if not normalized:
            continue

        if _is_unanswered_question(normalized):
            continue

        segment_experiencer = _experiencer(normalized)
        segment_temporality = _temporality(normalized)

        temp = _extract_temperature(normalized)
        if temp:
            add(
                type_="measurement",
                name="体温",
                experiencer=segment_experiencer,
                temporality=segment_temporality,
                value=temp,
                unit="℃",
                evidence=segment,
                index=index,
            )

        duration = _extract_duration(normalized)
        if duration:
            add(type_="duration", name="病程", experiencer=segment_experiencer, temporality=segment_temporality, value=duration, evidence=segment, index=index)

        if _contains_treatment(normalized):
            add(type_="treatment", name="既往处理", experiencer=segment_experiencer, temporality=segment_temporality, value=_treatment_value(normalized), evidence=segment, index=index)

        for allergy in _allergy_mentions(normalized):
            assertion, certainty = _semantic_assertion(normalized, allergy)
            add(
                type_="allergy",
                name=allergy,
                assertion=assertion,
                experiencer=segment_experiencer,
                temporality="resolved" if assertion == "resolved" else segment_temporality,
                certainty=certainty,
                evidence=segment,
                index=index,
            )

        for symptom_name, keywords in _RESPIRATORY_SYMPTOMS.items():
            matched_keyword = next((keyword for keyword in keywords if keyword in normalized), None)
            if not matched_keyword:
                continue
            assertion, certainty = _semantic_assertion(normalized, matched_keyword)
            add(
                type_="symptom",
                name=symptom_name,
                assertion=assertion,
                experiencer=segment_experiencer,
                temporality="resolved" if assertion == "resolved" else segment_temporality,
                certainty=certainty,
                evidence=segment,
                index=index,
            )

        if _RESOLVED_FEVER_RE.search(normalized) and not any(
            fact.type == "symptom" and fact.name == "发热" and fact.source_span.index == index for fact in facts
        ):
            add(
                type_="symptom",
                name="发热",
                assertion="resolved",
                experiencer=segment_experiencer,
                temporality="resolved",
                evidence=segment,
                index=index,
            )

        if temp and _temperature_number(temp) >= 37.3 and not any(
            fact.type == "symptom" and fact.name == "发热" and fact.source_span.index == index for fact in facts
        ):
            add(
                type_="symptom",
                name="发热",
                experiencer=segment_experiencer,
                temporality=segment_temporality,
                evidence=segment,
                index=index,
            )

    return _dedupe_facts(facts)


def build_fields_from_clinical_facts(text: str) -> MedicalRecordFields | None:
    facts = extract_clinical_facts(text)
    if not facts:
        return None

    patient_facts = [fact for fact in facts if fact.experiencer == "patient"]
    positive_symptoms = [fact for fact in patient_facts if fact.type == "symptom" and fact.assertion == "present"]
    absent_symptoms = [fact for fact in patient_facts if fact.type == "symptom" and fact.assertion == "absent"]
    resolved_symptoms = [fact for fact in patient_facts if fact.type == "symptom" and fact.assertion == "resolved"]
    measurements = [fact for fact in patient_facts if fact.type == "measurement"]
    durations = [fact for fact in patient_facts if fact.type == "duration"]
    treatments = [fact for fact in patient_facts if fact.type == "treatment"]
    allergies = [fact for fact in patient_facts if fact.type == "allergy"]

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
        allergy_history=_build_allergy_history(allergies, facts),
        physical_exam=MedicalField.missing_field("待医生查体补充"),
        candidate_diagnoses=infer_fever_respiratory_candidates(patient_facts),
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
        if strict_text_match and not all(_span_text_supported(span.text, text) for span in field_value.source_spans):
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
        return f"{_format_temperature_value(match.group('value'))}℃"
    for chinese, arabic in _CHINESE_TEMPERATURES.items():
        if f"{chinese}度" in text or f"{chinese}摄氏度" in text:
            return f"{arabic}℃"
    return None


def _format_temperature_value(value: str) -> str:
    if "." in value:
        return value.rstrip("0").rstrip(".")
    return value


def _temperature_number(value: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else 0.0


def _is_unanswered_question(text: str) -> bool:
    question = bool(re.search(r"(?:医生|医师|doctor|问).*(?:有没有|是否|是不是|吗|么|[?？])", text, re.I))
    patient_answer = bool(
        re.search(r"(?:患者|病人)(?:回答|说|称)[：:,，\s]*(?:有|没有|没|无|否认|不确定|不知道)", text)
        or re.search(r"(?:患者|病人)[：:]\s*(?:有|没有|没|无|否认|不确定|不知道)", text)
    )
    return question and not patient_answer


def _experiencer(text: str) -> Experiencer:
    if any(word in text for word in _FAMILY_WORDS):
        return "family"
    if re.search(r"(?:患者|病人|我|本人)", text):
        return "patient"
    return "patient"


def _temporality(text: str) -> Temporality:
    if any(word in text for word in _RESOLVED_WORDS):
        return "resolved"
    if any(word in text for word in _HISTORICAL_WORDS) or "昨天" in text:
        return "historical"
    return "current"


def _semantic_assertion(text: str, keyword: str) -> tuple[Assertion, Certainty]:
    mention = text.find(keyword)
    prefix = text[max(0, mention - 12) : mention] if mention >= 0 else text
    local_prefix = re.split(r"[，,；;]", prefix)[-1]
    if "不是没有" in local_prefix or "并非没有" in local_prefix:
        return "present", "confirmed"
    if any(word in text for word in _UNCERTAINTY_WORDS):
        return "uncertain", "uncertain"
    if any(word in text for word in _RESOLVED_WORDS):
        return "resolved", "confirmed"
    if any(word in local_prefix for word in _NEGATION_WORDS):
        return "absent", "confirmed"
    if re.search(r"(?:患者|病人)(?:回答|说|称)?[：:,，\s]*(?:没有|没|无|否认)(?:。|$)", text):
        return "absent", "confirmed"
    return "present", "confirmed"


def _allergy_mentions(text: str) -> list[str]:
    mentions: list[str] = []
    for concept in _ALLERGY_CONCEPTS:
        if concept not in text:
            continue
        if concept == "过敏" and any(item in text for item in mentions):
            continue
        mentions.append(concept)
    return mentions[:1]


def _answered_question_facts(text: str) -> list[tuple[FactType, str, str]]:
    results: list[tuple[FactType, str, str]] = []
    concepts: list[tuple[FactType, str, tuple[str, ...]]] = [
        ("allergy", item, (item,)) for item in _ALLERGY_CONCEPTS if item != "过敏"
    ]
    concepts.extend(("symptom", name, aliases) for name, aliases in _RESPIRATORY_SYMPTOMS.items())
    for fact_type, name, aliases in concepts:
        for alias in aliases:
            pattern = re.compile(
                rf"(?:医生|医师|doctor|问).{{0,18}}(?:有没有|是否).{{0,8}}{re.escape(alias)}"
                rf".{{0,24}}(?:患者|病人)(?:回答|说|称)?[：:,，\s]*(?:没有|没|无|否认)",
                re.I,
            )
            match = pattern.search(text)
            if match:
                results.append((fact_type, name, match.group(0)))
                break
    return results


def _symptom_assertion(text: str, keywords: tuple[str, ...]) -> Assertion | None:
    found_absent = False
    for keyword in keywords:
        for match in re.finditer(re.escape(keyword), text):
            prefix = text[max(0, match.start() - 8) : match.start()]
            if any(word in prefix for word in _NEGATION_WORDS):
                found_absent = True
                continue
            return "present"
    return "absent" if found_absent else None


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
    seen: set[tuple[str, str, str, str, str, str, str | None]] = set()
    for fact in facts:
        key = (
            fact.type,
            fact.name,
            fact.assertion,
            fact.experiencer,
            fact.temporality,
            fact.certainty,
            fact.value,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped


def _build_allergy_history(
    allergies: list[ClinicalFact],
    all_facts: list[ClinicalFact],
) -> MedicalField:
    if not allergies:
        if any(fact.type == "allergy" and fact.experiencer == "family" for fact in all_facts):
            return MedicalField.missing_field("仅提及家族过敏信息，患者本人过敏史尚未确认")
        return MedicalField.missing_field("过敏史尚未提及")

    exact_evidence = "；".join(_unique([fact.evidence for fact in allergies if fact.evidence]))
    uncertain = [fact for fact in allergies if fact.assertion == "uncertain"]
    resolved = [fact for fact in allergies if fact.assertion == "resolved"]
    if uncertain:
        return _field_from_facts(
            exact_evidence,
            allergies,
            confidence=0.55,
            status="partial",
            missing_elements=["当前过敏状态"],
            hint="过敏状态不确定，需医生核实后确认。",
        )
    if resolved:
        return _field_from_facts(
            exact_evidence,
            allergies,
            confidence=0.72,
            status="partial",
            missing_elements=["当前过敏风险"],
            hint="既往过敏或脱敏状态需医生复核。",
        )
    return _field_from_facts(
        exact_evidence,
        allergies,
        confidence=0.86,
        status="complete",
        missing_elements=[],
        hint=None,
    )


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
            status="complete",
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
    status: Literal["complete", "partial", "conflicting"],
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
    return bool(span and span in source)


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
