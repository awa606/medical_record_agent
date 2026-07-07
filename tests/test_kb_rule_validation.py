import json
import unittest
from pathlib import Path

from scripts.validate_kb_rules import validate_rule_cases


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KB_DIR = PROJECT_ROOT / "data" / "output" / "kb"


class KnowledgeRuleValidationTests(unittest.TestCase):
    def test_rule_sources_are_review_limited(self):
        sources = json.loads((KB_DIR / "rule_sources.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(sources), 4)
        for source in sources:
            self.assertEqual(source["source_type"], "course_mock")
            self.assertEqual(source["review_status"], "needs_medical_review")
            self.assertIn("不作为真实临床诊断依据", source["clinical_use_limit"])

    def test_validation_cases_all_pass(self):
        report = validate_rule_cases(KB_DIR / "rule_validation_cases.json")

        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(report["summary"]["clinical_validity"], "not_claimed")
        self.assertGreaterEqual(report["summary"]["total"], 6)

    def test_validation_report_blocks_unsafe_terms(self):
        report = validate_rule_cases(KB_DIR / "rule_validation_cases.json")

        for result in report["results"]:
            self.assertEqual(result["unsafe_terms"], [])
            for candidate in result["candidates"]:
                self.assertEqual(candidate["status"], "候选/待医生确认")


if __name__ == "__main__":
    unittest.main()
