from __future__ import annotations

from typing import Any
import re
from app.services.clinical_facts import (
    _CLAUSE_BREAK as _CLINICAL_CLAUSE_BREAK,
    clinical_experiencer,
    clinical_segment_contexts,
    extract_clinical_facts,
)
from app.services.privacy import anonymize_text


LIVE_DRAFT_STATUS = "temporary"
MAX_SUMMARY_ITEMS = 3


def _patient_fact_text(segment: dict[str, Any]) -> str:
    """Select source clauses before any live rule sees symptom keywords.

    Unresolved speakers remain in the transcript, but are not patient facts.
    Speaker identity alone is insufficient: a patient can describe a relative,
    and a family member can explicitly report the child's symptoms.
    """
    role = {
        "患者": "患者", "病人": "患者", "patient": "患者",
        "医生": "医生", "医师": "医生", "doctor": "医生",
        "家属": "家属", "家长": "家属", "陪同人员": "家属",
    }.get(str(segment.get("role") or "").strip().lower())
    if role is None:
        return ""
    text = str(segment.get("text") or "")
    prefix = f"{role}："
    target = "child" if role == "家属" and re.search(r"孩子|儿子|女儿", text) else "unknown"
    selected = []
    subject_context = prefix
    for sentence in re.finditer(r"[^。！？!?\n]+[。！？!?]?", text):
        value = sentence.group()
        contexts = clinical_segment_contexts(prefix + value)
        if not contexts or contexts[0].question or re.search(r"有没有|是否|是不是|[?？]|(?:吗|么|呢)[。\s]*$", value):
            continue
        # A doctor's own symptoms or an unanchored observation are not the
        # patient's history. Explicit patient observations remain usable.
        if role == "医生" and not re.search(r"患者|病人|患儿", value):
            continue
        clauses = []
        # Use the same contrast boundaries as clinical fact polarity/subject
        # parsing, so the final speaker's clause cannot claim earlier facts.
        for clause in _CLINICAL_CLAUSE_BREAK.split(value):
            quote = clause.strip("。！？!? \t\r\n")
            if not quote:
                continue
            if re.search(r"(?:我是|我叫).*(?:妈妈|爸爸|母亲|父亲|家属|家长)", quote):
                # Resolve an introduction as the reporter, not as the child
                # named inside it. This context is never emitted as evidence.
                subject_context += "我自己，"
                continue
            subject_context += quote + "，"
            doctor_subjects = re.findall(r"患者|病人|我|本人", subject_context)
            if role == "医生" and doctor_subjects and doctor_subjects[-1] in {"我", "本人"}:
                continue
            if clinical_experiencer(
                subject_context, speaker=role, patient_target=target
            ) == "patient":
                clauses.append(quote)
        if clauses:
            selected.append("，".join(clauses))
    return "。".join(selected)


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
    fact_segments = []
    for segment in usable_segments:
        text = _patient_fact_text(segment)
        if text:
            fact_segments.append({**segment, "text": text})
    # Keep each source attached while assembling temporary fields. Joining all
    # text first loses the relation between a fact and its recording segment.
    for segment in fact_segments:
        segment["text"] = anonymize_text(segment["text"])
    combined = " ".join(segment["text"] for segment in fact_segments)
    record_patch = _build_sourced_record_patch(fact_segments)
    alerts_by_id: dict[str, dict[str, Any]] = {}
    for segment in fact_segments:
        ids = [str(segment["segment_id"])] if segment.get("segment_id") else []
        for alert in _build_alerts(segment["text"], ids):
            if alert["id"] in alerts_by_id:
                current = alerts_by_id[alert["id"]]["evidence_segment_ids"]
                current.extend(value for value in ids if value not in current)
            else:
                alerts_by_id[alert["id"]] = alert
    alerts = list(alerts_by_id.values())
    missing_items = _build_missing_items(combined)
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
        # No guideline-backed decision service is connected to this live path.
        # Preserve the event schema without inventing diagnoses or test orders.
        "differentials": [],
        "care_plan": [],
        "next_questions": next_questions[:MAX_SUMMARY_ITEMS],
        "stable_segment_count": len(usable_segments),
    }


