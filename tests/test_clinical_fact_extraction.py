import os
import tempfile
import unittest

from app.agents import MedicalRecordOrchestrator
from app.services import MockLLM
from app.services.clinical_facts import extract_clinical_facts, has_extractable_clinical_fact
from app.services.record_quality import build_record_quality_report


class ClinicalFactExtractionTests(unittest.TestCase):
    def test_short_fever_keeps_known_facts_without_hallucinating_history(self):
        fields = MockLLM().extract_fields("我发烧39°C")

        self.assertEqual(fields.chief_complaint.status, "partial")
        self.assertEqual(fields.chief_complaint.value, "发热，体温39℃（持续时间待补问）")
        self.assertIn("持续时间", fields.chief_complaint.missing_elements)
        self.assertIn("患者自述发热", fields.present_illness.value)
        self.assertIn("体温约39℃", fields.present_illness.value)
        self.assertNotIn("3天前", fields.present_illness.value)
        self.assertNotIn("淋雨", fields.present_illness.value)
        self.assertNotIn("咳嗽", fields.present_illness.value)
        self.assertNotIn("布洛芬", fields.present_illness.value)
        self.assertTrue(fields.chief_complaint.source_spans)
        self.assertEqual(fields.candidate_diagnoses, [])

    def test_short_fever_and_headache_forms_partial_fields(self):
        fields = MockLLM().extract_fields("我感觉我发烧了，头很痛，39°C")

        self.assertEqual(fields.chief_complaint.status, "partial")
        self.assertEqual(fields.chief_complaint.value, "发热伴头痛（病程待补问）")
        self.assertIn("患者自述发热、头痛", fields.present_illness.value)
        self.assertEqual(fields.accompanying_symptoms.value, "头痛")
        self.assertEqual(fields.accompanying_symptoms.status, "partial")

    def test_duration_and_cough_are_preserved_as_partial_facts(self):
        fever = MockLLM().extract_fields("发热三天")
        cough = MockLLM().extract_fields("昨天开始咳嗽")

        self.assertEqual(fever.chief_complaint.value, "发热三天")
        self.assertEqual(fever.chief_complaint.status, "complete")
        self.assertIn("患者自述发热三天", fever.present_illness.value)
        self.assertIn("咳嗽", cough.chief_complaint.value)
        self.assertIn("昨天开始", cough.chief_complaint.value)

    def test_negative_and_resolved_fever_are_not_marked_positive(self):
        negative = MockLLM().extract_fields("我没有发烧，只是头痛")
        answered_no = MockLLM().extract_fields("医生：有没有发热？患者：没有")
        resolved = MockLLM().extract_fields("昨天发烧，今天已经退了")

        self.assertNotIn("发热伴", negative.chief_complaint.value)
        self.assertEqual(negative.chief_complaint.value, "头痛（病程待补问）")
        self.assertIn("患者否认发热", negative.present_illness.value)
        self.assertTrue(answered_no.chief_complaint.missing)
        self.assertEqual(answered_no.present_illness.status, "negative")
        self.assertIn("患者否认发热", answered_no.present_illness.value)
        self.assertIn("曾有发热", resolved.chief_complaint.value)
        self.assertIn("目前已缓解", resolved.present_illness.value)

    def test_treatment_fact_is_extracted_without_inventing_duration(self):
        fields = MockLLM().extract_fields("吃了布洛芬以后体温降下来了")

        self.assertEqual(fields.previous_treatment.value, "服用布洛芬后体温下降")
        self.assertIn("曾有发热", fields.chief_complaint.value)
        self.assertNotIn("发热3天", fields.chief_complaint.value)
        self.assertTrue(fields.previous_treatment.source_spans)

    def test_partial_fields_do_not_count_as_complete_quality(self):
        fields = MockLLM().extract_fields("我发烧39°C")
        report = build_record_quality_report(fields)

        self.assertIn("主诉", report["partial_fields"])
        self.assertIn("现病史", report["partial_fields"])
        self.assertEqual(report["core_completeness"], 0.0)
        self.assertFalse(report["ready_for_doctor_review"])

    def test_negative_fields_do_not_count_as_complete_quality(self):
        fields = MockLLM().extract_fields("医生：有没有发热？患者：没有")
        report = build_record_quality_report(fields)

        self.assertIn("现病史", report["negative_fields"])
        self.assertEqual(report["core_completeness"], 0.0)
        self.assertFalse(report["ready_for_doctor_review"])

    def test_has_extractable_clinical_fact_accepts_short_medical_text(self):
        self.assertTrue(has_extractable_clinical_fact("我发烧39°C"))
        facts = extract_clinical_facts("我发烧39°C")

        self.assertTrue(any(fact.name == "发热" for fact in facts))
        self.assertTrue(any(fact.name == "体温" and fact.value == "39℃" for fact in facts))


class ClinicalFactFormalGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(
            self.temp_dir.name,
            "records.sqlite3",
        )

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        self.temp_dir.cleanup()

    def test_formal_generation_uses_same_partial_extraction(self):
        result = MedicalRecordOrchestrator().run_from_text("我发烧39°C")

        fields = result["fields"]
        self.assertEqual(fields.chief_complaint.status, "partial")
        self.assertEqual(fields.chief_complaint.value, "发热，体温39℃（持续时间待补问）")
        self.assertIn("部分完成", result["draft"])
        self.assertEqual(result["quality_report"]["core_completeness"], 0.0)


if __name__ == "__main__":
    unittest.main()
