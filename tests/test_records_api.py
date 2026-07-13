import os
import tempfile
import unittest

from fastapi import BackgroundTasks, HTTPException

from app.agents import MedicalRecordOrchestrator
from app.api.records import (
    GenerateRecordRequest,
    PreviewRecordRequest,
    generate_record,
    preview_record,
    run_record_generation_task,
)
from app.api.tasks import read_task


class RecordsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(
            self.temp_dir.name,
            "records.sqlite3",
        )

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        self.temp_dir.cleanup()

    def test_generate_record_creates_task_for_background_execution(self):
        payload = GenerateRecordRequest(
            conversation_text="左手手掌被咬了，大约两个小时左右，用酒精冲洗，牙龈出血。"
        )

        response = generate_record(payload, BackgroundTasks())

        self.assertIsInstance(response["task_id"], int)
        self.assertEqual(response["status"], MedicalRecordOrchestrator.STATUS_CREATED)
        self.assertEqual(
            response["events_url"],
            f"/api/tasks/{response['task_id']}/events",
        )

        created_task = read_task(response["task_id"])
        self.assertEqual(created_task["status"], MedicalRecordOrchestrator.STATUS_CREATED)
        self.assertEqual(created_task["input_text"], payload.conversation_text)

        run_record_generation_task(response["task_id"], payload.conversation_text)

        completed_task = read_task(response["task_id"])
        self.assertEqual(completed_task["status"], MedicalRecordOrchestrator.STATUS_WAITING_DOCTOR_REVIEW)
        self.assertIn("门诊病历草稿", completed_task["result_json"]["draft"])
        self.assertIn("quality_report", completed_task["result_json"])

    def test_preview_record_returns_non_persistent_preview(self):
        payload = PreviewRecordRequest(
            conversation_text=(
                "[医生] 你好，哪里不舒服？\n"
                "[患者] 我发热三天，最高体温40度，还有咳嗽和铁锈色痰。\n"
                "[医生] 之前做过什么处理？\n"
                "[患者] 在卫生院吃过布洛芬，退热后又反复发热。"
            ),
            source="asr_partial",
            segments=[
                {
                    "segment_id": "seg-doctor-1",
                    "role": "医生",
                    "text": "你好，哪里不舒服？",
                    "start_time": 0.0,
                    "end_time": 1.2,
                },
                {
                    "segment_id": "seg-patient-1",
                    "role": "患者",
                    "text": "我发热三天，最高体温40度，还有咳嗽和铁锈色痰。",
                    "start_time": 1.2,
                    "end_time": 4.8,
                },
            ],
        )

        response = preview_record(payload)
        response_data = response.model_dump()

        self.assertEqual(response.status, "preview_ready")
        self.assertEqual(response.source, "asr_partial")
        self.assertEqual(response.segment_count, 2)
        self.assertIn("fields_preview", response_data)
        self.assertIn("candidate_diagnoses", response_data)
        self.assertIn("treatment_plan", response_data)
        self.assertIn("structured_updates", response_data)
        self.assertIn("evidence_links", response_data)
        self.assertIn("quality_preview", response_data)
        self.assertIn(response.preview_stage, {"collecting", "structured_preview", "diagnosis_preview"})
        self.assertIsInstance(response.ready_for_formal_generation, bool)
        self.assertTrue(any(item["status"] == "preview" for item in response.structured_updates))
        self.assertGreater(len(response.candidate_diagnoses), 0)
        chief_spans = response.fields_preview["chief_complaint"]["source_spans"]
        self.assertTrue(any(span.get("segment_id") == "seg-patient-1" for span in chief_spans))
        self.assertTrue(any(item["segment_id"] == "seg-patient-1" for item in response.evidence_links))
        self.assertTrue(
            any("seg-patient-1" in item["source_segment_ids"] for item in response.structured_updates)
        )
        self.assertGreater(response.quality_preview["core_completeness"], 0)
        self.assertTrue(response.quality_preview["field_quality"])
        self.assertFalse(response.quality_preview["export_allowed"])
        self.assertNotIn("task_id", response_data)
        self.assertNotIn("events_url", response_data)

    def test_preview_record_marks_partial_missing_items_without_export_task(self):
        response = preview_record(
            PreviewRecordRequest(
                conversation_text="[患者] 我有点发热。",
                source="asr_partial",
            )
        )

        self.assertEqual(response.status, "preview_ready")
        self.assertGreater(len(response.missing_items), 0)
        self.assertIn("实时预览", response.preview_notice)
        self.assertTrue(response.structured_updates)
        self.assertEqual(response.quality_preview["status"], "needs_review")
        self.assertNotIn("task_id", response.model_dump())

    def test_preview_ignores_provisional_windows_and_uses_stable_mapped_turns(self):
        response = preview_record(
            PreviewRecordRequest(
                conversation_text="[患者] 临时混合文本不应进入预览",
                source="asr_partial",
                segments=[
                    {
                        "segment_id": "temp-1",
                        "provisional": True,
                        "role": "患者",
                        "text": "临时混合文本不应进入预览",
                    },
                    {
                        "segment_id": "stable-1",
                        "provisional": False,
                        "role": "患者",
                        "text": "我发热三天。",
                    },
                ],
            )
        )

        self.assertEqual(response.segment_count, 1)
        self.assertEqual(response.character_count, len("[患者] 我发热三天。"))

    def test_preview_rejects_unmapped_stable_speaker(self):
        with self.assertRaises(HTTPException) as raised:
            preview_record(
                PreviewRecordRequest(
                    conversation_text="[说话人A] 我发热三天。",
                    source="asr_partial",
                    segments=[
                        {
                            "segment_id": "stable-1",
                            "provisional": False,
                            "speaker_id": "spk0",
                            "role": None,
                            "text": "我发热三天。",
                        }
                    ],
                )
            )
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("角色映射", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
