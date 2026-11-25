"""Production deterministic renderer and safety rules; no model fallback."""
from __future__ import annotations
import re
from app.schemas import MedicalField, MedicalRecordFields, SafetyCheckResult

PATIENT_FIELD_KEYS = ("chief_complaint", "present_illness", "previous_treatment", "accompanying_symptoms", "past_history", "allergy_history", "physical_exam")


# These optional clinical sections have their own fields in the doctor's editor.
# Suggested treatment and patient registration details are outside the clinical draft.
OPTIONAL_CLINICAL_FIELDS = (
    ("personal_history", "个人史"),
    ("marital_history", "婚育史"),
    ("family_history", "家族史"),
    ("auxiliary_exam", "辅助检查"),
    ("treatment_notes", "医生处理意见"),
)


def supported_field_keys(fields: MedicalRecordFields) -> list[str]:
    """Count supported draft fields, never rejected nonempty model values."""
    return [key for key in PATIENT_FIELD_KEYS
            if not getattr(fields, key).missing
            and getattr(fields, key).status in {"complete", "partial"}
            and str(getattr(fields, key).value or "").strip()]


def _field_text(field: MedicalField, *, physical_exam: bool = False) -> str:
    if field.status == "conflicting":
        return "待核对（模型内容未采纳）"
    if field.missing:
        if physical_exam:
            return "待医生查体补充"
        return "未提及，待补充"
    if field.status == "partial" and field.value:
        missing = "、".join(field.missing_elements or ["待补充信息"])
        return f"{field.value}（部分完成，仍需补充：{missing}）"
    return field.value or "未提及，待补充"


def _optional_section(label: str, field: MedicalField) -> str:
    # Continuation lines stay inside the same clinical section.
    content = "\n  ".join(_field_text(field).splitlines())
    return f"{label}：{content}"


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

    optional_lines = []
    for key, label in OPTIONAL_CLINICAL_FIELDS:
        field = getattr(record, key)
        if field.status == "conflicting" or (not field.missing and str(field.value or "").strip()):
            optional_lines.append(_optional_section(label, field))

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
            *optional_lines,
            "候选诊断：",
            candidate_text,
        ]
    )


def _line_for(label: str, draft_text: str) -> str:
    for line in draft_text.splitlines():
        if line.startswith(label):
            return line
    return ""


_ALLERGY_DRUG_RULES = {
    "青霉素": ("青霉素", "阿莫西林", "氨苄西林", "哌拉西林", "苄青霉素"),
    "头孢": ("头孢",),
    "磺胺": ("磺胺",),
    "阿司匹林": ("阿司匹林", "拜阿司匹灵"),
}


def allergy_treatment_errors(record: MedicalRecordFields) -> list[str]:
    """Conservative text-level allergy/treatment conflict check.

    This is a safety prompt, not an allergy database or prescribing engine.
    """
    allergy_field = record.allergy_history
    if allergy_field.missing or not str(allergy_field.value or "").strip():
        return []
    allergy_text = str(allergy_field.value)
    treatment_text = " ".join(
        str(getattr(record, key).value or "")
        for key in ("treatment_notes", "treatment_plan")
        if getattr(record, key).value
    ).strip()
    if not treatment_text:
        return []
    treatment_clauses = re.split(r"[，,。；;]", treatment_text)
    safe_clauses = [clause for clause in treatment_clauses if not re.search(r"避免|禁用|忌用|不用", clause)]
    safe_treatment = " ".join(safe_clauses)
    errors: list[str] = []
    for allergen, drugs in _ALLERGY_DRUG_RULES.items():
        relevant = [
            clause
            for clause in re.split(r"[，,。；;]", allergy_text)
            if allergen in clause and not re.search(r"否认|无|阴性|不过敏", clause)
        ]
        if not relevant:
            continue
        hits = [drug for drug in drugs if drug in safe_treatment]
        if hits:
            errors.append(
                f"过敏史提示“{allergen}”过敏，处理意见含“{hits[0]}”；请核对并修改后再导出。"
            )
    return errors


def _contains_unsupported_exam(draft: str, auxiliary: MedicalField) -> bool:
    if "生命体征平稳" in draft or "查体无异常" in draft:
        return True
    if "无明显异常" not in draft:
        return False

    # Only a negative report recorded in its own structured section can account
    # for this otherwise ambiguous phrase. Free text elsewhere is still checked.
    section = _optional_section("辅助检查", auxiliary)
    physical_context = re.search(r"查体|体格|体征|体检(?!中心|机构|报告|资料)|听诊|触诊|叩诊|视诊", section)
    if auxiliary.status in {"complete", "partial"} and not physical_context:
        # Match complete lines exactly, including indented report continuations.
        # If the text occurs elsewhere as well, that occurrence stays visible to the check.
        bounded = "\n" + draft + "\n"
        return "无明显异常" in bounded.replace("\n" + section + "\n", "\n", 1)
    return True


def check_draft_safety(
    draft_text: str,
    fields: MedicalRecordFields | dict,
    *,
    allow_export: bool = False,
) -> SafetyCheckResult:
    record = MedicalRecordFields.model_validate(fields)
    errors: list[str] = []
    warnings: list[str] = []

    for key in PATIENT_FIELD_KEYS + tuple(key for key, _ in OPTIONAL_CLINICAL_FIELDS):
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

    if record.physical_exam.missing and _contains_unsupported_exam(draft_text, record.auxiliary_exam):
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

    errors.extend(allergy_treatment_errors(record))

    return SafetyCheckResult(
        passed=not errors,
        blocked=bool(errors),
        errors=errors,
        warnings=warnings,
    )
