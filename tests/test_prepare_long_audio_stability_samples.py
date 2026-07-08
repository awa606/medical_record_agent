import unittest

from scripts.prepare_long_audio_stability_samples import build_sample_plan, parse_targets, render_manifest_markdown


class PrepareLongAudioStabilitySamplesTests(unittest.TestCase):
    def test_build_sample_plan_repeats_sources_and_pads_silence(self):
        sources = [
            {"sample_id": "fever_01", "duration_seconds": 310.0, "truth_text": "fever text"},
            {"sample_id": "chest_pain_01", "duration_seconds": 496.0, "truth_text": "chest text"},
            {"sample_id": "snakebite_01", "duration_seconds": 55.0, "truth_text": "snake text"},
        ]

        plan = build_sample_plan(sources, 960)

        self.assertEqual([segment["type"] for segment in plan[:-1]], ["source", "source", "source"])
        self.assertEqual(plan[-1]["type"], "silence")
        self.assertAlmostEqual(sum(float(segment["duration_seconds"]) for segment in plan), 960.0)
        self.assertEqual(plan[-1]["truth_text"], "")

    def test_parse_targets_accepts_cli_form(self):
        targets = parse_targets(["long_16min_course_cn=960", "long_30min_course_cn=1800"])

        self.assertEqual(targets["long_16min_course_cn"], 960)
        self.assertEqual(targets["long_30min_course_cn"], 1800)

    def test_render_manifest_marks_stability_boundary(self):
        markdown = render_manifest_markdown(
            {
                "generated_at": "2026-07-08T10:00:00+08:00",
                "source_audio_dir": "video",
                "source_truth_dir": "data/asr_eval/ground_truth",
                "sources": [
                    {
                        "sample_id": "fever_01",
                        "audio_file": "video/fever_01.wav",
                        "truth_file": "data/asr_eval/ground_truth/fever_01.txt",
                        "duration_seconds": 310.0,
                    }
                ],
                "samples": [
                    {
                        "sample_id": "long_16min_course_cn",
                        "target_seconds": 960,
                        "actual_seconds": 960.0,
                        "audio_file": "data/asr_eval/long_audio_stability/audio/long_16min_course_cn.wav",
                        "ground_truth_file": "data/asr_eval/long_audio_stability/ground_truth/long_16min_course_cn.txt",
                        "segments": [],
                    }
                ],
            }
        )

        self.assertIn("v0.5.8 长音频稳定性样本清单", markdown)
        self.assertIn("不代表中国门诊平均问诊时长", markdown)
        self.assertIn("long_16min_course_cn", markdown)


if __name__ == "__main__":
    unittest.main()
