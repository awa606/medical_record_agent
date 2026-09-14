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
        self.assertEqual(report["core_fields_completed"], 1)
        self.assertIn("既往史", report["missing_core_fields"])
        self.assertEqual(report["low_confidence_fields"][0]["label"], "现病史")
        self.assertIn("现病史", report["evidence_missing_fields"])
        self.assertTrue(report["candidate_diagnosis_status"]["has_candidates"])
        diagnosis_quality = report["candidate_diagnosis_status"]["diagnosis_quality"][0]
        self.assertEqual(diagnosis_quality["status"], "needs_review")
        self.assertIn("建议检查", diagnosis_quality["missing"])
        self.assertIn("风险提醒", diagnosis_quality["missing"])
        self.assertIn("补问建议", diagnosis_quality["missing"])
        self.assertFalse(report["export_allowed"])
        self.assertTrue(report["treatment_safety"]["requires_doctor_confirmation"])
        self.assertEqual(report["treatment_safety"]["status"], "needs_review")
        self.assertIn("建议检查", report["treatment_safety"]["quality_issues"])
        self.assertIn("风险提醒", report["treatment_safety"]["quality_issues"])
        self.assertIn("补问建议", report["treatment_safety"]["quality_issues"])
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

    def test_complete_candidate_diagnosis_builds_treatment_quality(self):
        fields = MedicalRecordFields(
            chief_complaint=MedicalField(
                value="左手蛇咬伤后肿痛2小时",
                missing=False,
                confidence=0.91,
                source_spans=[SourceSpan(text="左手被蛇咬了两个小时。")],
            ),
            present_illness=MedicalField(
                value="咬伤后局部肿痛，伴头晕、牙龈出血，自行酒精冲洗。",
                missing=False,
                confidence=0.86,
                source_spans=[SourceSpan(text="现在肿得厉害，还有头晕、牙龈出血。")],
            ),
            past_history=MedicalField(
                value="既往体健",
                missing=False,
                confidence=0.78,
                source_spans=[SourceSpan(text="之前身体都挺好的。")],
            ),
            allergy_history=MedicalField(
                value="否认药物过敏史",
                missing=False,
                confidence=0.78,
                source_spans=[SourceSpan(text="没有药物过敏。")],
            ),
            physical_exam=MedicalField(
                value="左手局部肿胀，需进一步查凝血功能和生命体征。",
                missing=False,
                confidence=0.74,
                source_spans=[SourceSpan(text="左手肿胀，后续要查凝血。")],
            ),
            candidate_diagnoses=[
                CandidateDiagnosis(
                    name="毒蛇咬伤（候选）",
                    status="候选/待医生确认",
                    evidence=[SourceSpan(text="蛇咬伤后肿痛，伴头晕、牙龈出血。")],
                    confidence=0.88,
                    reason="蛇咬伤后出现局部肿痛和出血倾向，需要警惕毒蛇咬伤。",
                    suggested_checks=["凝血功能", "血常规", "肝肾功能", "心电监测"],
                    medication_notes=["抗蛇毒血清、镇痛和抗感染治疗均需医生确认；系统不自动处方。"],
                    risk_warnings=["牙龈出血提示凝血异常风险，需密切观察。"],
                    follow_up_questions=["蛇的颜色和体型？", "是否出现胸闷、呼吸困难或意识改变？"],
                )
            ],
        )

        report = build_record_quality_report(fields, SafetyCheckResult(passed=True))

        diagnosis_quality = report["candidate_diagnosis_status"]["diagnosis_quality"][0]
        self.assertEqual(diagnosis_quality["status"], "complete")
        self.assertEqual(diagnosis_quality["missing"], [])
        self.assertEqual(report["treatment_safety"]["status"], "complete")
        self.assertFalse(report["treatment_safety"]["auto_prescription"])
        self.assertIn("凝血功能", report["treatment_safety"]["suggested_checks"])
        self.assertIn("牙龈出血提示凝血异常风险，需密切观察。", report["treatment_safety"]["risk_warnings"])
        self.assertIn("蛇的颜色和体型？", report["treatment_safety"]["follow_up_questions"])
        self.assertNotIn("完善治疗建议", " ".join(report["next_actions"]))

    def test_quality_report_without_candidate_diagnosis_marks_treatment_not_applicable(self):
        fields = MedicalRecordFields(
            chief_complaint=MedicalField(
                value="发热3天",
                missing=False,
                confidence=0.91,
                source_spans=[SourceSpan(text="我发热3天。")],
            ),
            present_illness=MedicalField(
                value="伴咳嗽、乏力。",
                missing=False,
                confidence=0.82,
                source_spans=[SourceSpan(text="还咳嗽，感觉没劲。")],
            ),
            past_history=MedicalField(
                value="既往体健",
                missing=False,
                confidence=0.8,
                source_spans=[SourceSpan(text="之前身体挺好。")],
            ),
            allergy_history=MedicalField(
                value="否认药物过敏史",
                missing=False,
                confidence=0.8,
                source_spans=[SourceSpan(text="没有药物过敏。")],
            ),
            physical_exam=MedicalField(
                value="咽部充血，双肺呼吸音粗。",
                missing=False,
                confidence=0.75,
                source_spans=[SourceSpan(text="查体见咽部充血，双肺呼吸音粗。")],
            ),
            candidate_diagnoses=[],
        )

        report = build_record_quality_report(fields, SafetyCheckResult(passed=True))

        self.assertFalse(report["candidate_diagnosis_status"]["has_candidates"])
        self.assertEqual(report["candidate_diagnosis_status"]["quality_score"], 0.0)
        self.assertEqual(report["treatment_safety"]["status"], "not_applicable")
        self.assertEqual(report["treatment_safety"]["quality_issues"], [])
        self.assertEqual(report["treatment_safety"]["next_actions"], [])
        self.assertTrue(report["ready_for_doctor_review"])
        self.assertEqual(report["next_actions"], ["核心字段和证据基本完整，可进入医生审核。"])

    def test_quality_report_orders_next_actions_with_safety_last(self):
        fields = MedicalRecordFields(
            chief_complaint=MedicalField(
                value="发热3天",
                missing=False,
                confidence=0.91,
                source_spans=[SourceSpan(text="我发热3天。")],
            ),
            present_illness=MedicalField(
                value="反复发热伴咳嗽",
                missing=False,
                confidence=0.61,
                source_spans=[],
            ),
            candidate_diagnoses=[
                CandidateDiagnosis(
                    name="肺部感染可能/肺炎待排",
                    status="候选/待医生确认",
                    evidence=[],
                    confidence=0.82,
                    medication_notes=[],
                    suggested_checks=[],
                    risk_warnings=[],
                    follow_up_questions=[],
                )
            ],
        )
        safety = SafetyCheckResult(
            passed=False,
            blocked=True,
            errors=["存在未确认候选诊断却允许导出的风险。"],
        )

        report = build_record_quality_report(fields, safety)

        self.assertGreaterEqual(len(report["next_actions"]), 5)
        self.assertEqual(report["next_actions"][0], "补问核心字段：既往史、过敏史、查体。")
        self.assertEqual(report["next_actions"][1], "复核低置信度字段：现病史。")
        self.assertEqual(report["next_actions"][2], "补充证据来源：现病史。")
        self.assertIn("完善候选诊断", report["next_actions"][4])
        self.assertEqual(report["next_actions"][-1], "处理安全校验错误后再进入审核。")


if __name__ == "__main__":
    unittest.main()
