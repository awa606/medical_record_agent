import unittest

from app.schemas import (
    CandidateDiagnosis,
    MedicalField,
    MedicalRecordFields,
    SafetyCheckResult,
    SourceSpan,
    StepStatus,
    TaskStatus,
)


class MedicalRecordSchemaTests(unittest.TestCase):
    def test_missing_field_expression(self):
        field = MedicalField.missing_field()

        self.assertIsNone(field.value)
        self.assertTrue(field.missing)
        self.assertEqual(field.hint, "建议补问")
        self.assertEqual(field.source_spans, [])

    def test_medical_field_with_source_span(self):
        source = SourceSpan(
            index=1,
            text="左手手掌被咬了，大概两个小时左右。",
            start_time=0.0,
            end_time=5.5,
        )
        field = MedicalField(
            value="左手手掌被咬伤后肿痛约2小时",
            missing=False,
            hint=None,
            confidence=0.92,
            source_spans=[source],
        )

        self.assertEqual(field.value, "左手手掌被咬伤后肿痛约2小时")
        self.assertFalse(field.missing)
        self.assertEqual(field.confidence, 0.92)
        self.assertEqual(field.source_spans[0].text, source.text)

    def test_candidate_diagnosis_defaults(self):
        diagnosis = CandidateDiagnosis(
            name="毒蛇咬伤",
            evidence=[
                SourceSpan(text="左手手掌被咬了。"),
                SourceSpan(text="牙龈也有一些出血。"),
            ],
        )

        self.assertEqual(diagnosis.status, "候选/待医生确认")
        self.assertFalse(diagnosis.confirmed_by_doctor)
        self.assertEqual(len(diagnosis.evidence), 2)
        self.assertIsNone(diagnosis.reason)
        self.assertIsNone(diagnosis.rule_id)
        self.assertIsNone(diagnosis.confidence)
        self.assertEqual(diagnosis.suggested_checks, [])
        self.assertEqual(diagnosis.medication_notes, [])
        self.assertEqual(diagnosis.risk_warnings, [])
        self.assertEqual(diagnosis.follow_up_questions, [])

    def test_medical_record_fields_default_to_missing(self):
        record = MedicalRecordFields()

        self.assertTrue(record.past_history.missing)
        self.assertIsNone(record.past_history.value)
        self.assertEqual(record.past_history.hint, "建议补问")
        self.assertTrue(record.allergy_history.missing)
        self.assertEqual(record.candidate_diagnoses, [])

    def test_safety_check_result(self):
        result = SafetyCheckResult(
            passed=False,
            blocked=True,
            errors=["候选诊断未确认，禁止导出"],
            warnings=["过敏史未提及，建议补问"],
        )

        self.assertFalse(result.passed)
        self.assertTrue(result.blocked)
        self.assertEqual(result.errors[0], "候选诊断未确认，禁止导出")

    def test_task_and_step_status_enums(self):
        self.assertEqual(TaskStatus.CREATED.value, "CREATED")
        self.assertEqual(TaskStatus.WAITING_DOCTOR_REVIEW.value, "WAITING_DOCTOR_REVIEW")
        self.assertEqual(StepStatus.DEGRADED.value, "DEGRADED")


if __name__ == "__main__":
    unittest.main()
