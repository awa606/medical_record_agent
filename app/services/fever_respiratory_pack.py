from __future__ import annotations

import re
from typing import Any

from app.schemas import CandidateDiagnosis, SourceSpan


PACK_VERSION = "fever_respiratory_v1"


def infer_fever_respiratory_candidates(facts: list[Any]) -> list[CandidateDiagnosis]:
    present_symptoms = _symptom_names(facts, "present")
    resolved_symptoms = _symptom_names(facts, "resolved")
    absent_symptoms = _symptom_names(facts, "absent")
    measurements = [fact for fact in facts if getattr(fact, "type", None) == "measurement"]
    durations = [fact for fact in facts if getattr(fact, "type", None) == "duration"]

    has_current_fever = "发热" in present_symptoms or any(_temperature_value(fact) for fact in measurements)
    has_fever_history = has_current_fever or "发热" in resolved_symptoms
    if not has_fever_history or ("发热" in absent_symptoms and not has_current_fever):
        return []

    candidates: list[CandidateDiagnosis] = []
    candidates.append(_fever_workup_candidate(facts, durations, measurements, present_symptoms))

    if has_current_fever and "头痛" in present_symptoms:
        candidates.append(_influenza_like_candidate(facts, durations, measurements, present_symptoms))

    if has_current_fever and "咳嗽" in present_symptoms:
        candidates.append(_pulmonary_infection_candidate(facts, durations, measurements, present_symptoms))

    candidates.sort(key=lambda item: item.confidence or 0.0, reverse=True)
    return candidates[:3]


def _fever_workup_candidate(
    facts: list[Any],
    durations: list[Any],
    measurements: list[Any],
    symptoms: set[str],
) -> CandidateDiagnosis:
    missing = _common_missing(durations, symptoms)
    confidence = 0.66 + (0.06 if measurements else 0.0) + (0.04 if durations else 0.0)
    return CandidateDiagnosis(
        name="发热待查",
        evidence=_evidence_spans(facts),
        reason=_reason("发热、体温或退热相关事实支持发热待查方向", missing, confidence),
        rule_id="FEVER_RESP_V1_FEVER_WORKUP",
        confidence=round(min(confidence, 0.84), 2),
        suggested_checks=[
            "复测体温并记录热型。",
            "由医生结合查体判断是否完善血常规、CRP 或病原学检查。",
        ],
        medication_notes=["退热、抗感染或其他治疗必须由医生确认；系统不生成处方。"],
        risk_warnings=["持续高热、意识异常、胸痛、气促或脱水表现需医生及时评估。"],
        follow_up_questions=_follow_up_questions(missing),
    )


def _influenza_like_candidate(
    facts: list[Any],
    durations: list[Any],
    measurements: list[Any],
    symptoms: set[str],
) -> CandidateDiagnosis:
    missing = _common_missing(durations, symptoms)
    missing.extend(["流行病学接触史", "肌肉酸痛或乏力"])
    confidence = 0.62 + (0.05 if measurements else 0.0)
    return CandidateDiagnosis(
        name="流感样症状参考",
        evidence=_evidence_spans(facts),
        reason=_reason("发热伴头痛可作为流感样症状筛查线索", missing, confidence),
        rule_id="FEVER_RESP_V1_INFLUENZA_LIKE",
        confidence=round(min(confidence, 0.78), 2),
        suggested_checks=[
            "询问流感样病例接触史和近期聚集性发病情况。",
            "由医生判断是否需要病原学检测。",
        ],
        medication_notes=["抗病毒或退热治疗需医生结合病程和禁忌证判断；系统不生成处方。"],
        risk_warnings=["高热不退、精神差、呼吸困难或基础病患者需提高警惕。"],
        follow_up_questions=_follow_up_questions(missing),
    )


def _pulmonary_infection_candidate(
    facts: list[Any],
    durations: list[Any],
    measurements: list[Any],
    symptoms: set[str],
) -> CandidateDiagnosis:
    missing = _common_missing(durations, symptoms)
    missing.extend(["痰液性状", "胸痛或气促", "肺部听诊"])
    high_temp = any((_temperature_value(fact) or 0.0) >= 38.5 for fact in measurements)
    confidence = 0.64 + (0.08 if high_temp else 0.0)
    return CandidateDiagnosis(
        name="肺部感染待排",
        evidence=_evidence_spans(facts),
        reason=_reason("发热伴咳嗽提示需排查下呼吸道感染", missing, confidence),
        rule_id="FEVER_RESP_V1_PULMONARY_INFECTION",
        confidence=round(min(confidence, 0.82), 2),
        suggested_checks=[
            "医生查体补充肺部听诊。",
            "由医生判断是否完善胸部影像、血常规或 CRP。",
        ],
        medication_notes=["抗感染、止咳化痰等治疗需医生确认；系统不生成处方。"],
        risk_warnings=["胸痛、气促、持续高热或咳脓痰加重时需医生进一步评估。"],
        follow_up_questions=_follow_up_questions(missing),
    )


def _symptom_names(facts: list[Any], assertion: str) -> set[str]:
    return {
        str(getattr(fact, "name", ""))
        for fact in facts
        if getattr(fact, "type", None) == "symptom" and getattr(fact, "assertion", None) == assertion
    }


def _common_missing(durations: list[Any], symptoms: set[str]) -> list[str]:
    missing: list[str] = []
    if not durations:
        missing.append("持续时间")
    if "咳嗽" not in symptoms:
        missing.append("呼吸道症状")
    if "头痛" not in symptoms:
        missing.append("全身症状")
    return missing


def _follow_up_questions(missing: list[str]) -> list[str]:
    question_map = {
        "持续时间": "症状持续多久了？",
        "呼吸道症状": "是否有咳嗽、咽痛、鼻塞流涕或咳痰？",
        "全身症状": "是否有头痛、肌肉酸痛、乏力或寒战？",
        "流行病学接触史": "近期是否接触过发热或流感样症状患者？",
        "肌肉酸痛或乏力": "是否有明显肌肉酸痛或乏力？",
        "痰液性状": "是否咳痰，痰的颜色和量如何？",
        "胸痛或气促": "是否有胸痛、气促或呼吸困难？",
        "肺部听诊": "需医生查体补充肺部听诊结果。",
    }
    return [question_map[item] for item in dict.fromkeys(missing) if item in question_map][:3]


def _reason(support: str, missing: list[str], confidence: float) -> str:
    missing_text = "、".join(dict.fromkeys(missing)) or "暂无明显缺失"
    return (
        f"{PACK_VERSION}；规则匹配度 {confidence:.2f}。"
        f"支持证据：{support}。缺失证据：{missing_text}。仅供鉴别诊断参考，需医生判断。"
    )


def _evidence_spans(facts: list[Any]) -> list[SourceSpan]:
    spans: list[SourceSpan] = []
    seen: set[tuple[int | None, str]] = set()
    for fact in facts:
        span = getattr(fact, "source_span", None)
        if not isinstance(span, SourceSpan) or not span.text:
            continue
        identity = (span.index, span.text)
        if identity in seen:
            continue
        seen.add(identity)
        spans.append(span)
    return spans


def _temperature_value(fact: Any) -> float | None:
    if getattr(fact, "name", None) != "体温":
        return None
    value = str(getattr(fact, "value", "") or "")
    match = re.search(r"\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


__all__ = ["PACK_VERSION", "infer_fever_respiratory_candidates"]
