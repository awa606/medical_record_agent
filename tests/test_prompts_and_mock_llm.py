import unittest

from app.prompts import (
    build_extract_fields_prompt,
    build_generate_draft_prompt,
    build_safety_check_prompt,
)
from app.services import MockLLM, mock_extract_fields, mock_generate_draft, mock_safety_check


SNAKE_BITE_CONVERSATION = """
你好，哪里不好，你是哪里被咬了吗？我是左手手掌被咬了。现在什么感受？
感觉这里有点肿痛。大概被咬了多久了？大概咬了两个小时左右。
你被咬了后做没做过什么处理，用酒精冲洗了一下，有没有包扎伤口，
我这伤口这里绑了绷带，你有没有吃过什么药？吃的季德胜蛇药片。
现在除了咬伤部位不舒服，还有什么其他难受的？
我现在有一些胃寒，然后还有一些头晕胸闷，严重的时候还有心慌，
然后我感觉我的牙龈也有一些出血。
"""


class PromptAndMockLLMTests(unittest.TestCase):
    def test_prompt_builders_include_required_constraints(self):
        extract_prompt = build_extract_fields_prompt("医患对话")
        draft_prompt = build_generate_draft_prompt("{}")
        safety_prompt = build_safety_check_prompt("草稿", "{}")

        self.assertIn("输出必须是合法 JSON", extract_prompt)
        self.assertIn("missing", extract_prompt)
        self.assertIn("source_spans", extract_prompt)
        self.assertIn("不得补充新事实", draft_prompt)
        self.assertIn("候选/待医生确认", draft_prompt)
        self.assertIn("是否把过敏史未提及写成“无”", safety_prompt)

    def test_mock_extract_fields_creates_structured_record(self):
        fields = mock_extract_fields(SNAKE_BITE_CONVERSATION)

        self.assertEqual(fields.chief_complaint.value, "左手手掌被咬伤后肿痛约2小时")
        self.assertFalse(fields.chief_complaint.missing)
        self.assertTrue(fields.allergy_history.missing)
        self.assertIsNone(fields.allergy_history.value)
        self.assertEqual(fields.allergy_history.hint, "建议补问")
        self.assertTrue(fields.physical_exam.missing)
        self.assertEqual(fields.physical_exam.hint, "待医生查体补充")
        self.assertGreaterEqual(len(fields.chief_complaint.source_spans), 1)

    def test_mock_generate_draft_marks_candidate_diagnosis(self):
        fields = mock_extract_fields(SNAKE_BITE_CONVERSATION)
        draft = mock_generate_draft(fields)

        self.assertIn("过敏史：未提及/待补充", draft)
        self.assertIn("查体：待医生查体补充", draft)
        self.assertIn("毒蛇咬伤（候选/待医生确认）", draft)
        self.assertIn("建议检查", draft)
        self.assertIn("用药提示", draft)
        self.assertIn("风险提醒", draft)
        self.assertIn("医生确认", draft)
        self.assertIn("不生成处方", draft)
        self.assertNotIn("立即使用抗蛇毒血清", draft)

    def test_mock_safety_check_blocks_unsafe_export(self):
        fields = mock_extract_fields(SNAKE_BITE_CONVERSATION)
        draft = mock_generate_draft(fields)

        result = mock_safety_check(draft, fields)
        self.assertTrue(result.passed)
        self.assertFalse(result.blocked)

        export_result = mock_safety_check(draft, fields, allow_export=True)
        self.assertFalse(export_result.passed)
        self.assertTrue(export_result.blocked)
        self.assertIn("存在未确认候选诊断却允许导出的风险。", export_result.errors)

    def test_mock_llm_service_pipeline(self):
        service = MockLLM()
        fields = service.extract_fields(SNAKE_BITE_CONVERSATION)
        draft = service.generate_draft(fields)
        result = service.safety_check(draft, fields)

        self.assertTrue(result.passed)
        self.assertIn("门诊病历草稿", draft)


if __name__ == "__main__":
    unittest.main()
