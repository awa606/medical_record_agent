import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_hardware_profile import collect_hardware_profile
from scripts.check_asr_dependencies import collect_asr_dependency_status, render_markdown
from scripts.check_qwen_asr_env import render_markdown as render_qwen_markdown
from scripts.prepare_public_asr_smoke_samples import render_markdown as render_public_samples_markdown
from scripts.run_local_asr_benchmark import CSV_FIELDS
from scripts.summarize_asr_benchmark import summarize_benchmark


class LocalModelBenchmarkScriptTests(unittest.TestCase):
    def test_collect_hardware_profile_has_required_sections(self):
        profile = collect_hardware_profile()

        self.assertEqual(profile["schema_version"], "v0.5.3")
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

        self.assertEqual(report["schema_version"], "v0.5.3")
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
                            "whisper": {"available": True, "version": "test"},
                            "ffmpeg": {"available": True, "version": "test", "source": "project_portable"},
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
                    fieldnames=CSV_FIELDS,
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "filename": "fever_01.wav",
                        "engine": "mock-asr-v0.2",
                        "duration": "25.0",
                        "status": "measured",
                        "error": "",
                        "ground_truth_available": "True",
                        "transcript_non_empty": "True",
                        "segments": "6",
                        "model_load_time": "0.01",
                        "inference_time": "0.2",
                        "realtime_factor": "0.008",
                        "peak_memory_mb": "1.5",
                        "gpu_memory_mb": "",
                        "rss_start_mb": "100.0",
                        "rss_peak_mb": "125.0",
                        "rss_delta_mb": "25.0",
                        "cpu_time_seconds": "0.1",
                        "cpu_process_percent": "50.0",
                        "cpu_normalized_percent": "6.25",
                        "cer": "0.5",
                        "keyword_recall": "0.25",
                        "recognized_keywords": "发热",
                        "missing_keywords": "咳嗽",
                    }
                )
            qwen_dir = reports_dir / "qwen3"
            qwen_dir.mkdir()
            (qwen_dir / "hardware_profile.json").write_text(
                json.dumps(
                    {
                        "python": {"implementation": "CPython", "version": "3.12"},
                        "gpu": {"torch_cuda_available": False},
                        "dependencies": {
                            "funasr": {"available": False},
                            "qwen_asr": {"available": True},
                            "whisper": {"available": False},
                        },
                        "benchmark_status": {"current_machine_role": "qwen_ascii_runtime"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with (qwen_dir / "qwen3_report.csv").open("w", encoding="utf-8-sig", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
                writer.writeheader()
                writer.writerow(
                    {
                        "filename": "snakebite_01.wav",
                        "engine": "qwen3-asr-0.6b",
                        "duration": "112.0",
                        "status": "measured",
                        "error": "",
                        "ground_truth_available": "True",
                        "transcript_non_empty": "True",
                        "segments": "1",
                        "model_load_time": "1.0",
                        "inference_time": "66.0",
                        "realtime_factor": "0.589",
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
                        "missing_keywords": "破伤风",
                    }
                )
            (reports_dir / "local_asr_benchmark_run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "v0.5.6",
                        "mode": "smoke",
                        "evaluation_profile": "mixed_public_smoke",
                        "evaluation_policy": "公开 smoke 混合集",
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
            self.assertEqual(summary["run_status"]["schema_version"], "v0.5.6")
            self.assertEqual(summary["engines"][0]["sample_count"], 1)
            self.assertEqual(summary["engines"][0]["failed_count"], 0)
            self.assertEqual(summary["engines"][0]["avg_realtime_factor"], 0.008)
            self.assertEqual(summary["engines"][0]["avg_cpu_process_percent"], 50.0)
            self.assertEqual(summary["engines"][0]["max_rss_peak_mb"], 125.0)
            self.assertIn("qwen3/qwen3_report.csv", summary["csv_reports"])
            self.assertEqual(summary["runtime_profiles"][0]["report_file"], "qwen3/hardware_profile.json")
            self.assertTrue(output_path.exists())
            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("本地模型与边缘端评测基线报告", markdown)
            self.assertIn("额外运行环境", markdown)
            self.assertIn("qwen3/hardware_profile.json", markdown)
            self.assertIn("多引擎运行状态", markdown)
            self.assertIn("评测分层", markdown)
            self.assertIn("平均 RTF", markdown)
            self.assertIn("CPU%", markdown)
            self.assertIn("RSS", markdown)
            self.assertIn("mock_report.csv", markdown)
            self.assertIn("qwen3/qwen3_report.csv", markdown)
            self.assertIn("whisper", markdown)
            self.assertIn("project_portable", markdown)

    def test_public_sample_manifest_markdown_marks_non_medical_boundary(self):
        markdown = render_public_samples_markdown(
            {
                "samples": [
                    {
                        "sample_id": "qwen_asr_en",
                        "language": "en",
                        "has_ground_truth": False,
                        "source": "Qwen3-ASR official repository sample",
                        "license": "smoke-test reference only",
                    }
                ]
            }
        )

        self.assertIn("中文优先公开 ASR 冒烟测试样本记录", markdown)
        self.assertIn("public_en_smoke", markdown)
        self.assertIn("不用于医学诊断", markdown)

    def test_qwen_env_markdown_records_recommendation(self):
        markdown = render_qwen_markdown(
            {
                "python": {
                    "implementation": "CPython",
                    "version": "3.11",
                    "executable_name": "python.exe",
                    "executable_path": "python.exe",
                    "prefix": ".venv-asr",
                    "recommended_for_qwen": "3.12",
                    "matches_recommended_version": False,
                    "inside_qwen_venv": False,
                    "path_contains_non_ascii": True,
                    "ascii_runtime_dir": "C:\\mra_qwen_runtime",
                },
                "modules": {
                    "nagisa": {"available": False, "error": "nagisa missing"},
                    "qwen_asr": {"available": False, "error": "qwen_asr missing"},
                },
                "model_init": {"status": "skipped", "message": "qwen_asr import failed"},
                "recommendation": "创建 `.venv-qwen-asr` Python 3.12 隔离环境。",
            }
        )

        self.assertIn("Qwen-ASR 环境检查报告", markdown)
        self.assertIn("Python 3.12", markdown)
        self.assertIn("路径是否含非 ASCII 字符", markdown)
        self.assertIn("C:\\mra_qwen_runtime", markdown)


if __name__ == "__main__":
    unittest.main()
