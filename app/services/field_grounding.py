"""Conservative extractive grounding, independent of model confidence."""
from __future__ import annotations

import re
from typing import Any

from app.schemas import MedicalRecordFields, SourceSpan
from app.services.clinical_facts import split_clinical_segments

FIELD_KEYS = ("chief_complaint", "present_illness", "previous_treatment", "accompanying_symptoms", "past_history", "allergy_history", "physical_exam")

def compact(text: str) -> str:
    return re.sub(r"[\s，,。；;、：:！？!?]", "", text).replace("发烧", "发热").replace("摄氏度", "℃")


def reconcile_extractive_fields(
    fields: MedicalRecordFields,
    trusted_segments: list[dict[str, Any]] | None,
) -> tuple[MedicalRecordFields, dict[str, dict[str, Any]]]:
    """Replace model paraphrases with uniquely matched, role-safe source quotes.

    The language model is still responsible for selecting the fields and spans.
    This function only canonicalizes a selected span when it maps to exactly one
    reviewed source segment. Unsupported spans are removed from the field value
    instead of being allowed to survive as a paraphrase. The normal grounding
    gate runs afterwards and remains authoritative.
    """

    if not trusted_segments:
        return fields, {}

    repairs: dict[str, dict[str, Any]] = {}
    for key in FIELD_KEYS:
        field = getattr(fields, key)
        if not field.value or not field.source_spans:
            continue

        canonical: list[SourceSpan] = []
        rejected: list[str] = []
        seen: set[tuple[str | None, str]] = set()
        for span in field.source_spans:
            span_text = str(span.text or "").strip()
            if not span_text:
                rejected.append("empty_span")
                continue

            matches = [
                segment
                for segment in trusted_segments
                if span_text and compact(span_text) in compact(str(segment.get("text") or ""))
            ]
            if span.segment_id:
                matches = [
                    segment for segment in matches
                    if str(segment.get("segment_id") or "") == span.segment_id
                ]
            if len(matches) != 1:
                rejected.append("ambiguous_or_missing_segment")
                continue

            segment = matches[0]
            role = str(segment.get("role") or "")
            text = str(segment.get("text") or "").strip()
            is_doctor_question = role in {"医生", "doctor"} and bool(
                re.search(r"吗|么|有没有|是否|[?？]", text)
            )
            if role not in {"患者", "patient"} and not (
                key == "physical_exam" and role in {"医生", "doctor"} and not is_doctor_question
            ):
                rejected.append("role_not_allowed")
                continue

            segment_id = str(segment.get("segment_id") or "") or None
            dedupe_key = (segment_id, text)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            canonical.append(
                SourceSpan(
                    text=text,
                    segment_id=segment_id,
                    index=None,
                    start_time=segment.get("start_time"),
                    end_time=segment.get("end_time"),
                )
            )

        if not canonical:
            # No model-selected quote can be tied to one reviewed patient
            # segment. Treat the field as absent from the trusted extraction
            # rather than carrying a paraphrase into the medical record. The
            # original ASR remains available to the doctor for manual review.
            field.value = None
            field.source_spans = []
            field.missing = True
            field.status = "missing"
            field.confidence = None
            field.hint = "模型提取内容缺少唯一、角色可信的原文片段，请医生从转写补录。"
            if "缺少可信患者原文证据" not in field.missing_elements:
                field.missing_elements.append("缺少可信患者原文证据")
            repairs[key] = {
                "strategy": "discard_unsupported_field",
                "original_value_changed": True,
                "accepted_span_count": 0,
                "rejected_span_count": len(rejected),
                "rejected_reasons": sorted(set(rejected)),
            }
            continue

        original_value = field.value
        field.value = "；".join(span.text.rstrip("，,。；; ") for span in canonical)
        field.source_spans = canonical
        field.missing = False
        if rejected:
            field.status = "partial"
            if "需医生复核被移除的模型改写" not in field.missing_elements:
                field.missing_elements.append("需医生复核被移除的模型改写")
            field.hint = "已移除无法唯一定位或角色不允许的模型引用，请医生复核。"
        elif field.status == "conflicting":
            field.status = "complete"
            field.hint = None
        repairs[key] = {
            "strategy": "canonical_source_quotes",
            "original_value_changed": compact(original_value) != compact(field.value),
            "accepted_span_count": len(canonical),
            "rejected_span_count": len(rejected),
            "rejected_reasons": sorted(set(rejected)),
        }

    return fields, repairs

