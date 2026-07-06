import unittest

from app.services.asr import ASREvaluator


class ASREvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = ASREvaluator()

    def test_same_text_has_zero_cer(self):
        cer, reference_length, distance = self.evaluator.cer("左手肿痛两个小时", "左手肿痛两个小时")

        self.assertEqual(cer, 0)
        self.assertGreater(reference_length, 0)
        self.assertEqual(distance, 0)

    def test_one_wrong_character_has_nonzero_cer(self):
        cer, reference_length, distance = self.evaluator.cer("左手肿痛两个小时", "右手肿痛两个小时")

        self.assertGreater(cer, 0)
        self.assertEqual(distance, 1)
        self.assertGreater(reference_length, 0)

    def test_keyword_recall_is_one_when_all_keywords_hit(self):
        result = self.evaluator.keyword_metrics(
            ["蛇咬伤", "肿痛"],
            "患者左手蛇咬伤后肿痛。",
        )

        self.assertEqual(result["keyword_recall"], 1)
        self.assertEqual(result["missing"], [])

    def test_keyword_recall_reports_missing_keywords(self):
        result = self.evaluator.keyword_metrics(
            ["蛇咬伤", "胸闷"],
            "患者左手蛇咬伤后肿痛。",
        )

        self.assertLess(result["keyword_recall"], 1)
        self.assertEqual(result["missing"], ["胸闷"])

    def test_keyword_aliases_match_canonical_keywords(self):
        result = self.evaluator.keyword_metrics(
            [
                {"name": "40度", "aliases": ["40度", "四十度", "40摄氏度", "四十摄氏度"]},
                {"name": "食欲不佳", "aliases": ["食欲不佳", "胃口不是很好"]},
                {"name": "铁锈色痰", "aliases": ["铁锈色痰", "铁锈涩痰"]},
            ],
            "患者最高体温四十摄氏度，胃口不是很好，伴有铁锈涩痰。",
        )

        self.assertEqual(result["keyword_recall"], 1)
        self.assertEqual(result["recognized"], ["40度", "食欲不佳", "铁锈色痰"])
        self.assertEqual(result["missing"], [])

    def test_clean_ground_truth_text_removes_speaker_and_timestamp_lines(self):
        cleaned = self.evaluator.clean_ground_truth_text(
            """
发言人1
00:04 你好，哪里不舒服？
发言人2 00:07
发言人2 00:08 我发烧三天了。
01:23 还有铁锈色痰。
"""
        )

        self.assertEqual(
            cleaned,
            "你好，哪里不舒服？\n我发烧三天了。\n还有铁锈色痰。",
        )

    def test_cer_cleans_ground_truth_by_default(self):
        cer, reference_length, distance = self.evaluator.cer(
            "发言人2 00:04\n我发烧三天了。",
            "我发烧三天了。",
        )

        self.assertEqual(cer, 0)
        self.assertEqual(distance, 0)
        self.assertEqual(reference_length, len("我发烧三天了"))


if __name__ == "__main__":
    unittest.main()
