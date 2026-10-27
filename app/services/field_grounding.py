"""Conservative extractive grounding, independent of model confidence."""
from __future__ import annotations

import re
from typing import Any

from app.schemas import MedicalRecordFields, SourceSpan
from app.services.clinical_facts import (
    _FAMILY_WORDS, _RESPIRATORY_SYMPTOMS, clinical_experiencer, clinical_segment_contexts,
    extract_clinical_facts, split_clinical_segments,
)
from app.services.treatment_context import treatment_grounding_errors

FIELD_KEYS = ("chief_complaint", "present_illness", "previous_treatment", "accompanying_symptoms", "past_history", "allergy_history", "physical_exam")
_TIME_QUALIFIERS = ("昨天", "既往", "曾经", "以前", "已缓解", "已退热", "已停止", "已经脱敏")

def compact(text: str) -> str:
    return re.sub(r"[\s，,。；;、：:！？!?]", "", text).replace("发烧", "发热").replace("摄氏度", "℃")


def _explicitly_retracted_chief(value: str, matching_contexts: list,
                              *, symptom_aliases: tuple[str, ...] | None = None) -> bool:
    """Reject an old positive selected without its explicit same-patient denial.

    Only one patient sentence with a uniquely located selected clause qualifies.
    A correction must explicitly deny the same symptom after a prior "said"
    reference. Resolution, another symptom/person and later positive evidence
    cannot supply that relation. Original values and spans are never rewritten.
    """
    if len(matching_contexts) != 1:
        return False
    context = matching_contexts[0]
    if context.speaker != "患者" or context.question:
        return False
    # Do not infer a self-correction in a sentence mentioning another person;
    # the denied symptom can have a postposed subject ("没有发热的是他").
    if any(token in context.text for token in (*_FAMILY_WORDS, "家长", "他", "她")):
        return False
    # "Said earlier" dates the utterance, not the clinical event. If the
    # remaining sentence dates an occurrence/resolution, do not infer that a
    # denial at another time retracts it. Existing time/negation guards remain.
    clinical_context = re.sub(r"(?:刚才|刚刚|方才|前面|之前)(?:我)?说(?:过)?", "", context.text)
    if any(token in clinical_context for token in (
        *_TIME_QUALIFIERS, "昨晚", "前天", "今天", "现在", "目前", "早上", "上午",
        "中午", "下午", "晚上", "刚才", "刚刚", "退了", "退烧", "退热",
    )):
        return False
    clauses = [part.strip() for part in re.split(r"[，,。；;\n]+", value) if part.strip()]
    alias_groups = (symptom_aliases,) if symptom_aliases is not None else _RESPIRATORY_SYMPTOMS.values()
    for aliases in alias_groups:
        symptom = "(?:" + "|".join(re.escape(alias) for alias in aliases) + ")"
        # A retained negative/correction is not an unqualified positive claim.
        if re.search(r"(?:没有|没|无|未|否认)\s*" + symptom, value):
            continue
        mentions = list(re.finditer(
            r"(?:刚才|刚刚|方才|前面|之前)(?:我)?说(?:过)?[^，,；;。！？!?\n]{0,12}?" + symptom,
            context.text,
        ))
        corrections = list(re.finditer(
            r"(?:其实|实际上|实际|更正(?:一下)?|纠正(?:一下)?|我?说错了)"
            r"[，,；;：:\s]*(?:我|本人|患者)?(?:并)?(?:没有|没|无|未|否认)\s*" + symptom,
            context.text,
        ))
        for clause in clauses:
            locations = list(re.finditer(re.escape(clause), context.text))
            if len(locations) != 1:
                continue
            selected = locations[0]
            for occurrence in re.finditer(symptom, clause):
                position = selected.start() + occurrence.start()
                for mention in mentions:
                    if not mention.start() <= position < mention.end():
                        continue
                    if clinical_experiencer(context.text, speaker=context.speaker,
                            patient_target=context.patient_target, position=mention.end()) != "patient":
                        continue
                    if any(correction.start() >= mention.end()
                           and clinical_experiencer(context.text, speaker=context.speaker,
                               patient_target=context.patient_target,
                               position=correction.end()) == "patient"
                           for correction in corrections):
                        return True
    return False