def ground_fields(fields: MedicalRecordFields, source: str, trusted_segments: list[dict] | None = None) -> MedicalRecordFields:
    segments = split_clinical_segments(source)
    for key in FIELD_KEYS:
        field = getattr(fields, key)
        field.confirmed_by_doctor = False
        field.doctor_review_status = "pending"
        manual_doctor_edit = str(field.doctor_review_note or "").startswith("manual_doctor_edit_v1:")
        if not field.value:
            continue
        errors = []
        if field.missing:
            errors.append("非空字段不能标记为未提及")
        if not field.source_spans and not manual_doctor_edit:
            errors.append("缺少转写证据")
        for span in field.source_spans:
            matching = [s for s in segments if span.text and compact(span.text) in compact(s)]
            if not span.text or compact(span.text) not in compact(source):
                errors.append("引用不在原始转写中")
            if span.index is not None and (span.index < 0 or span.index >= len(segments) or compact(span.text) not in compact(segments[span.index])):
                errors.append("引用片段序号不匹配")
            if span.segment_id is not None:
                trusted = next((s for s in trusted_segments or [] if s.get('segment_id') == span.segment_id), None)
                if trusted is None or compact(span.text) not in compact(trusted.get('text', '')):
                    errors.append("转写片段身份或原文不匹配")
            if trusted_segments:
                matches = [s for s in trusted_segments if span.text and compact(span.text) in compact(s.get('text', ''))]
                if span.segment_id:
                    matches = [s for s in matches if s.get('segment_id') == span.segment_id]
                if len(matches) == 1:
                    trusted = matches[0]
                    span.segment_id = trusted.get('segment_id')
                    if trusted.get('role') not in {'患者', '医生'}:
                        errors.append("转写角色尚未确认")
                    if trusted.get('role') == '医生' and (key != 'physical_exam' or re.search(r'吗|么|有没有|是否|[?？]', trusted.get('text', ''))):
                        errors.append("医生提问或非患者陈述不能写成患者事实")
                elif not matches:
                    errors.append("没有对应的真实音频片段")
                else:
                    errors.append("引用匹配多个音频片段，必须明确片段身份")
            context = segments[span.index] if span.index is not None and 0 <= span.index < len(segments) else "\n".join(matching)
            if re.search(r"(?:医生|医师|doctor)[\]】\s：:].*(?:吗|么|有没有|是否|[?？])", context, re.I):
                errors.append("医生提问不能作为患者事实")
            if re.search(r"忽略.{0,12}(?:规则|指令|提示)|(?:伪造|编造).{0,12}(?:病历|症状|诊断)|绕过.{0,12}(?:审核|审批)|ignore.{0,20}instructions", context, re.I):
                errors.append("转写中的操作指令不能作为患者事实")
            for token in ("父亲", "母亲", "家属", "孩子", "丈夫", "妻子", "昨天", "既往", "曾经", "以前", "已缓解", "已退热", "已停止", "已经脱敏", "不确定", "不知道"):
                if token in context and token not in field.value:
                    errors.append("引用截断了主体、时间、确定性或状态限定")
            for symptom in ("发热", "发烧", "咳嗽", "胸痛", "气促", "呼吸困难", "过敏", "高血压", "糖尿病"):
                if symptom in field.value and re.search(r"(?:否认|没有|无|未|不).{0,8}" + symptom, context) and not re.search(r"(?:否认|没有|无|未|不).{0,8}" + symptom, field.value):
                    errors.append("引用截断了否定状态")
        evidence = "\n".join(s.text for s in field.source_spans)
        if manual_doctor_edit:
            if errors:
                field.status = "conflicting"
                field.hint = "；".join(dict.fromkeys(errors))
            else:
                field.status = "partial"
                field.hint = "医生手工修改；原始转写证据仅供对照，需在当前Revision中明确审核。"
            continue
        # Require extractive clauses. Negation, subject, time, numbers and units
        # therefore survive unchanged; confidence cannot override this gate.
        clauses = [x for x in re.split(r"[，,。；;\n]+", field.value) if x.strip()]
        if not clauses or any(compact(x) not in compact(evidence) for x in clauses):
            errors.append("字段改写不能由引用逐项支持，需医生修正")
        for symptom in ("发热", "发烧", "咳嗽", "胸痛", "气促", "呼吸困难", "过敏", "高血压", "糖尿病"):
            if symptom in field.value and re.search(r"(?:否认|没有|无|未|不).{0,8}" + symptom, evidence) and not re.search(r"(?:否认|没有|无|未|不).{0,8}" + symptom, field.value):
                errors.append("否定状态与证据矛盾")
        for subject in ("父亲", "母亲", "家属", "孩子", "丈夫", "妻子"):
            if subject in evidence and subject not in field.value:
                errors.append("主体归属丢失，不能写成患者本人事实")
        for timing in ("昨天", "既往", "曾经", "以前", "已缓解", "已退热", "已停止", "已经脱敏"):
            if timing in evidence and timing not in field.value:
                errors.append("时间或状态限定丢失")
        for uncertainty in ("不确定", "不知道", "说不清", "可能", "疑似"):
            if uncertainty in evidence and uncertainty not in field.value:
                errors.append("确定性限定丢失")
        if errors:
            field.status = "conflicting"
            field.hint = "；".join(dict.fromkeys(errors))
        elif field.status == "conflicting":
            field.status = "complete"
            field.hint = None
    for diagnosis in fields.candidate_diagnoses:
        diagnosis.confirmed_by_doctor = False
        if not diagnosis.evidence or any(not s.text or compact(s.text) not in compact(source) for s in diagnosis.evidence):
            diagnosis.risk_warnings.append("证据冲突：候选缺少有效转写依据")
    return fields
