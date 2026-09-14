"""Production deterministic renderer and safety rules; no model fallback."""
from __future__ import annotations
import re
from app.schemas import MedicalField, MedicalRecordFields, SafetyCheckResult

def _field_text(field: MedicalField, *, physical_exam: bool = False) -> str:
    if field.missing:
        if physical_exam:
            return "待医生查体补充"
        return "未提及，待补充"
    if field.status == "partial" and field.value:
        missing = "、".join(field.missing_elements or ["待补充信息"])
        return f"{field.value}（部分完成，仍需补充：{missing}）"
    if field.status == "conflicting" and field.value:
        return f"{field.value}（证据冲突，需医生复核）"
    return field.value or "未提及，待补充"


def _items_text(items: list[str]) -> str:
    return "；".join(item.rstrip("。") for item in items if item).strip()


def render_draft(fields: MedicalRecordFields | dict) -> str:
    record = MedicalRecordFields.model_validate(fields)
    diagnosis_lines = []
    for diagnosis in record.candidate_diagnoses:
        evidence = "；".join(span.text for span in diagnosis.evidence[:3]) or "依据待医生核对"
        line_parts = [f"- {diagnosis.name}（{diagnosis.status}）依据：{evidence}"]
        if diagnosis.reason:
            line_parts.append(f"  触发原因：{diagnosis.reason}")
        suggested_checks = _items_text(diagnosis.suggested_checks)
        if suggested_checks:
            line_parts.append(f"  建议检查：{suggested_checks}")
        medication_notes = _items_text(diagnosis.medication_notes)
        if medication_notes:
            line_parts.append(f"  用药提示：{medication_notes}")
        risk_warnings = _items_text(diagnosis.risk_warnings)
        if risk_warnings:
            line_parts.append(f"  风险提醒：{risk_warnings}")
        follow_up_questions = _items_text(diagnosis.follow_up_questions)
        if follow_up_questions:
            line_parts.append(f"  建议补问：{follow_up_questions}")
        diagnosis_lines.append("\n".join(line_parts))

    candidate_text = "\n".join(diagnosis_lines) if diagnosis_lines else "未提及，待医生确认"

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


def check_draft_safety(
    draft_text: str,
    fields: MedicalRecordFields | dict,
    *,
    allow_export: bool = False,
) -> SafetyCheckResult:
    record = MedicalRecordFields.model_validate(fields)
    errors: list[str] = []
    warnings: list[str] = []

    for key in ("chief_complaint", "present_illness", "previous_treatment", "accompanying_symptoms", "past_history", "allergy_history", "physical_exam"):
        if getattr(record, key).status == "conflicting":
            errors.append(f"{key}存在证据冲突，必须先修正。")

    allergy_line = _line_for("过敏史：", draft_text)
    if record.allergy_history.missing and re.search(r"(无|否认)", allergy_line):
        errors.append("过敏史未提及时不得写成“无”或“否认”。")

    for diagnosis in record.candidate_diagnoses:
        for line in draft_text.splitlines():
            if line.startswith("- ") and diagnosis.name in line and diagnosis.status not in line:
                errors.append(f"候选诊断“{diagnosis.name}”未标记“候选/待医生确认”。")
                break

    if re.search(r"诊断为|确诊为|最终诊断", draft_text):
        errors.append("草稿存在把候选诊断写成最终诊断的风险。")

    fabricated_phrases = ["生命体征平稳", "查体无异常", "无明显异常"]
    if record.physical_exam.missing and any(phrase in draft_text for phrase in fabricated_phrases):
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
