from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.services.asr.funasr_reliability import classify_funasr_error, funasr_cache_status


class FunASRReliabilityTests(unittest.TestCase):
    def test_classifies_dns_model_config_and_audio_failures(self):
        dns = classify_funasr_error("NameResolutionError: Failed to resolve modelscope.cn")
        mismatch = classify_funasr_error("model 'paraformer-zh-streaming' is not registered. Registered model keys")
        missing = classify_funasr_error("model path does not exist: paraformer-zh")
        damaged = classify_funasr_error("ffmpeg audio decode failed: Invalid data found")

        self.assertEqual(dns["category"], "dns_failure")
        self.assertTrue(dns["retryable"])
        self.assertIn("模型缓存", dns["user_message"])
        self.assertEqual(mismatch["category"], "model_config_mismatch")
        self.assertIn("模型配置", mismatch["user_message"])
        self.assertEqual(missing["category"], "model_missing")
        self.assertEqual(damaged["category"], "audio_damaged")

    def test_cache_status_reports_configured_cache_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "modelscope" / "models").mkdir(parents=True)
            (root / "modelscope" / "models" / "marker.txt").write_text("ok", encoding="utf-8")
            original = _capture_cache_env()
            try:
                os.environ["MODELSCOPE_CACHE"] = str(root / "modelscope")
                os.environ["HF_HOME"] = str(root / "hf")
                os.environ["TORCH_HOME"] = str(root / "torch")
                os.environ["MEDICAL_RECORD_AGENT_FUNASR_CACHE_MIN_FILES"] = "1"

                status = funasr_cache_status()
            finally:
                _restore_env(original)

        self.assertTrue(status["ok"])
        self.assertTrue(status["has_cached_files"])
        self.assertTrue(status["has_required_cache"])
        self.assertGreater(status["caches"]["modelscope"]["file_count"], 0)

    def test_cache_status_rejects_nearly_empty_model_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "modelscope" / "models").mkdir(parents=True)
            (root / "modelscope" / "models" / "partial.marker").write_text("partial", encoding="utf-8")
            original = _capture_cache_env()
            try:
                os.environ["MODELSCOPE_CACHE"] = str(root / "modelscope")
                os.environ["HF_HOME"] = str(root / "hf")
                os.environ["TORCH_HOME"] = str(root / "torch")
                os.environ["MEDICAL_RECORD_AGENT_FUNASR_CACHE_MIN_FILES"] = "5"

                status = funasr_cache_status()
            finally:
                _restore_env(original)

        self.assertTrue(status["has_cached_files"])
        self.assertFalse(status["has_required_cache"])
        self.assertEqual(status["total_file_count"], 1)


def _capture_cache_env() -> dict[str, str | None]:
    return {
        "MODELSCOPE_CACHE": os.environ.get("MODELSCOPE_CACHE"),
        "HF_HOME": os.environ.get("HF_HOME"),
        "TORCH_HOME": os.environ.get("TORCH_HOME"),
        "MEDICAL_RECORD_AGENT_FUNASR_CACHE_MIN_FILES": os.environ.get("MEDICAL_RECORD_AGENT_FUNASR_CACHE_MIN_FILES"),
    }


def _restore_env(values: dict[str, str | None]) -> None:
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
