from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_diarization_results import render_markdown, summarize_results


class SummarizeDiarizationResultsTests(unittest.TestCase):
    def test_summary_marks_two_speaker_results_and_pending_three_speaker_sample(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports_dir = root / "reports"
            reports_dir.mkdir()
            (reports_dir / "fever_01_funasr_campp.json").write_text(
                json.dumps(
                    {
                        "engine": "funasr_campp",
                        "status": "measured",
                        "speaker_count_error": 0,
                        "boundary_f1": 0.8,
                        "mixed_utterance_rate": 0.1,
                        "role_consistency": 0.9,
                        "der": None,
                        "jer": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (reports_dir / "fever_01_funasr_campp_asr_result.json").write_text(
                json.dumps({"segments": [{"text": "ignored raw ASR payload"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            deps = root / "dependency_status.json"
            deps.write_text(
                json.dumps(
                    {
                        "engines": {
                            "pyannote": {"status": "skipped", "reason": "missing token"},
                            "three_d_speaker": {"status": "skipped", "reason": "not configured"},
                            "funasr_campp": {"status": "measured_in_docker", "reason": "baseline"},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            summary = summarize_results(reports_dir, deps)
            markdown = render_markdown(summary)

        self.assertEqual(summary["annotated_samples"], ["fever_01"])
        self.assertEqual(summary["measured_result_count"], 1)
        self.assertEqual([item["report_file"] for item in summary["results"]], ["fever_01_funasr_campp.json"])
        self.assertEqual(summary["der_jer_status"], "not_available")
        self.assertEqual(summary["pending_samples"][0]["status"], "pending_sample")
        self.assertIn("three_speaker_course_sample", markdown)
        self.assertIn("不能把本轮结果扩展解释为三说话人成绩", markdown)


if __name__ == "__main__":
    unittest.main()
