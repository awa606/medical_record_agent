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

    completed_core = len(CORE_FIELD_LABELS) - len(missing_core)
    core_completeness = round(completed_core / len(CORE_FIELD_LABELS), 2)
    evidence_total = len([key for key in ALL_FIELD_LABELS if not getattr(record, key).missing])
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
        },
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
        if field.missing or not field.value:
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
        if field.missing or not field.value:
            continue
        if not field.source_spans:
            missing.append(label)
    return missing


def _diagnosis_summary(record: MedicalRecordFields) -> dict[str, Any]:
    diagnoses = record.candidate_diagnoses
    return {
        "has_candidates": bool(diagnoses),
        "unconfirmed_count": len([item for item in diagnoses if not item.confirmed_by_doctor]),
        "confirmed_count": len([item for item in diagnoses if item.confirmed_by_doctor]),
        "max_confidence": max((item.confidence or 0.0 for item in diagnoses), default=None),
        "names": [item.name for item in diagnoses],
        "doctor_confirmation_required": bool(diagnoses),
    }


def _treatment_summary(record: MedicalRecordFields) -> dict[str, Any]:
    notes: list[str] = []
    for diagnosis in record.candidate_diagnoses:
        notes.extend(diagnosis.medication_notes)
    if not notes:
        notes = ["系统不自动生成处方，治疗和用药必须由医生确认。"]
    return {
        "requires_doctor_confirmation": True,
        "auto_prescription": False,
        "medication_notes": list(dict.fromkeys(notes)),
    }


def _next_actions(
    *,
    missing_core: list[str],
    low_confidence: list[dict[str, Any]],
    evidence_missing: list[str],
    diagnosis_summary: dict[str, Any],
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
    if safety and safety.errors:
        actions.append("处理安全校验错误后再进入审核。")
    if not actions:
        actions.append("核心字段和证据基本完整，可进入医生审核。")
    return actions
