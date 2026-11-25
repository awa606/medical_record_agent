from app.schemas import CandidateDiagnosis, MedicalField, MedicalRecordFields
from app.services.clinical_codes import icd10_errors
from app.services.record_rules import allergy_treatment_errors


def test_icd10_format_is_validated_without_rejecting_unknown_codes():
    fields = MedicalRecordFields(
        candidate_diagnoses=[
            CandidateDiagnosis(name="上呼吸道感染", icd10_code="j06.9"),
            CandidateDiagnosis(name="不明原因发热", icd10_code="R50.9"),
        ]
    )
    assert icd10_errors(fields) == []

    invalid = MedicalRecordFields(
        candidate_diagnoses=[CandidateDiagnosis(name="测试", icd10_code="J6.9")]
    )
    errors = icd10_errors(invalid)
    assert errors and "格式无效" in errors[0]


def test_allergy_treatment_conflict_blocks_penicillin_cross_reaction():
    fields = MedicalRecordFields(
        allergy_history=MedicalField(value="青霉素过敏"),
        treatment_notes=MedicalField(value="口服阿莫西林 0.5g，每日三次。"),
    )
    errors = allergy_treatment_errors(fields)
    assert errors and "青霉素" in errors[0] and "阿莫西林" in errors[0]


def test_allergy_negation_and_explicit_avoidance_do_not_trigger():
    negated = MedicalRecordFields(
        allergy_history=MedicalField(value="否认青霉素过敏"),
        treatment_notes=MedicalField(value="阿莫西林 0.5g"),
    )
    assert allergy_treatment_errors(negated) == []

    avoided = MedicalRecordFields(
        allergy_history=MedicalField(value="青霉素过敏"),
        treatment_notes=MedicalField(value="避免使用青霉素类；改用阿奇霉素。"),
    )
    assert allergy_treatment_errors(avoided) == []
