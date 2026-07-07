import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.asr.mock_engine import MockASREngine
from scripts.run_local_asr_benchmark import run_local_asr_benchmark


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
            self.assertEqual(summary["schema_version"], "v0.5.1")
            self.assertEqual(by_engine["mock"]["status"], "measured")
            self.assertEqual(by_engine["mock"]["rows"], 1)
            self.assertEqual(by_engine["qwen3"]["status"], "skipped")
            self.assertIn("missing qwen3 dependency", by_engine["qwen3"]["reason"])
            self.assertTrue((reports_dir / "mock_report.csv").exists())
            self.assertTrue((reports_dir / "local_asr_benchmark_run.json").exists())
            self.assertTrue((reports_dir / "local_asr_benchmark_run.md").exists())
            benchmark = (reports_dir / "local_model_benchmark.md").read_text(encoding="utf-8")
            self.assertIn("多引擎运行状态", benchmark)
            self.assertIn("qwen3", benchmark)


if __name__ == "__main__":
    unittest.main()
