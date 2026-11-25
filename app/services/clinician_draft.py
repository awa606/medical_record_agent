from app.schemas import MedicalField, MedicalRecordFields
from app.schemas.clinician_draft import ClinicianDraftOrigin
from app.services.record_quality import build_record_quality_report
from app.services.record_rules import check_draft_safety, render_draft


def build_manual_first_result(values: dict[str, str], origin: ClinicianDraftOrigin) -> dict:
    fields = MedicalRecordFields(
        **{key: MedicalField(value=value, doctor_review_note="医生手录首稿") for key, value in values.items()}
    )
    draft, safety = render_manual_draft(fields, origin)
    return {
        "clinician_draft_origin": origin.model_dump(),
        "fields": fields.model_dump(),
        "draft": draft,
        "safety_check": safety.model_dump(),
        "quality_report": build_record_quality_report(fields, safety, draft=draft, clinician_authored=True),
    }


def render_manual_draft(fields: MedicalRecordFields, origin: ClinicianDraftOrigin):
    clinical_text = render_draft(fields)
    safety = check_draft_safety(clinical_text, fields)
    return clinical_text + "\n\n" + origin.display(), safety