def _doctor_negative_equivalent_clause(clause: str, field: Any, contexts: list) -> bool:
    """Support only a doctor's direct 没有/否认 interchange, never a new quote.

    The caller must have a server-validated source correction. One exact quoted
    negative clause in one explicit patient context must support the same known
    symptom. Do not infer negation across subjects, clinical times or unresolved
    positive evidence. This comparison cannot erase any other grounding error.
    """
    aliases = sorted({compact(alias) for values in _RESPIRATORY_SYMPTOMS.values()
                      for alias in values}, key=len, reverse=True)
    symptom_pattern = "(?:" + "|".join(re.escape(alias) for alias in aliases) + ")"
    negative_pattern = re.compile(
        r"^(?:(?:患者|病人|本人|我)[:：]?)?(?:没有|否认)(" + symptom_pattern + r")$"
    )
    target = negative_pattern.fullmatch(compact(clause))
    if not target:
        return False
    symptom = target.group(1)
    concept_aliases = next(values for values in _RESPIRATORY_SYMPTOMS.values()
                           if symptom in {compact(alias) for alias in values})
    same_concept = {compact(alias) for alias in concept_aliases}
    matched = {}
    for span in field.source_spans:
        for context in contexts:
            if span.index is not None and span.index != context.index:
                continue
            quote = compact(span.text)
            if not quote or compact(context.text).count(quote) != 1:
                continue
            parts = [part.strip() for part in re.split(r"[，,。；;\n]+", context.text) if part.strip()]
            for position, part in enumerate(parts):
                direct = re.sub(r"^\s*(?:[\[【](?:患者|病人)[\]】]\s*[:：]?|(?:患者|病人)\s*[:：])\s*", "", part)
                direct = re.sub(r"^(?:其实|实际上|实际)\s*", "", direct)
                negative = negative_pattern.fullmatch(compact(direct))
                if negative and negative.group(1) == symptom and compact(direct) in quote:
                    matched[(context.index, position)] = (context, parts)
    if len(matched) != 1:
        return False
    (index, selected), (context, parts) = next(iter(matched.items()))
    if (context.speaker != "患者" or context.question
            or any(word in context.text for word in (*_FAMILY_WORDS, "家长", "他", "她"))):
        return False
    clinical_context = re.sub(r"(?:刚才|刚刚|方才|前面|之前)(?:我)?说(?:过)?", "", context.text)
    if any(word in clinical_context for word in (
        *_TIME_QUALIFIERS, "昨晚", "前天", "今天", "现在", "目前", "之前", "刚才", "刚刚",
        "早上", "上午", "中午", "下午", "晚上", "可能", "疑似", "不确定", "不清楚", "不知道",
        "说不清", "建议", "计划", "如果", "是否", "有没有", "是不是", "吗", "么", "?", "？",
        "不是没有", "并非没有", "不能否认", "不否认", "未否认",
    )):
        return False
    # Another occurrence is not silently resolved by taking the last negative.
    for position, part in enumerate(parts):
        if position != selected and any(alias in compact(part) for alias in same_concept):
            if not _explicitly_retracted_chief(part, [context], symptom_aliases=concept_aliases):
                return False
    # Other patient statements containing the same symptom need a separate
    # scope decision. A doctor's unanswered question is not an assertion.
    if any(other.index != index and not other.question and any(alias in compact(other.text) for alias in same_concept)
           for other in contexts):
        return False
    return clinical_experiencer(context.text, speaker=context.speaker,
                               patient_target=context.patient_target) == "patient"


