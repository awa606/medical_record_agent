from __future__ import annotations

from typing import Any

from app.schemas import MedicalRecordFields, SafetyCheckResult


CORE_FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "physical_exam": "查体",
}

ALL_FIELD_LABELS = {
    **CORE_FIELD_LABELS,
    "previous_treatment": "既往处理",
    "accompanying_symptoms": "伴随症状",
}

LOW_CONFIDENCE_THRESHOLD = 0.65
PLACEHOLDER_VALUES = {
    "待医生查体补充",
    "待医生查体补充舌象、脉象、咽部和肺部情况",
    "未提及",
    "未提及，待补充",
    "建议补问",
}


def build_record_quality_report(
    fields: MedicalRecordFields | dict[str, Any] | None,
    safety_check: SafetyCheckResult | dict[str, Any] | None = None,
    *,
    draft: str | None = None,
) -> dict[str, Any]:
    """Build an explainable quality report without creating or approving a record."""

    if fields is None:
        return _empty_report()

    record = MedicalRecordFields.model_validate(fields)
    safety = (
        SafetyCheckResult.model_validate(safety_check)
        if safety_check is not None
        else None
    )

    missing_core = _missing_fields(record, CORE_FIELD_LABELS)
    missing_all = _missing_fields(record, ALL_FIELD_LABELS)
    low_confidence = _low_confidence_fields(record)
    evidence_missing = _evidence_missing_fields(record)
    diagnosis_summary = _diagnosis_summary(record)
    treatment_summary = _treatment_summary(record)
    field_quality = _field_quality(record)

    completed_core = len(CORE_FIELD_LABELS) - len(missing_core)
    core_completeness = round(completed_core / len(CORE_FIELD_LABELS), 2)
    evidence_total = len([key for key in ALL_FIELD_LABELS if _has_real_field_value(getattr(record, key))])
    evidence_covered = evidence_total - len(evidence_missing)
    evidence_coverage = round(evidence_covered / evidence_total, 2) if evidence_total else 0.0

    blocked = bool(safety and (safety.blocked or not safety.passed))
    ready_for_doctor_review = not blocked and not missing_core
    export_allowed = False

    next_actions = _next_actions(
        missing_core=missing_core,
        low_confidence=low_confidence,
        evidence_missing=evidence_missing,
        diagnosis_summary=diagnosis_summary,
        treatment_summary=treatment_summary,
        safety=safety,
    )

    return {
        "status": "ready_for_review" if ready_for_doctor_review else "needs_review",
        "core_completeness": core_completeness,
        "core_fields_total": len(CORE_FIELD_LABELS),
        "core_fields_completed": completed_core,
        "missing_fields": missing_all,
        "missing_core_fields": missing_core,
        "low_confidence_fields": low_confidence,
        "evidence_coverage": evidence_coverage,
        "evidence_missing_fields": evidence_missing,
        "candidate_diagnosis_status": diagnosis_summary,
        "treatment_safety": treatment_summary,
        "field_quality": field_quality,
        "safety_blocked": blocked,
        "safety_errors": list(safety.errors) if safety else [],
        "safety_warnings": list(safety.warnings) if safety else [],
        "ready_for_doctor_review": ready_for_doctor_review,
        "export_allowed": export_allowed,
        "doctor_confirmation_required": True,
        "draft_character_count": len(draft or ""),
        "next_actions": next_actions,
    }


def _empty_report() -> dict[str, Any]:
    return {
        "status": "needs_review",
        "core_completeness": 0.0,
        "core_fields_total": len(CORE_FIELD_LABELS),
        "core_fields_completed": 0,
        "missing_fields": list(ALL_FIELD_LABELS.values()),
        "missing_core_fields": list(CORE_FIELD_LABELS.values()),
        "low_confidence_fields": [],
        "evidence_coverage": 0.0,
        "evidence_missing_fields": [],
        "candidate_diagnosis_status": {
            "has_candidates": False,
            "unconfirmed_count": 0,
            "confirmed_count": 0,
            "max_confidence": None,
        },
        "treatment_safety": {
            "requires_doctor_confirmation": True,
            "auto_prescription": False,
            "medication_notes": ["系统不自动生成处方，治疗和用药必须由医生确认。"],
            "suggested_checks": [],
            "risk_warnings": [],
            "follow_up_questions": [],
            "status": "needs_review",
            "quality_issues": ["建议检查", "风险提醒", "补问建议"],
        },
        "field_quality": [
            _field_quality_item(key, label, None)
            for key, label in ALL_FIELD_LABELS.items()
        ],
        "safety_blocked": False,
        "safety_errors": [],
        "safety_warnings": [],
        "ready_for_doctor_review": False,
        "export_allowed": False,
        "doctor_confirmation_required": True,
        "draft_character_count": 0,
        "next_actions": ["请先完成问诊转写或文本导入。"],
    }


