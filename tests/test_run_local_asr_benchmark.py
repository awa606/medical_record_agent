import tempfile
import unittest
import csv
import wave
from pathlib import Path
from unittest.mock import patch

from app.services.asr.mock_engine import MockASREngine
from scripts.run_local_asr_benchmark import _audio_duration_seconds, benchmark_audio_files, run_local_asr_benchmark


class RunLocalASRBenchmarkTests(unittest.TestCase):
    def test_run_records_measured_and_skipped_engine(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_dir = root / "audio"
            truth_dir = root / "truth"
            reports_dir = root / "reports"
            audio_dir.mkdir()
            truth_dir.mkdir()
            (audio_dir / "fever_01.wav").write_bytes(b"fake wav bytes")
            (truth_dir / "fever_01.txt").write_text(
                "患者发热三天，咳嗽，铁锈色痰。",
                encoding="utf-8",
            )

            def fake_create_asr_engine(engine_name: str):
                if engine_name == "mock":
                    return MockASREngine()
                raise RuntimeError("missing qwen3 dependency")

            with patch(
                "scripts.run_local_asr_benchmark.create_asr_engine",
                side_effect=fake_create_asr_engine,
            ):
                summary = run_local_asr_benchmark(
                    engines=["mock", "qwen3"],
                    audio_dir=audio_dir,
                    truth_dir=truth_dir,
                    reports_dir=reports_dir,
                )

            by_engine = {item["engine"]: item for item in summary["engines"]}
            self.assertEqual(summary["schema_version"], "v0.5.6")
            self.assertEqual(summary["evaluation_profile"], "course_medical_cn")
            self.assertEqual(by_engine["mock"]["status"], "measured")
            self.assertEqual(by_engine["mock"]["rows"], 1)
            self.assertEqual(by_engine["qwen3"]["status"], "skipped")
            self.assertIn("missing qwen3 dependency", by_engine["qwen3"]["reason"])
            self.assertTrue((reports_dir / "mock_report.csv").exists())
            rows = list(csv.DictReader((reports_dir / "mock_report.csv").open("r", encoding="utf-8-sig")))
            self.assertEqual(rows[0]["status"], "measured")
            self.assertIn("realtime_factor", rows[0])
            self.assertIn("model_load_time", rows[0])
            self.assertIn("rss_peak_mb", rows[0])
            self.assertIn("cpu_process_percent", rows[0])
            self.assertIn("cpu_normalized_percent", rows[0])
            self.assertTrue((reports_dir / "local_asr_benchmark_run.json").exists())
            self.assertTrue((reports_dir / "local_asr_benchmark_run.md").exists())
            benchmark = (reports_dir / "local_model_benchmark.md").read_text(encoding="utf-8")
            self.assertIn("多引擎运行状态", benchmark)
            self.assertIn("qwen3", benchmark)

    def test_benchmark_audio_files_deduplicates_by_stem_and_prefers_wav(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_dir = Path(temp_dir)
            (audio_dir / "snakebite_01.mp3").write_bytes(b"mp3")
            (audio_dir / "snakebite_01.wav").write_bytes(b"wav")
            (audio_dir / "fever_01.wav").write_bytes(b"wav")
            (audio_dir / "ignored.txt").write_text("not audio", encoding="utf-8")

            files = benchmark_audio_files(audio_dir)

        self.assertEqual([path.name for path in files], ["fever_01.wav", "snakebite_01.wav"])

    def test_audio_duration_seconds_reads_standard_wav(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wav_path = Path(temp_dir) / "sample.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\x00\x00" * 16000)

            duration = _audio_duration_seconds(wav_path)

        self.assertEqual(duration, 1.0)

    def test_run_records_failed_sample_without_stopping_engine(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_dir = root / "audio"
            truth_dir = root / "truth"
            reports_dir = root / "reports"
            audio_dir.mkdir()
            truth_dir.mkdir()
            (audio_dir / "missing_truth.wav").write_bytes(b"fake wav bytes")

            with patch(
                "scripts.run_local_asr_benchmark.create_asr_engine",
                return_value=MockASREngine(),
            ):
                summary = run_local_asr_benchmark(
                    engines=["mock"],
                    audio_dir=audio_dir,
                    truth_dir=truth_dir,
                    reports_dir=reports_dir,
                )

            engine = summary["engines"][0]
            self.assertEqual(engine["status"], "failed")
            self.assertEqual(engine["rows"], 0)
            self.assertEqual(engine["failed_samples"], 1)
            rows = list(csv.DictReader((reports_dir / "mock_report.csv").open("r", encoding="utf-8-sig")))
            self.assertEqual(rows[0]["status"], "failed")
            self.assertIn("missing ground truth", rows[0]["error"])

    def test_smoke_mode_transcribes_without_ground_truth(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_dir = root / "audio"
            truth_dir = root / "truth"
            reports_dir = root / "reports"
            audio_dir.mkdir()
            truth_dir.mkdir()
            (audio_dir / "public_sample.wav").write_bytes(b"fake wav bytes")

            with patch(
                "scripts.run_local_asr_benchmark.create_asr_engine",
                return_value=MockASREngine(),
            ):
                summary = run_local_asr_benchmark(
                    engines=["mock"],
                    audio_dir=audio_dir,
                    truth_dir=truth_dir,
                    reports_dir=reports_dir,
                    mode="smoke",
                )

            engine = summary["engines"][0]
            self.assertEqual(summary["schema_version"], "v0.5.6")
            self.assertEqual(summary["mode"], "smoke")
            self.assertEqual(summary["evaluation_profile"], "course_medical_cn")
            self.assertEqual(engine["status"], "smoke_measured")
            self.assertEqual(engine["rows"], 1)
            rows = list(csv.DictReader((reports_dir / "mock_report.csv").open("r", encoding="utf-8-sig")))
            self.assertEqual(rows[0]["status"], "smoke_measured")
            self.assertEqual(rows[0]["ground_truth_available"], "False")
            self.assertEqual(rows[0]["transcript_non_empty"], "True")
            self.assertEqual(rows[0]["cer"], "")
            benchmark = (reports_dir / "local_model_benchmark.md").read_text(encoding="utf-8")
            self.assertIn("smoke", benchmark)


if __name__ == "__main__":
    unittest.main()
