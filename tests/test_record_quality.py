import unittest

from app.schemas import CandidateDiagnosis, MedicalField, MedicalRecordFields, SafetyCheckResult, SourceSpan
from app.services.record_quality import build_record_quality_report


class RecordQualityTests(unittest.TestCase):
    def test_quality_report_marks_missing_and_evidence_gaps(self):
        fields = MedicalRecordFields(
            chief_complaint=MedicalField(
                value="发热3天",
                missing=False,
                confidence=0.9,
                source_spans=[SourceSpan(text="我发热三天。")],
            ),
            present_illness=MedicalField(
                value="反复发热伴咳嗽",
                missing=False,
                confidence=0.62,
                source_spans=[],
            ),
            candidate_diagnoses=[
                CandidateDiagnosis(
                    name="肺部感染可能/肺炎待排",
                    evidence=[SourceSpan(text="咳嗽和铁锈色痰")],
                    confidence=0.82,
                    medication_notes=["抗感染治疗需医生确认；系统不生成处方。"],
                )
            ],
        )
        safety = SafetyCheckResult(passed=True, blocked=False, warnings=["查体未提及。"])

        report = build_record_quality_report(fields, safety, draft="门诊病历草稿")

        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["core_fields_completed"], 2)
        self.assertIn("既往史", report["missing_core_fields"])
        self.assertEqual(report["low_confidence_fields"][0]["label"], "现病史")
        self.assertIn("现病史", report["evidence_missing_fields"])
        self.assertTrue(report["candidate_diagnosis_status"]["has_candidates"])
        self.assertFalse(report["export_allowed"])
        self.assertTrue(report["treatment_safety"]["requires_doctor_confirmation"])
        self.assertIn("查体未提及。", report["safety_warnings"])
        field_quality = {item["key"]: item for item in report["field_quality"]}
        self.assertEqual(field_quality["present_illness"]["status"], "evidence_missing")
        self.assertEqual(field_quality["physical_exam"]["status"], "missing")

    def test_quality_report_allows_review_but_never_auto_export(self):
        fields = MedicalRecordFields(
            chief_complaint=MedicalField(
                value="左手手掌被咬伤后肿痛约2小时",
                missing=False,
                confidence=0.9,
                source_spans=[SourceSpan(text="左手手掌被咬了两个小时。")],
            ),
            present_illness=MedicalField(
                value="伤后局部肿痛，自行酒精冲洗。",
                missing=False,
                confidence=0.84,
                source_spans=[SourceSpan(text="酒精冲洗了一下。")],
            ),
            past_history=MedicalField(
                value="既往体健",
                missing=False,
                confidence=0.7,
                source_spans=[SourceSpan(text="既往体健。")],
            ),
            allergy_history=MedicalField(
                value="未发现药物过敏史",
                missing=False,
                confidence=0.8,
                source_spans=[SourceSpan(text="没有药物过敏。")],
            ),
            physical_exam=MedicalField(
                value="T 36.8℃，P 96次/分，BP 128/78mmHg。左手手掌可见伤口，局部肿胀。",
                missing=False,
                confidence=0.82,
                source_spans=[SourceSpan(text="T 36.8℃，P 96次/分，BP 128/78mmHg。左手手掌可见伤口，局部肿胀。")],
            ),
        )

        report = build_record_quality_report(fields, SafetyCheckResult(passed=True))

        self.assertEqual(report["status"], "ready_for_review")
        self.assertTrue(report["ready_for_doctor_review"])
        self.assertFalse(report["export_allowed"])
        self.assertEqual(report["next_actions"], ["核心字段和证据基本完整，可进入医生审核。"])

    def test_placeholder_physical_exam_is_not_counted_as_complete(self):
        fields = MedicalRecordFields(
            chief_complaint=MedicalField(
                value="发热3天",
                missing=False,
                confidence=0.9,
                source_spans=[SourceSpan(text="我发热三天。")],
            ),
            present_illness=MedicalField(
                value="3天前受凉后发热。",
                missing=False,
                confidence=0.86,
                source_spans=[SourceSpan(text="3天前淋雨受凉后开始发热。")],
            ),
            past_history=MedicalField(
                value="既往体健",
                missing=False,
                confidence=0.82,
                source_spans=[SourceSpan(text="既往体健。")],
            ),
            allergy_history=MedicalField(
                value="未发现药物过敏史",
                missing=False,
                confidence=0.82,
                source_spans=[SourceSpan(text="没有药物过敏。")],
            ),
            physical_exam=MedicalField(
                value="待医生查体补充",
                missing=False,
                confidence=0.66,
                source_spans=[SourceSpan(text="待医生查体。")],
            ),
        )

        report = build_record_quality_report(fields, SafetyCheckResult(passed=True))

        self.assertIn("查体", report["missing_core_fields"])
        field_quality = {item["key"]: item for item in report["field_quality"]}
        self.assertEqual(field_quality["physical_exam"]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