def _build_sourced_record_patch(segments: list[dict[str, Any]]) -> dict[str, Any]:
    parts = []
    for segment in segments:
        ids = [str(segment["segment_id"])] if segment.get("segment_id") else []
        parts.append((segment["text"], ids, _build_record_patch(segment["text"], ids)))
    combined = " ".join(text for text, _, _ in parts)
    patch = _build_record_patch(combined, [])
    for name in list(patch):
        if name == "present_illness":
            # The preview is intentionally bounded; cite only sources whose
            # text actually falls inside that displayed prefix.
            consumed, ids = 0, []
            for text, source_ids, _ in parts:
                if consumed >= 120:
                    break
                ids.extend(source_ids)
                consumed += len(" ".join(text.split())) + 1
            patch[name]["evidence_segment_ids"] = list(dict.fromkeys(ids))
            continue
        relevant = [field_map[name] for _, _, field_map in parts if name in field_map]
        if name == "chief_complaint":
            terms = patch[name]["value"].split("伴")
            relevant = [field for field in relevant if any(term in field["value"] for term in terms)]
        else:
            # A field value is composed only from the matching source fields,
            # not from one arbitrary sentence in the complete transcript.
            patch[name]["value"] = "；".join(dict.fromkeys(field["value"] for field in relevant))
        if not relevant:
            del patch[name]
            continue
        patch[name]["evidence_segment_ids"] = list(dict.fromkeys(
            value for field in relevant for value in field["evidence_segment_ids"]
        ))
    return patch


