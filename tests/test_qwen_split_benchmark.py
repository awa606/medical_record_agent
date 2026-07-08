import csv
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_local_asr_benchmark import CSV_FIELDS
from scripts.run_qwen_course_medical_split import run_split_benchmark


class QwenSplitBenchmarkTests(unittest.TestCase):
    def test_split_benchmark_merges_successful_sample_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_dir = root / "audio"
            truth_dir = root / "truth"
            reports_dir = root / "reports"
            audio_dir.mkdir()
            truth_dir.mkdir()
            (audio_dir / "snakebite_01.wav").write_bytes(b"fake wav")
            (truth_dir / "snakebite_01.txt").write_text("蛇咬伤 两个小时", encoding="utf-8")

            def fake_run(command, **kwargs):
                sample_report_dir = Path(command[command.index("--reports-dir") + 1])
                sample_report_dir.mkdir(parents=True, exist_ok=True)
                with (sample_report_dir / "qwen3_report.csv").open("w", encoding="utf-8-sig", newline="") as csv_file:
                    writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
                    writer.writeheader()
                    writer.writerow(
                        {
                            "filename": "snakebite_01.wav",
                            "engine": "qwen3-asr-0.6b",
                            "duration": "111.93",
                            "status": "measured",
                            "error": "",
                            "ground_truth_available": "True",
                            "transcript_non_empty": "True",
                            "segments": "1",
                            "model_load_time": "1.0",
                            "inference_time": "66.0",
                            "realtime_factor": "0.59",
                            "peak_memory_mb": "20.0",
                            "gpu_memory_mb": "",
                            "rss_start_mb": "6000.0",
                            "rss_peak_mb": "7000.0",
                            "rss_delta_mb": "1000.0",
                            "cpu_time_seconds": "120.0",
                            "cpu_process_percent": "181.8",
                            "cpu_normalized_percent": "22.7",
                            "cer": "0.144",
                            "keyword_recall": "0.6",
                            "recognized_keywords": "蛇咬伤",
                            "missing_keywords": "",
                        }
                    )
                return subprocess.CompletedProcess(command, 0, "ok", "")

            with patch("scripts.run_qwen_course_medical_split.subprocess.run", side_effect=fake_run):
                summary = run_split_benchmark(
                    sample_ids=["snakebite_01"],
                    audio_dir=audio_dir,
                    truth_dir=truth_dir,
                    reports_dir=reports_dir,
                    python_executable=Path("python"),
                )

            self.assertEqual(summary["schema_version"], "v0.5.7")
            self.assertEqual(summary["rows"], 1)
            self.assertEqual(summary["failed_samples"], 0)
            merged_rows = list(csv.DictReader((reports_dir / "qwen3_report.csv").open("r", encoding="utf-8-sig")))
            self.assertEqual(merged_rows[0]["status"], "measured")
            self.assertTrue((reports_dir / "samples" / "snakebite_01" / "snakebite_01_qwen3_sample.csv").exists())
            self.assertFalse((reports_dir / "samples" / "snakebite_01" / "qwen3_report.csv").exists())

    def test_split_benchmark_writes_failed_row_on_subprocess_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_dir = root / "audio"
            truth_dir = root / "truth"
            reports_dir = root / "reports"
            audio_dir.mkdir()
            truth_dir.mkdir()
            (audio_dir / "fever_01.wav").write_bytes(b"fake wav")
            (truth_dir / "fever_01.txt").write_text("发热 三天", encoding="utf-8")

            def fake_run(command, **kwargs):
                return subprocess.CompletedProcess(command, 1073807364, "", "process crashed")

            with patch("scripts.run_qwen_course_medical_split.subprocess.run", side_effect=fake_run):
                summary = run_split_benchmark(
                    sample_ids=["fever_01"],
                    audio_dir=audio_dir,
                    truth_dir=truth_dir,
                    reports_dir=reports_dir,
                    python_executable=Path("python"),
                )

            self.assertEqual(summary["rows"], 0)
            self.assertEqual(summary["failed_samples"], 1)
            merged_rows = list(csv.DictReader((reports_dir / "qwen3_report.csv").open("r", encoding="utf-8-sig")))
            self.assertEqual(merged_rows[0]["status"], "failed")
            self.assertIn("1073807364", merged_rows[0]["error"])
            self.assertTrue((reports_dir / "samples" / "fever_01" / "stderr.txt").exists())


if __name__ == "__main__":
    unittest.main()
