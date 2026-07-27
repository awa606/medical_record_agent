from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.services.asr.funasr_reliability import classify_funasr_error, funasr_cache_status


class FunASRReliabilityTests(unittest.TestCase):
    def test_classifies_dns_and_model_failures(self):
        dns = classify_funasr_error("NameResolutionError: Failed to resolve modelscope.cn")
        missing = classify_funasr_error("model path does not exist: paraformer-zh")
        damaged = classify_funasr_error("ffmpeg audio decode failed: Invalid data found")

        self.assertEqual(dns["category"], "dns_failure")
        self.assertTrue(dns["retryable"])
        self.assertIn("模型缓存", dns["user_message"])
        self.assertEqual(missing["category"], "model_missing")
        self.assertEqual(damaged["category"], "audio_damaged")

    def test_cache_status_reports_configured_cache_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "modelscope" / "models").mkdir(parents=True)
            (root / "modelscope" / "models" / "marker.txt").write_text("ok", encoding="utf-8")
            original = {
                "MODELSCOPE_CACHE": os.environ.get("MODELSCOPE_CACHE"),
                "HF_HOME": os.environ.get("HF_HOME"),
                "TORCH_HOME": os.environ.get("TORCH_HOME"),
            }
            try:
                os.environ["MODELSCOPE_CACHE"] = str(root / "modelscope")
                os.environ["HF_HOME"] = str(root / "hf")
                os.environ["TORCH_HOME"] = str(root / "torch")

                status = funasr_cache_status()
            finally:
                for key, value in original.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertTrue(status["ok"])
        self.assertTrue(status["has_cached_files"])
        self.assertGreater(status["caches"]["modelscope"]["file_count"], 0)


if __name__ == "__main__":
    unittest.main()
