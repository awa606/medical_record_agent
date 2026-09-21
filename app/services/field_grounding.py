"""Conservative extractive grounding, independent of model confidence."""
from __future__ import annotations

import re
from app.schemas import MedicalRecordFields
from app.services.clinical_facts import split_clinical_segments

FIELD_KEYS = ("chief_complaint", "present_illness", "previous_treatment", "accompanying_symptoms", "past_history", "allergy_history", "physical_exam")

def compact(text: str) -> str:
    return re.sub(r"[\s，,。；;、：:！？!?]", "", text).replace("发烧", "发热").replace("摄氏度", "℃")

def ground_fields(fields: MedicalRecordFields, source: str, trusted_segments: list[dict] | None = None) -> MedicalRecordFields:
    segments = split_clinical_segments(source)
    for key in FIELD_KEYS:
        field = getattr(fields, key)
        field.confirmed_by_doctor = False
        field.doctor_review_status = "pending"
        if not field.value:
            continue
        errors = []
        if field.missing:
            errors.append("非空字段不能标记为未提及")
        if not field.source_spans:
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