def _missing_fields(record: MedicalRecordFields, labels: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for key, label in labels.items():
        field = getattr(record, key)
        if not _has_real_field_value(field):
            missing.append(label)
    return missing


def _low_confidence_fields(record: MedicalRecordFields) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key, label in ALL_FIELD_LABELS.items():
        field = getattr(record, key)
        if field.confidence is not None and field.confidence < LOW_CONFIDENCE_THRESHOLD:
            items.append(
                {
                    "key": key,
                    "label": label,
                    "confidence": field.confidence,
                    "hint": field.hint or "建议医生复核该字段。",
                }
            )
    return items


def _evidence_missing_fields(record: MedicalRecordFields) -> list[str]:
    missing: list[str] = []
    for key, label in ALL_FIELD_LABELS.items():
        field = getattr(record, key)
        if not _has_real_field_value(field):
            continue
        if not field.source_spans:
            missing.append(label)
    return missing


def _has_real_field_value(field: Any) -> bool:
    value = (field.value or "").strip() if field is not None else ""
    if not value:
        return False
    if field.missing:
        return False
    return value not in PLACEHOLDER_VALUES


def _field_quality(record: MedicalRecordFields) -> list[dict[str, Any]]:
    return [
        _field_quality_item(key, label, getattr(record, key))
        for key, label in ALL_FIELD_LABELS.items()
    ]


def _field_quality_item(key: str, label: str, field: Any | None) -> dict[str, Any]:
    if field is None or not _has_real_field_value(field):
        return {
            "key": key,
            "label": label,
            "status": "missing",
            "reason": f"{label}未形成有效内容。",
            "suggested_action": f"补问或人工填写{label}。",
            "evidence_count": 0,
        }

    evidence_count = len(field.source_spans)
    if evidence_count == 0:
        return {
            "key": key,
            "label": label,
            "status": "evidence_missing",
            "reason": f"{label}已有内容但缺少转写证据。",
            "suggested_action": f"补充{label}对应的原始转写证据。",
            "evidence_count": 0,
        }
    if field.confidence is not None and field.confidence < LOW_CONFIDENCE_THRESHOLD:
        return {
            "key": key,
            "label": label,
            "status": "low_confidence",
            "reason": f"{label}置信度低于 {LOW_CONFIDENCE_THRESHOLD:.2f}。",
            "suggested_action": f"医生复核{label}内容和证据。",
            "evidence_count": evidence_count,
        }
    if not field.confirmed_by_doctor:
        return {
            "key": key,
            "label": label,
            "status": "needs_doctor_review",
            "reason": f"{label}来自系统抽取，尚未医生确认。",
            "suggested_action": f"医生审核并确认{label}。",
            "evidence_count": evidence_count,
        }
    return {
        "key": key,
        "label": label,
        "status": "complete",
        "reason": f"{label}已有内容和证据。",
        "suggested_action": "无需额外处理。",
        "evidence_count": evidence_count,
    }


def _diagnosis_summary(record: MedicalRecordFields) -> dict[str, Any]:
    diagnoses = record.candidate_diagnoses
    quality_issues: list[dict[str, Any]] = []
    diagnosis_quality: list[dict[str, Any]] = []
    missing_total = 0
    for diagnosis in diagnoses:
        missing_items: list[str] = []
        if not diagnosis.evidence:
            missing_items.append("依据")
        if not diagnosis.suggested_checks:
            missing_items.append("建议检查")
        if not diagnosis.risk_warnings:
            missing_items.append("风险提醒")
        if not diagnosis.medication_notes:
            missing_items.append("用药边界")
        if not diagnosis.follow_up_questions:
            missing_items.append("补问建议")
        if diagnosis.status != "候选/待医生确认" or diagnosis.confirmed_by_doctor:
            missing_items.append("医生确认边界")
        missing_total += len(missing_items)
        diagnosis_quality.append(
            {
                "name": diagnosis.name,
                "status": "needs_review" if missing_items else "complete",
                "missing": missing_items,
                "has_evidence": bool(diagnosis.evidence),
                "has_suggested_checks": bool(diagnosis.suggested_checks),
                "has_risk_warnings": bool(diagnosis.risk_warnings),
                "has_medication_boundary": bool(diagnosis.medication_notes),
                "has_follow_up_questions": bool(diagnosis.follow_up_questions),
                "doctor_confirmation_required": (
                    diagnosis.status == "候选/待医生确认"
                    and not diagnosis.confirmed_by_doctor
                ),
                "suggested_action": (
                    f"补充{ '、'.join(missing_items) }。"
                    if missing_items
                    else "候选诊断信息完整，等待医生确认。"
                ),
            }
        )
        if missing_items:
            quality_issues.append({"name": diagnosis.name, "missing": missing_items})
    total_requirements = max(len(diagnoses) * 6, 1)
    quality_score = (
        round(max(0.0, 1 - missing_total / total_requirements), 2)
        if diagnoses
        else 0.0
    )
    return {
        "has_candidates": bool(diagnoses),
        "unconfirmed_count": len([item for item in diagnoses if not item.confirmed_by_doctor]),
        "confirmed_count": len([item for item in diagnoses if item.confirmed_by_doctor]),
        "max_confidence": max((item.confidence or 0.0 for item in diagnoses), default=None),
        "names": [item.name for item in diagnoses],
        "doctor_confirmation_required": bool(diagnoses),
        "quality_issues": quality_issues,
        "diagnosis_quality": diagnosis_quality,
        "quality_score": quality_score,
    }


def _treatment_summary(record: MedicalRecordFields) -> dict[str, Any]:
    if not record.candidate_diagnoses:
        return {
            "requires_doctor_confirmation": True,
            "auto_prescription": False,
            "medication_notes": ["系统不自动生成处方，治疗和用药必须由医生确认。"],
            "suggested_checks": [],
            "risk_warnings": [],
            "follow_up_questions": [],
            "has_suggested_checks": False,
            "has_risk_warnings": False,
            "has_follow_up_questions": False,
            "has_medication_boundary": True,
            "status": "not_applicable",
            "quality_issues": [],
            "next_actions": [],
        }
    suggested_checks: list[str] = []
    notes: list[str] = []
    risk_warnings: list[str] = []
    follow_up_questions: list[str] = []
    for diagnosis in record.candidate_diagnoses:
        suggested_checks.extend(diagnosis.suggested_checks)
        notes.extend(diagnosis.medication_notes)
        risk_warnings.extend(diagnosis.risk_warnings)
        follow_up_questions.extend(diagnosis.follow_up_questions)
    suggested_checks = _unique(suggested_checks)
    risk_warnings = _unique(risk_warnings)
    follow_up_questions = _unique(follow_up_questions)
    if not notes:
        notes = ["系统不自动生成处方，治疗和用药必须由医生确认。"]
    medication_notes = _unique(notes)
    has_medication_boundary = any(
        "医生确认" in note or "不自动" in note or "系统不" in note
        for note in medication_notes
    )
    quality_issues: list[str] = []
    if not suggested_checks:
        quality_issues.append("建议检查")
    if not risk_warnings:
        quality_issues.append("风险提醒")
    if not follow_up_questions:
        quality_issues.append("补问建议")
    if not has_medication_boundary:
        quality_issues.append("用药边界")
    return {
        "requires_doctor_confirmation": True,
        "auto_prescription": False,
        "medication_notes": medication_notes,
        "suggested_checks": suggested_checks,
        "risk_warnings": risk_warnings,
        "follow_up_questions": follow_up_questions,
        "has_suggested_checks": bool(suggested_checks),
        "has_risk_warnings": bool(risk_warnings),
        "has_follow_up_questions": bool(follow_up_questions),
        "has_medication_boundary": has_medication_boundary,
        "status": "needs_review" if quality_issues else "complete",
        "quality_issues": quality_issues,
        "next_actions": [
            f"补充治疗建议中的{item}。"
            for item in quality_issues
        ],
    }


def _next_actions(
    *,
    missing_core: list[str],
    low_confidence: list[dict[str, Any]],
    evidence_missing: list[str],
    diagnosis_summary: dict[str, Any],
    treatment_summary: dict[str, Any],
    safety: SafetyCheckResult | None,
) -> list[str]:
    actions: list[str] = []
    if missing_core:
        actions.append(f"补问核心字段：{'、'.join(missing_core)}。")
    if low_confidence:
        labels = "、".join(item["label"] for item in low_confidence[:4])
        actions.append(f"复核低置信度字段：{labels}。")
    if evidence_missing:
        actions.append(f"补充证据来源：{'、'.join(evidence_missing)}。")
    if diagnosis_summary["unconfirmed_count"]:
        actions.append("候选诊断仍需医生确认，不能作为最终诊断。")
    for issue in diagnosis_summary.get("quality_issues", []):
        missing_parts = "、".join(issue["missing"])
        actions.append(f"完善候选诊断“{issue['name']}”：{missing_parts}。")
    for item in treatment_summary.get("quality_issues", []):
        actions.append(f"完善治疗建议：{item}。")
    if safety and safety.errors:
        actions.append("处理安全校验错误后再进入审核。")
    if not actions:
        actions.append("核心字段和证据基本完整，可进入医生审核。")
    return actions


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))
