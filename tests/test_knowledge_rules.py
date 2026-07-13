import unittest

from app.services.knowledge_rules import infer_common_cold_candidates
from app.services.mock_llm import MockLLM, mock_generate_draft


class KnowledgeRuleTests(unittest.TestCase):
    def test_wind_cold_rule_outputs_explainable_candidate(self):
        conversation = "患者发热、怕冷明显、清涕、基本不出汗、全身酸痛。"

        candidates = infer_common_cold_candidates(conversation)

        self.assertGreaterEqual(len(candidates), 1)
        top = candidates[0]
        self.assertIn("感冒", top.name)
        self.assertIn("风寒束表证", top.name)
        self.assertEqual(top.rule_id, "R_WIND_COLD_001")
        self.assertIn("命中症状", top.reason)
        self.assertGreater(len(top.suggested_checks), 0)
        self.assertGreater(len(top.follow_up_questions), 0)
        self.assertIn("医生确认", "；".join(top.medication_notes))

    def test_wind_heat_rule_outputs_risk_warning(self):
        conversation = "患者发热比较明显、嗓子疼、鼻涕有点黄、有点咳，痰偏黄。"

        candidates = infer_common_cold_candidates(conversation)

        self.assertGreaterEqual(len(candidates), 1)
        top = candidates[0]
        self.assertIn("风热犯表证", top.name)
        self.assertEqual(top.rule_id, "R_WIND_HEAT_001")
        self.assertGreater(len(top.risk_warnings), 0)
        self.assertGreater(len(top.suggested_checks), 0)

    def test_mock_llm_uses_knowledge_rule_candidate_in_draft(self):
        conversation = "患者发热、怕冷明显、清涕、基本不出汗、全身酸痛。"

        fields = MockLLM().extract_fields(conversation)
        draft = mock_generate_draft(fields)

        self.assertIn("感冒（风寒束表证）", [diagnosis.name for diagnosis in fields.candidate_diagnoses])
        self.assertIn("建议检查", draft)
        self.assertIn("用药提示", draft)
        self.assertIn("风险提醒", draft)
        self.assertNotIn("最终诊断", draft)


if __name__ == "__main__":
    unittest.main()