def _build_record_patch(text: str, evidence_ids: list[str]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if _contains_any(text, ["发热", "发烧", "体温"]) or _contains_any(text, ["咳嗽", "咳痰"]):
        complaint = []
        if _contains_any(text, ["发热", "发烧", "体温"]) and not re.search(r"(?:无|没有|否认|不).{0,4}(?:发热|发烧)", text):
            complaint.append("发热")
        if _contains_any(text, ["咳嗽", "咳痰"]) and not re.search(r"(?:无|没有|否认|不).{0,4}(?:咳嗽|咳痰)", text):
            complaint.append("咳嗽")
        if complaint:
            patch["chief_complaint"] = _field("伴".join(complaint), evidence_ids)
    if text:
        patch["present_illness"] = _field(_compact_text(text, 120), evidence_ids)
    allergy_facts = [
        fact
        for fact in extract_clinical_facts(text)
        # Subjects have already been resolved per source clause, before
        # concatenation discards speaker context (including child reports).
        if fact.type == "allergy"
    ]
    if allergy_facts:
        allergy_text = "；".join(dict.fromkeys(fact.field_excerpt or fact.evidence for fact in allergy_facts))
        patch["allergy_history"] = _field(allergy_text, evidence_ids)
    if _contains_any(text, ["既往", "高血压", "糖尿病"]):
        patch["past_history"] = _field(_extract_sentence(text, "既往") or "提及既往史，需医生确认", evidence_ids)
    if _contains_any(text, ["胸痛", "呼吸困难", "气短", "喘"]):
        quote = next((_extract_sentence(text, k) for k in ["胸痛", "呼吸困难", "气短", "喘"] if k in text), "")
        patch["associated_symptoms"] = _field(quote, evidence_ids)
    return patch


def _field(value: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "value": value,
        "state": "updated",
        "temporary": True,
        "evidence_segment_ids": list(dict.fromkeys(evidence_ids)),
    }


def _build_alerts(text: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if _contains_any(text, ["胸痛", "呼吸困难", "气短"]):
        alerts.append(
            {
                "id": "danger-breathing",
                "title": "转写提及呼吸困难或胸痛",
                "summary": "请优先核对这段患者原话；本提示只定位症状，不代表诊断或检查建议。",
                "severity": "warning",
                "evidence_segment_ids": list(dict.fromkeys(evidence_ids)),
                "status": LIVE_DRAFT_STATUS,
            }
        )
    if _contains_any(text, ["四十度", "40度", "高热"]):
        alerts.append(
            {
                "id": "danger-high-fever",
                "title": "转写提及高热",
                "summary": "请核对这段体温原话；本提示不代表诊断或处理方案。",
                "severity": "warning",
                "evidence_segment_ids": list(dict.fromkeys(evidence_ids)),
                "status": LIVE_DRAFT_STATUS,
            }
        )
    return alerts


def _build_missing_items(text: str) -> list[dict[str, Any]]:
    return [
        {"id": f"missing-{key}", "summary": question, "status": "pending_doctor_question"}
        for key, question in _unanswered_questions(text)
    ]


def _build_next_questions(text: str) -> list[dict[str, Any]]:
    return [
        {"id": f"next-{key}", "question": question}
        for key, question in _unanswered_questions(text)
    ]


def _unanswered_questions(text: str) -> list[tuple[str, str]]:
    """Ask about missing source information, without inferring a diagnosis.

    Only explicit answers in patient-filtered clauses suppress a question.
    A cough's duration must not silently become the duration of fever.
    """
    questions: list[tuple[str, str]] = []
    clauses = re.split(r"[，,。；;!?！？\n]", text)
    uncertainty = r"可能|不确定|不知道|不清楚|说不清|好像|估计|没有量|没量|未测|没测"
    certain_clauses = [clause for clause in clauses if not re.search(uncertainty, clause)]
    if _contains_any(text, ["发热", "发烧"]):
        measured = any(
            not re.search(uncertainty, clause)
            and any(fact.type == "measurement" for fact in extract_clinical_facts(clause))
            for clause in clauses
        )
        duration = any(
            _contains_any(clause, ["发热", "发烧"])
            and not re.search(uncertainty, clause)
            and any(fact.type == "duration" for fact in extract_clinical_facts(clause))
            for clause in clauses
        )
        missing = []
        if not measured:
            missing.append("最高体温")
        if not duration:
            missing.append("发热持续时间")
        if missing:
            questions.append(("temperature", "请补充" + "和".join(missing) + "。"))
    if _contains_any(text, ["咳嗽", "咳痰"]):
        # A tentative colour or an explicit unknown is not an answered slot.
        answered = "。".join(certain_clauses)
        absent = re.search(r"(?:没有|没|无|不)\s*(?:咳)?痰|干咳", answered)
        color = re.search(r"(?:白|黄|绿|红|血|透明|清|铁锈).{0,2}痰|痰.{0,4}(?:白|黄|绿|红|血|透明|清|铁锈)", answered)
        amount = re.search(r"(?:少量|大量|很多|不多|一点|较多|较少).{0,3}痰|痰.{0,4}(?:少量|大量|很多|不多|一点|较多|较少)", answered)
        if not absent and not (color and amount):
            needed = [name for name, known in (("痰的颜色", color), ("痰量", amount)) if not known]
            questions.append(("sputum", "是否咳痰？如有，请补充" + "和".join(needed) + "。"))
    exposure_known = any(re.search(r"接触史|接触过|接触了|接触患者|接触病人|没接触|未接触|无接触", clause) for clause in certain_clauses)
    if _contains_any(text, ["发热", "咳嗽"]) and not exposure_known:
        questions.append(("exposure", "是否有流感或呼吸道感染接触史？"))
    allergy_known = any(
        fact.type == "allergy" and fact.assertion != "uncertain"
        for fact in extract_clinical_facts(text)
    )
    if _contains_any(text, ["用药", "退烧药", "抗生素"]) and not allergy_known:
        questions.append(("allergy", "请确认药物过敏史。"))
    return questions


def _contains_any(text: str, keywords: list[str]) -> bool:
    clauses = re.split(r"[，,。；;!?！？\n]", text)
    return any(keyword in clause and not re.search(r"(?:无|没有|否认|不|未).{0,5}" + re.escape(keyword), clause)
               for clause in clauses for keyword in keywords)


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
