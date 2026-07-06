import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.db import create_task, create_task_step, finish_task_step, json_dumps, update_task
from scripts.save_run_log import save_run_log


class SaveRunLogTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.upload_dir = self.root / "uploads"
        self.output_dir = self.root / "runs"
        self.upload_dir.mkdir()
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(self.root / "run_log.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = str(self.upload_dir)

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        os.environ.pop("MEDICAL_RECORD_AGENT_UPLOAD_DIR", None)
        self.temp_dir.cleanup()

    def test_save_run_log_generates_markdown_from_task_and_audio(self):
        task_id = create_task("text", "CREATED", input_text="[patient] fever")
        step_id = create_task_step(
            task_id,
            "extract_fields",
            "RUNNING",
            input_snapshot={"conversation_text": "[patient] fever"},
        )
        finish_task_step(
            step_id,
            status="SUCCEEDED",
            output_snapshot={"chief_complaint": {"value": "发热3天"}},
        )
        update_task(
            task_id,
            status="WAITING_DOCTOR_REVIEW",
            current_stage="doctor_review",
            result_json=json_dumps(
                {
                    "draft": "门诊病历草稿\n主诉：发热3天",
                    "safety_check": {
                        "passed": True,
                        "blocked": False,
                        "errors": [],
                        "warnings": ["查体待补充"],
                    },
                }
            ),
        )

        audio_id = "audio123"
        (self.upload_dir / f"{audio_id}.wav").write_bytes(b"RIFF....WAVE")
        (self.upload_dir / f"{audio_id}.record.json").write_text(
            json.dumps(
                {
                    "audio_id": audio_id,
                    "filename": "fever_01.wav",
                    "path": str(self.upload_dir / f"{audio_id}.wav"),
                    "status": "uploaded",
                    "size_bytes": 12,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.upload_dir / f"{audio_id}.transcript.json").write_text(
            json.dumps(
                {
                    "audio_id": audio_id,
                    "engine": "funasr-local",
                    "text": "发热三天",
                    "conversation_text": "[patient] 发热三天",
                    "segments": [{"role": "patient", "text": "发热三天"}],
                    "duration": 8.5,
                    "medical_keywords": {
                        "expected": ["发热"],
                        "recognized": ["发热"],
                        "missing": [],
                    },
                    "role_strategy": "single_segment_needs_review",
                    "warnings": ["医生/患者角色需人工校正"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.upload_dir / f"{audio_id}.evaluation.json").write_text(
            json.dumps(
                {
                    "audio_id": audio_id,
                    "engine": "funasr-local",
                    "cer": 0.12,
                    "keyword_recall": 1.0,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        output_path = save_run_log(
            task_id=task_id,
            audio_id=audio_id,
            title="fever_01_demo",
            output_dir=self.output_dir,
            upload_dir=self.upload_dir,
            now=datetime(2026, 6, 8, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertEqual(output_path.name, "2026-06-08_fever_01_demo.md")
        content = output_path.read_text(encoding="utf-8")
        self.assertIn("运行日志：fever_01_demo", content)
        self.assertIn("engine：funasr-local", content)
        self.assertIn("CER：0.12", content)
        self.assertIn("keyword_recall：1.0", content)
        self.assertIn("single_segment_needs_review", content)
        self.assertIn("Agent mode: Plan-and-Execute + Human-in-the-loop", content)
        self.assertIn("LLM provider: mock", content)
        self.assertIn("LLM model: mock-deterministic-extractor", content)
        self.assertIn("LLM fallback: False", content)
        self.assertIn("Plan steps: ASR_TRANSCRIBE -> FIELD_EXTRACTION", content)
        self.assertIn("reason=doctor_review_required", content)
        self.assertIn("Human-in-the-loop: True", content)
        self.assertIn("Export allowed: False", content)
        self.assertIn("extract_fields", content)
        self.assertIn("门诊病历草稿", content)
        self.assertIn("passed：True", content)


if __name__ == "__main__":
    unittest.main()