def _treatment_time_scope(value: str, context: str) -> str:
    """Scope time checks only when every selected clause is uniquely located.

    Keep full original clauses, including prefixes omitted by the model. A
    separate time-only prefix still qualifies the following clause. Ambiguous
    or non-extractive values retain the previous whole-context protection.
    Other subject, negation, modality and citation checks use the full source.
    """
    clauses = [part for part in re.split(r"[，,。；;\n]+", context) if part.strip()]
    selected = [compact(part) for part in re.split(r"[，,。；;\n]+", value) if compact(part)]
    if not selected:
        return context
    indexes: set[int] = set()
    for text in selected:
        matches = [index for index, clause in enumerate(clauses) if text in compact(clause)]
        if len(matches) != 1:
            return context
        index = matches[0]
        indexes.add(index)
        while index > 0:
            prefix = re.sub(
                r"^\s*(?:[\[【](?:患者|病人|医生|医师|家属|家长)[\]】]\s*[:：]?|(?:患者|病人|医生|医师|家属|家长)\s*[:：])\s*",
                "", clauses[index - 1],
            )
            if not re.fullmatch(r"(?:在)?(?:" + "|".join(_TIME_QUALIFIERS) + r")", compact(prefix)):
                break
            index -= 1
            indexes.add(index)
    return "\n".join(clauses[index] for index in sorted(indexes))


def _guardian_child_quote(span_text: str, matching_contexts: list) -> bool:
    """A cited child's statement may omit its subject in a patient field.

    Require one matching source sentence, an explicit child reference and
    patient ownership of every quoted clause. Other sentences cannot supply
    the subject, and questions never qualify. The evidence itself is unchanged.
    """
    if len(matching_contexts) != 1:
        return False
    context = matching_contexts[0]
    if (context.speaker not in {"家属", "家长"} or context.patient_target != "child"
            or context.question or not re.search(r"孩子|儿子|女儿", context.text)):
        return False
    clauses = [part.strip() for part in re.split(r"[，,。；;\n]+|但是|不过|然而|但", span_text) if part.strip()]
    return bool(clauses) and all(
        context.text.find(clause) >= 0
        and clinical_experiencer(context.text, speaker=context.speaker,
                             patient_target=context.patient_target,
                             position=context.text.find(clause) + len(clause)) == "patient"
        for clause in clauses
    )


def _selected_child_clauses(value: str, span_text: str, matching_contexts: list) -> list[str]:
    """Scope subject checks to explicitly selected child facts in a wide quote.

    The quote and original index remain unchanged. Every selected clause must
    name the child, occur verbatim in this one source sentence, and resolve to
    that child. An adjacent parent fact cannot supply the selected subject.
    All quote existence, role, negation and qualifier guards still run normally.
    """
    if len(matching_contexts) != 1:
        return []
    context = matching_contexts[0]
    if (context.speaker not in {"家属", "家长"} or context.patient_target != "child"
            or context.question):
        return []
    clauses = [part.strip() for part in re.split(r"[，,。；;\n]+", value) if part.strip()]
    for clause in clauses:
        position = context.text.find(clause)
        if (not re.search(r"孩子|儿子|女儿", clause) or clause not in span_text or position < 0
                or clinical_experiencer(context.text, speaker=context.speaker,
                    patient_target=context.patient_target, position=position + len(clause)) != "patient"):
            return []
    return clauses


