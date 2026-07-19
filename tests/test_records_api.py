import os
import tempfile
import unittest

from fastapi import BackgroundTasks, HTTPException

from app.agents import MedicalRecordOrchestrator
from app.api.records import (
    BuildDraftRequest,
    ExtractFieldsRequest,
    GenerateRecordRequest,
    PreviewRecordRequest,
    QualityRequest,
    build_draft,
    evaluate_record_quality,
    extract_fields,
    generate_record,
    preview_record,
    run_record_generation_task,
)
from app.api.tasks import read_task


class RecordsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "LLM_PROVIDER",
                "RECORD_PROVIDER_MODE",
                "ONLINE_LLM_API_BASE",
                "ONLINE_LLM_API_KEY",
                "ONLINE_LLM_MODEL",
                "OLLAMA_BASE_URL",
                "OLLAMA_MODEL",
            ]
        }
        for key in self.original_env:
            os.environ.pop(key, None)
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(
            self.temp_dir.name,
            "records.sqlite3",
        )

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
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

    def test_reusable_record_service_interfaces_do_not_create_task(self):
        extracted = extract_fields(
            ExtractFieldsRequest(
                conversation_text=(
                    "[doctor] hello, what is wrong?\n"
                    "[patient] fever for three days and cough.\n"
                    "[doctor] did you take any medicine?\n"
                    "[patient] ibuprofen, but fever returned."
                ),
                source="external_api",
                segments=[
                    {
                        "segment_id": "seg-patient-1",
                        "speaker_id": "spk1",
                        "role": "patient",
                        "role_confidence": 0.99,
                        "role_source": "manual_speaker_map",
                        "text": "fever for three days and cough.",
                    }
                ],
            )
        )

        self.assertEqual(extracted.status, "fields_extracted")
        self.assertFalse(extracted.creates_task)
        self.assertIn("chief_complaint", extracted.fields)
        self.assertIn("quality_report", extracted.model_dump())
        self.assertIn("extraction_info", extracted.model_dump())
        self.assertEqual(extracted.extraction_info["actual_provider"], "mock")
        self.assertIn("candidate_diagnoses", extracted.model_dump())
        self.assertNotIn("task_id", extracted.model_dump())

        draft_result = build_draft(BuildDraftRequest(fields=extracted.fields))

        self.assertEqual(draft_result.status, "draft_built")
        self.assertFalse(draft_result.creates_task)
        self.assertFalse(draft_result.export_allowed)
        self.assertIn("draft", draft_result.model_dump())
        self.assertIn("safety_check", draft_result.model_dump())
        self.assertIn("quality_report", draft_result.model_dump())

        quality = evaluate_record_quality(
            QualityRequest(fields=extracted.fields, draft=draft_result.draft)
        )

        self.assertIn(quality.status, {"needs_review", "ready_for_review"})
        self.assertFalse(quality.creates_task)
        self.assertIn("field_quality", quality.quality_report)

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
                {
                    "segment_id": "seg-patient-2",
                    "role": "患者",
                    "text": "在卫生院吃过布洛芬，退热后又反复发热。",
                    "start_time": 4.8,
                    "end_time": 7.6,
                },
            ],
        )

        response = preview_record(payload)
        response_data = response.model_dump()

        self.assertEqual(response.status, "preview_ready")
        self.assertEqual(response.source, "asr_partial")
        self.assertEqual(response.segment_count, 3)
        self.assertIn("fields_preview", response_data)
        self.assertIn("candidate_diagnoses", response_data)
        self.assertIn("treatment_plan", response_data)
        self.assertIn("structured_updates", response_data)
        self.assertIn("evidence_links", response_data)
        self.assertIn("quality_preview", response_data)
        self.assertIn("extraction_info", response_data)
        self.assertEqual(response.extraction_info["extraction_mode"], "clinical_fact_rules_v1")
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
        self.assertIn("candidate_diagnosis_status", response.quality_preview)
        self.assertIn("diagnosis_quality", response.quality_preview["candidate_diagnosis_status"])
        self.assertIn("treatment_safety", response.quality_preview)
        self.assertIn("status", response.quality_preview["treatment_safety"])
        self.assertIn("quality_issues", response.quality_preview["treatment_safety"])
        self.assertNotIn("task_id", response_data)
        self.assertNotIn("events_url", response_data)

    def test_preview_record_marks_partial_missing_items_without_export_task(self):
        response = preview_record(
            PreviewRecordRequest(
                conversation_text="[患者] 我发烧39°C。",
                source="asr_partial",
            )
        )

        self.assertEqual(response.status, "preview_ready")
        self.assertGreater(len(response.missing_items), 0)
        self.assertEqual(response.fields_preview["chief_complaint"]["status"], "partial")
        self.assertEqual(response.fields_preview["present_illness"]["status"], "partial")
        self.assertIn("体温约39℃", response.fields_preview["present_illness"]["value"])
        self.assertIn("主诉", response.quality_preview["partial_fields"])
        self.assertIn("实时预览", response.preview_notice)
        self.assertTrue(response.structured_updates)
        self.assertEqual(response.quality_preview["status"], "needs_review")
        self.assertEqual(response.extraction_info["actual_provider"], "mock")
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

    def test_extract_fields_rejects_low_confidence_speaker_role(self):
        with self.assertRaises(HTTPException) as raised:
            extract_fields(
                ExtractFieldsRequest(
                    conversation_text="[患者] 我发热三天",
                    source="external_api",
                    segments=[
                        {
                            "segment_id": "stable-1",
                            "speaker_id": "spk1",
                            "role": "患者",
                            "role_confidence": 0.86,
                            "role_source": "global_two_party_constraint",
                            "text": "我发热三天",
                        }
                    ],
                )
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["role_quality"]["status"], "needs_review")

    def test_live_mode_preview_returns_503_when_provider_is_mock(self):
        os.environ["RECORD_PROVIDER_MODE"] = "live"

        with self.assertRaises(HTTPException) as raised:
            preview_record(
                PreviewRecordRequest(
                    conversation_text="[患者] 我发烧39°C",
                    source="text_preview",
                )
            )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertFalse(raised.exception.detail["fallback"])
        self.assertEqual(raised.exception.detail["mode"], "live")

    def test_build_draft_returns_generation_info(self):
        extracted = extract_fields(
            ExtractFieldsRequest(
                conversation_text="[患者] 我发烧39°C",
                source="external_api",
            )
        )

        draft_result = build_draft(BuildDraftRequest(fields=extracted.fields))

        self.assertIn("generation_info", draft_result.model_dump())
        self.assertEqual(draft_result.generation_info["actual_provider"], "mock")
        self.assertEqual(draft_result.generation_info["mode"], "demo")

    def test_extract_fields_rejects_unmapped_stable_speaker(self):
        with self.assertRaises(HTTPException) as raised:
            extract_fields(
                ExtractFieldsRequest(
                    conversation_text="[说话人 A] 我发热三天",
                    source="external_api",
                    segments=[
                        {
                            "segment_id": "stable-1",
                            "speaker_id": "spk1",
                            "role": None,
                            "text": "我发热三天",
                        }
                    ],
                )
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["role_quality"]["status"], "needs_review")


if __name__ == "__main__":
    unittest.main()
