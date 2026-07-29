from __future__ import annotations

from typing import Any


LIVE_DRAFT_STATUS = "temporary"
MAX_SUMMARY_ITEMS = 3


def normalize_live_segment(segment: dict[str, Any], *, sequence: int | None = None) -> dict[str, Any]:
    text = str(segment.get("text") or "").strip()
    segment_id = str(segment.get("segment_id") or segment.get("id") or f"live-seg-{sequence or 0}")
    return {
        "segment_id": segment_id,
        "sequence": int(sequence if sequence is not None else segment.get("sequence") or 0),
        "text": text,
        "speaker": segment.get("speaker"),
        "role": segment.get("role"),
        "start_time": segment.get("start_time"),
        "end_time": segment.get("end_time"),
    }


def merge_live_segment(state: dict[str, Any], segment: dict[str, Any]) -> bool:
    segments = [item for item in state.get("stable_segments") or [] if isinstance(item, dict)]
    segment_id = str(segment.get("segment_id") or "")
    sequence = int(segment.get("sequence") or 0)
    for index, item in enumerate(segments):
        if item.get("segment_id") == segment_id or int(item.get("sequence") or 0) == sequence:
            if item == segment:
                state["stable_segments"] = segments
                return False
            segments[index] = segment
            state["stable_segments"] = sorted(segments, key=lambda value: int(value.get("sequence") or 0))
            return True
    segments.append(segment)
    state["stable_segments"] = sorted(segments, key=lambda value: int(value.get("sequence") or 0))
    return True


def should_emit_live_snapshot(
    state: dict[str, Any],
    *,
    based_on_sequence: int,
    min_new_segments: int = 3,
) -> bool:
    if state.get("version") is None:
        return True
    raw_last_sequence = state.get("based_on_sequence")
    last_sequence = -1 if raw_last_sequence is None else int(raw_last_sequence)
    return based_on_sequence - last_sequence >= min_new_segments


