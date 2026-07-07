import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_hardware_profile import collect_hardware_profile
from scripts.check_asr_dependencies import collect_asr_dependency_status, render_markdown
from scripts.summarize_asr_benchmark import summarize_benchmark


class LocalModelBenchmarkScriptTests(unittest.TestCase):
    def test_collect_hardware_profile_has_required_sections(self):
        profile = collect_hardware_profile()

        self.assertEqual(profile["schema_version"], "v0.5.0")
        self.assertIn("system", profile)
        self.assertIn("python", profile)
        self.assertIn("gpu", profile)
        self.assertIn("dependencies", profile)
        self.assertIn("cpu_logical_cores", profile["system"])
        self.assertIn("memory_total_gb", profile["system"])
        self.assertIn("funasr", profile["dependencies"])
        self.assertIn("qwen_asr", profile["dependencies"])
        self.assertIn("whisper", profile["dependencies"])
        self.assertIn("ffmpeg", profile["dependencies"])
        self.assertNotIn("hostname", json.dumps(profile, ensure_ascii=False).lower())

    def test_collect_asr_dependency_status_has_model_fields(self):
        report = collect_asr_dependency_status()

        self.assertEqual(report["schema_version"], "v0.5.2")
        self.assertIn("modules", report)
        self.assertIn("sensevoice", report["modules"])
        self.assertIn("whisper", report["modules"])
        self.assertIn("ffmpeg", report["modules"])
        self.assertIn("SENSEVOICE_MODEL_ID", report["environment"])
        markdown = render_markdown(report)
        self.assertIn("ASR 本地依赖检查报告", markdown)
        self.assertIn("whisper", markdown)

    def test_summarize_benchmark_reads_csv_and_hardware_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports_dir = Path(temp_dir)
            hardware_path = reports_dir / "hardware_profile.json"
            hardware_path.write_text(
                json.dumps(
                    {
                        "system": {
                            "os": "Windows",
                            "os_release": "11",
                            "cpu_logical_cores": 8,
                            "memory_total_gb": 16,
                        },
                        "python": {"implementation": "CPython", "version": "3.11"},
                        "gpu": {"torch_cuda_available": False, "cuda_device_count": 0},
                        "dependencies": {
                            "torch": {"available": True, "version": "test"},
                            "funasr": {"available": False, "version": None},
                            "qwen_asr": {"available": False, "version": None},
                            "ollama_cli": {"available": False},
                        },
                        "benchmark_status": {
                            "current_machine_role": "developer_baseline",
                            "hospital_pc_profile": "pending_collection",
                            "edge_device_profile": "pending_collection",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            csv_path = reports_dir / "mock_report.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
                        "filename",
                        "engine",
                        "duration",
                        "status",
                        "error",
                        "model_load_time",
                        "inference_time",
                        "realtime_factor",
                        "peak_memory_mb",
                        "gpu_memory_mb",
                        "cer",
                        "keyword_recall",
                        "recognized_keywords",
                        "missing_keywords",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "filename": "fever_01.wav",
                        "engine": "mock-asr-v0.2",
                        "duration": "25.0",
                        "status": "measured",
                        "error": "",
                        "model_load_time": "0.01",
                        "inference_time": "0.2",
                        "realtime_factor": "0.008",
                        "peak_memory_mb": "1.5",
                        "gpu_memory_mb": "",
                        "cer": "0.5",
                        "keyword_recall": "0.25",
                        "recognized_keywords": "发热",
                        "missing_keywords": "咳嗽",
                    }
                )
            (reports_dir / "local_asr_benchmark_run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "v0.5.2",
                        "sample_count": 1,
                        "engines": [
                            {
                                "engine": "mock",
                                "status": "measured",
                                "report_file": "mock_report.csv",
                                "rows": 1,
                                "failed_samples": 0,
                                "reason": "completed",
                            },
                            {
                                "engine": "whisper",
                                "status": "skipped",
                                "report_file": None,
                                "rows": 0,
                                "failed_samples": 0,
                                "reason": "missing dependency",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output_path = reports_dir / "local_model_benchmark.md"
            summary = summarize_benchmark(reports_dir, output_path)

            self.assertEqual(summary["engines"][0]["engine"], "mock-asr-v0.2")
            self.assertEqual(summary["run_status"]["schema_version"], "v0.5.2")
            self.assertEqual(summary["engines"][0]["sample_count"], 1)
            self.assertEqual(summary["engines"][0]["failed_count"], 0)
            self.assertEqual(summary["engines"][0]["avg_realtime_factor"], 0.008)
            self.assertTrue(output_path.exists())
            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("本地模型与边缘端评测基线报告", markdown)
            self.assertIn("多引擎运行状态", markdown)
            self.assertIn("平均 RTF", markdown)
            self.assertIn("mock_report.csv", markdown)
            self.assertIn("whisper", markdown)


if __name__ == "__main__":
    unittest.main()
