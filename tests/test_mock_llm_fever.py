import unittest

from app.services import MockLLM, mock_generate_draft


FEVER_01_CONVERSATION = """
[医生] 你这次主要哪里不舒服？
[患者] 发热3天了，3天前淋雨受凉后开始发烧。
[医生] 最高体温多少？有没有咳嗽咳痰？
[患者] 最高体温40℃，体温多在39到40℃，伴咳嗽、咳痰，曾有铁锈色痰。
[医生] 之前在哪里看过，用过什么药？
[患者] 当地卫生院考虑感冒，服用布洛芬后可以退热，但还是反复发热。
[医生] 食欲睡眠和大小便怎么样？既往有什么病史和过敏史？
[患者] 病程中食欲不佳，睡眠尚可，大小便正常。既往体健，否认肺结核、肝炎等传染病史，按计划预防接种，未发现食物或药品过敏史。
"""


class MockLLMFeverTests(unittest.TestCase):
    def test_extract_fields_supports_fever_case(self):
        fields = MockLLM().extract_fields(FEVER_01_CONVERSATION)

        self.assertFalse(fields.chief_complaint.missing)
        self.assertEqual(fields.chief_complaint.value, "发热3天")
        self.assertIn("最高体温40℃", fields.present_illness.value)
        self.assertEqual(fields.previous_treatment.value, "当地卫生院就诊，服用布洛芬")
        self.assertEqual(fields.accompanying_symptoms.value, "咳嗽、咳痰、铁锈色痰、食欲不佳")
        self.assertIn("既往体健", fields.past_history.value)
        self.assertEqual(fields.allergy_history.value, "未发现食物或药品过敏史")
        self.assertEqual(fields.physical_exam.value, "待医生查体补充")

        for field in [
            fields.chief_complaint,
            fields.present_illness,
            fields.previous_treatment,
            fields.accompanying_symptoms,
            fields.past_history,
            fields.allergy_history,
            fields.physical_exam,
        ]:
            self.assertGreater(len(field.source_spans), 0)

        diagnosis_names = [diagnosis.name for diagnosis in fields.candidate_diagnoses]
        self.assertEqual(diagnosis_names, ["发热待查", "肺部感染可能/肺炎待排"])
        for diagnosis in fields.candidate_diagnoses:
            self.assertIn("候选", diagnosis.status)
            self.assertFalse(diagnosis.confirmed_by_doctor)
            self.assertGreater(len(diagnosis.evidence), 0)

    def test_fever_case_generates_nonempty_draft_without_final_diagnosis(self):
        fields = MockLLM().extract_fields(FEVER_01_CONVERSATION)
        draft = mock_generate_draft(fields)

        self.assertIn("发热3天", draft)
        self.assertIn("肺部感染可能/肺炎待排", draft)
        self.assertIn("候选", draft)
        self.assertNotIn("最终诊断", draft)
        self.assertGreater(len(draft.strip()), 0)


if __name__ == "__main__":
    unittest.main()