def merge_snapshot_if_newer(current: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if current is None:
        return candidate
    if int(candidate.get("version") or 0) <= int(current.get("version") or 0):
        return current
    return candidate


def build_live_clinical_snapshot(
    *,
    session_id: str,
    stable_segments: list[dict[str, Any]],
    version: int,
    based_on_sequence: int,
    updated_at: str,
) -> dict[str, Any]:
    usable_segments = [segment for segment in stable_segments if str(segment.get("text") or "").strip()]
    combined = " ".join(str(segment.get("text") or "") for segment in usable_segments)
    evidence_ids = [str(segment.get("segment_id")) for segment in usable_segments if segment.get("segment_id")]
    record_patch = _build_record_patch(combined, evidence_ids)
    alerts = _build_alerts(combined, evidence_ids)
    missing_items = _build_missing_items(combined)
    differentials = _build_differentials(combined, evidence_ids)
    care_plan = _build_care_plan(combined, evidence_ids)
    next_questions = _build_next_questions(combined)

    return {
        "live_session_id": session_id,
        "session_id": session_id,
        "version": int(version),
        "based_on_sequence": int(based_on_sequence),
        "status": LIVE_DRAFT_STATUS,
        "temporary": True,
        "updated_at": updated_at,
        "record_patch": record_patch,
        "alerts": alerts[:MAX_SUMMARY_ITEMS],
        "missing_items": missing_items[:MAX_SUMMARY_ITEMS],
        "differentials": differentials[:MAX_SUMMARY_ITEMS],
        "care_plan": care_plan[:MAX_SUMMARY_ITEMS],
        "next_questions": next_questions[:MAX_SUMMARY_ITEMS],
        "stable_segment_count": len(usable_segments),
    }


def _build_record_patch(text: str, evidence_ids: list[str]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if _contains_any(text, ["发热", "发烧", "体温"]) or _contains_any(text, ["咳嗽", "咳痰"]):
        complaint = []
        if _contains_any(text, ["发热", "发烧", "体温"]):
            complaint.append("发热")
        if _contains_any(text, ["咳嗽", "咳痰"]):
            complaint.append("咳嗽")
        patch["chief_complaint"] = _field("伴".join(complaint) or "发热呼吸道症状", evidence_ids)
    if text:
        patch["present_illness"] = _field(_compact_text(text, 120), evidence_ids)
    if _contains_any(text, ["过敏"]):
        patch["allergy_history"] = _field(_extract_sentence(text, "过敏") or "提及过敏史，需医生确认", evidence_ids)
    if _contains_any(text, ["既往", "高血压", "糖尿病"]):
        patch["past_history"] = _field(_extract_sentence(text, "既往") or "提及既往史，需医生确认", evidence_ids)
    if _contains_any(text, ["胸痛", "呼吸困难", "气短", "喘"]):
        patch["associated_symptoms"] = _field("存在胸痛、呼吸困难或气短相关表述，需重点复核", evidence_ids)
    return patch


def _field(value: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "value": value,
        "state": "updated",
        "temporary": True,
        "evidence_segment_ids": evidence_ids[:5],
    }


def _build_alerts(text: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if _contains_any(text, ["胸痛", "呼吸困难", "气短"]):
        alerts.append(
            {
                "id": "danger-breathing",
                "title": "呼吸困难或胸痛需优先评估",
                "summary": "转写中出现胸痛、呼吸困难或气短相关表述，建议医生立即追问并评估生命体征。",
                "severity": "warning",
                "evidence_segment_ids": evidence_ids[:5],
                "status": LIVE_DRAFT_STATUS,
            }
        )
    if _contains_any(text, ["四十度", "40度", "高热"]):
        alerts.append(
            {
                "id": "danger-high-fever",
                "title": "高热需要风险复核",
                "summary": "出现高热相关表述，建议结合体温、精神状态和基础疾病复核。",
                "severity": "warning",
                "evidence_segment_ids": evidence_ids[:5],
                "status": LIVE_DRAFT_STATUS,
            }
        )
    return alerts


def _build_missing_items(text: str) -> list[dict[str, Any]]:
    candidates = [
        ("missing-temperature", "补充最高体温和持续时间", ["发热", "发烧", "体温"]),
        ("missing-sputum", "补充咳痰颜色和痰量", ["咳嗽", "咳痰"]),
        ("missing-exposure", "询问流感或呼吸道感染接触史", ["发热", "咳嗽"]),
        ("missing-allergy", "确认药物过敏史", ["用药", "退烧药", "抗生素"]),
    ]
    return [
        {"id": item_id, "summary": summary, "status": "pending_doctor_question"}
        for item_id, summary, keywords in candidates
        if _contains_any(text, keywords)
    ]


def _build_differentials(text: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if _contains_any(text, ["发热", "发烧", "体温"]):
        items.append(
            _differential(
                "diff-fever",
                "发热待查",
                "已出现发热相关证据，需要结合病程、体温和伴随症状继续判断。",
                evidence_ids,
            )
        )
    if _contains_any(text, ["咳嗽", "咳痰", "胸痛", "呼吸困难"]):
        items.append(
            _differential(
                "diff-lung-infection",
                "肺部感染",
                "发热伴呼吸道症状时需排查肺部感染。",
                evidence_ids,
            )
        )
    if _contains_any(text, ["咽痛", "流感", "乏力", "肌肉酸痛"]):
        items.append(
            _differential(
                "diff-influenza",
                "甲型流感",
                "发热合并全身症状或接触史时，可作为鉴别诊断参考。",
                evidence_ids,
            )
        )
    return items


def _differential(item_id: str, name: str, summary: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "summary": summary,
        "supporting_evidence": evidence_ids[:5],
        "missing_evidence": ["需医生补充问诊和查体"],
        "recommended_questions": ["继续询问病程、最高体温、伴随症状和接触史"],
        "recommended_tests": ["血常规", "CRP"],
        "confidence_state": "preliminary",
        "status": LIVE_DRAFT_STATUS,
    }


def _build_care_plan(text: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    if _contains_any(text, ["发热", "发烧", "咳嗽", "咳痰"]):
        plans.append(
            _care_plan(
                "care-cbc-crp",
                "完善血常规及CRP",
                "评估感染及炎症程度。",
                evidence_ids,
            )
        )
    if _contains_any(text, ["咳嗽", "咽痛", "流感"]):
        plans.append(
            _care_plan(
                "care-respiratory-pathogen",
                "考虑呼吸道病原检测",
                "结合流行病学史和症状判断是否需要病原学检测。",
                evidence_ids,
            )
        )
    if _contains_any(text, ["发热", "发烧"]):
        plans.append(
            _care_plan(
                "care-supportive",
                "对症支持处理",
                "根据体温、饮水、精神状态和禁忌证进行医生确认后的对症处理。",
                evidence_ids,
            )
        )
    return plans


def _care_plan(item_id: str, title: str, summary: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "summary": summary,
        "reason": "来自实时转写稳定片段的临时参考，需医生确认。",
        "evidence_segment_ids": evidence_ids[:5],
        "status": "pending_doctor_confirmation",
    }


def _build_next_questions(text: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    if _contains_any(text, ["发热", "发烧"]):
        questions.append({"id": "next-temperature", "question": "最高体温是多少，持续了几天？"})
    if _contains_any(text, ["咳嗽", "咳痰"]):
        questions.append({"id": "next-sputum", "question": "是否咳痰，痰的颜色和量如何？"})
    if _contains_any(text, ["胸痛", "呼吸困难", "气短"]):
        questions.append({"id": "next-red-flags", "question": "是否有胸痛、气短、喘憋或血氧下降？"})
    return questions


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _compact_text(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit].rstrip()}..."


def _extract_sentence(text: str, keyword: str) -> str:
    for separator in ["。", "；", ";", "\n"]:
        for sentence in text.split(separator):
            if keyword in sentence:
                return _compact_text(sentence, 80)
    return ""