def reconcile_extractive_fields(
    fields: MedicalRecordFields,
    trusted_segments: list[dict[str, Any]] | None,
    *,
    source: str,
) -> tuple[MedicalRecordFields, dict[str, dict[str, Any]]]:
    """Bind already supported extracts to reviewed audio segment identities.

    The language model is still responsible for selecting the fields and spans.
    Validate the original value and citations before binding identity/timing.
    Keep selected values, quote text and original sentence indices unchanged:
    expanding them to a whole audio segment mixes independent clinical fields.
    Invalid fields remain intact and conflicting for review. The normal
    grounding gate runs again against the resulting audio references.
    """

    if not trusted_segments:
        return fields, {}

    # Validate a copy: ground_fields may bind segment IDs. Preserve the model's
    # original values/spans on a rejected field, including its incorrect index.
    original_check = ground_fields(fields.model_copy(deep=True), source, trusted_segments)
    repairs: dict[str, dict[str, Any]] = {}
    for key in FIELD_KEYS:
        field = getattr(fields, key)
        checked = getattr(original_check, key)
        if checked.status == "conflicting":
            field.status = "conflicting"
            field.hint = checked.hint
            repairs[key] = {
                "strategy": "preserve_original_conflict",
                "original_value_changed": False,
                "original_validation_reason": checked.hint,
            }
            continue
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
            dedupe_key = (segment_id, span_text)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            canonical.append(
                SourceSpan(
                    text=span.text,
                    segment_id=segment_id,
                    index=span.index,
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
            "strategy": "bind_source_identity",
            "original_value_changed": False,
            "accepted_span_count": len(canonical),
            "rejected_span_count": len(rejected),
            "rejected_reasons": sorted(set(rejected)),
        }

    return fields, repairs

def ground_fields(fields: MedicalRecordFields, source: str, trusted_segments: list[dict] | None = None,
                  *, source_corrected_fields: set[str] | None = None) -> MedicalRecordFields:
    segments = split_clinical_segments(source)
    contexts = clinical_segment_contexts(source)
    for key in FIELD_KEYS:
        field = getattr(fields, key)
        field.confirmed_by_doctor = False
        field.doctor_review_status = "pending"
        manual_doctor_edit = str(field.doctor_review_note or "").startswith("manual_doctor_edit_v1:")
        if not field.value:
            continue
        errors = []
        guardian_child_quotes: set[str] = set()
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
            errors.extend(treatment_grounding_errors(field.value, context, previous_treatment=key == "previous_treatment"))
            matching_contexts = [c for c in contexts if span.text and compact(span.text) in compact(c.text)]
            if span.index is not None:
                matching_contexts = [c for c in matching_contexts if c.index == span.index]
            if key == "chief_complaint" and _explicitly_retracted_chief(field.value, matching_contexts):
                errors.append("原文已明确撤回该症状，不能作为当前阳性主诉")
            guardian_child_quote = _guardian_child_quote(span.text, matching_contexts)
            if guardian_child_quote:
                guardian_child_quotes.add(span.text)
            if any(c.question for c in matching_contexts):
                errors.append("未回答的提问不能作为患者事实")
            selected_child = _selected_child_clauses(field.value, span.text, matching_contexts)
            subject_clauses = selected_child or re.split(r"[，,。；;\n]+", span.text)
            for clause in subject_clauses:
                if clause.strip() and any(clinical_experiencer(c.text, speaker=c.speaker, patient_target=c.patient_target, position=c.text.find(clause) + len(clause)) in {"family", "other", "unknown"} for c in matching_contexts):
                    # No disease lookup: even an unfamiliar family condition is rejected.
                    errors.append("家属或他人事实不能归入患者本人字段，需医生核对归属")
            if re.search(r"(?:医生|医师|doctor)[\]】\s：:].*(?:吗|么|有没有|是否|[?？])", context, re.I):
                errors.append("医生提问不能作为患者事实")
            if re.search(r"忽略.{0,12}(?:规则|指令|提示)|(?:伪造|编造).{0,12}(?:病历|症状|诊断)|绕过.{0,12}(?:审核|审批)|ignore.{0,20}instructions", context, re.I):
                errors.append("转写中的操作指令不能作为患者事实")
            # A leading role label identifies the speaker, not the experiencer.
            # Exclude only that label from qualifier checks; never edit the
            # source/quote or relax trusted audio role checks above. First-person
            # and unspecified family statements remain ineligible patient facts.
            family_statement = re.fullmatch(
                r"\s*(?:(?:家属|家长)\s*[:：]|\[(?:家属|家长)\]\s*[:：]?|【(?:家属|家长)】\s*[:：]?)\s*(.+)",
                context, re.S,
            )
            if family_statement:
                context = family_statement.group(1)
                referent = re.match(r"(?:患者|病人|她|他)", context)
                if not guardian_child_quote and (not referent or referent.group(0) not in field.value):
                    errors.append("家属发言缺少明确且保留的患者主体，需医生核对归属")
                if re.search(r"吗|么|有没有|是否|[?？]", context):
                    errors.append("家属提问不能作为已确认的患者事实")
            time_context = _treatment_time_scope(field.value, context) if key == "previous_treatment" else context
            for token in ("父亲", "母亲", "家属", "孩子", "丈夫", "妻子", *_TIME_QUALIFIERS, "不确定", "不知道"):
                if token == "孩子" and guardian_child_quote:
                    continue
                qualifier_context = time_context if token in _TIME_QUALIFIERS else context
                if token in qualifier_context and token not in field.value:
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
        # These seven fields describe the patient. An accurately quoted family
        # fact still belongs to another person, even if the model kept “父亲”.
        # Retain it for review; do not silently move, rewrite or approve it.
        if any(fact.experiencer in {"family", "other"} for fact in extract_clinical_facts(field.value)) and not any(c.patient_target == "child" and c.speaker in {"家属", "家长"} for c in contexts):
            errors.append("家属或他人事实不能归入患者本人字段，需医生核对归属")
        clauses = [x for x in re.split(r"[，,。；;\n]+", field.value) if x.strip()]
        # A clause must be supported within one selected quote. Flattening all
        # quotes would manufacture statements such as "否认发热" from "否认"
        # in a chest-pain denial and "发热" in a separate positive statement.
        # Independent clauses may still cite different spans; keep the exact
        # selected text and identity for review rather than repairing a quote.
        unsupported = [clause for clause in clauses if not any(
            compact(clause) in compact(span.text) for span in field.source_spans
        )]
        doctor_negative_equivalence = bool(unsupported) and key in (source_corrected_fields or set()) and key in {
            "chief_complaint", "present_illness",
        } and all(_doctor_negative_equivalent_clause(clause, field, contexts) for clause in unsupported)
        if not clauses or (unsupported and not doctor_negative_equivalence):
            errors.append("字段改写不能由引用逐项支持，需医生修正")
        for symptom in ("发热", "发烧", "咳嗽", "胸痛", "气促", "呼吸困难", "过敏", "高血压", "糖尿病"):
            if symptom in field.value and re.search(r"(?:否认|没有|无|未|不).{0,8}" + symptom, evidence) and not re.search(r"(?:否认|没有|无|未|不).{0,8}" + symptom, field.value):
                errors.append("否定状态与证据矛盾")
        for subject in ("父亲", "母亲", "家属", "孩子", "丈夫", "妻子"):
            subject_required = any(subject in span.text and not (
                subject == "孩子" and span.text in guardian_child_quotes
            ) for span in field.source_spans)
            if subject_required and subject not in field.value:
                errors.append("主体归属丢失，不能写成患者本人事实")
        time_evidence = _treatment_time_scope(field.value, evidence) if key == "previous_treatment" else evidence
        for timing in _TIME_QUALIFIERS:
            if timing in time_evidence and timing not in field.value:
                errors.append("时间或状态限定丢失")
        for uncertainty in ("不确定", "不知道", "说不清", "可能", "疑似"):
            if uncertainty in evidence and uncertainty not in field.value:
                errors.append("确定性限定丢失")
        if errors:
            field.status = "conflicting"
            field.hint = "；".join(dict.fromkeys(errors))
        elif doctor_negative_equivalence:
            field.status = "partial"
            field.hint = "医生根据原文修正否定表述；仍须审核当前病历版本。"
        elif field.status == "conflicting":
            field.status = "complete"
            field.hint = None
    for diagnosis in fields.candidate_diagnoses:
        diagnosis.confirmed_by_doctor = False
        if not diagnosis.evidence or any(not s.text or compact(s.text) not in compact(source) for s in diagnosis.evidence):
            diagnosis.risk_warnings.append("证据冲突：候选缺少有效转写依据")
    return fields
