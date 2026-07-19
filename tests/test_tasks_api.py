import os
import tempfile
import unittest

from pathlib import Path
from zipfile import ZipFile

from fastapi import HTTPException

from app.agents import MedicalRecordOrchestrator
from app.api.tasks import (
    ReviewRequest,
    _event_from_audit_log,
    _validate_export_ready,
    approve_task,
    export_task,
    read_task_agent_trace,
    read_export_readiness,
    read_task,
    read_task_steps,
    review_task,
)
from app.db import get_audit_logs
from app.main import app
from app.services import WORD_NOTICE
from app.schemas import SafetyCheckResult


class TaskApiTests(unittest.TestCase):
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
            "api.sqlite3",
        )
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(
            self.temp_dir.name,
            "outputs",
        )

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        os.environ.pop("MEDICAL_RECORD_AGENT_OUTPUT_DIR", None)
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_task_routes_are_registered(self):
        route_paths = set(app.openapi()["paths"])

        self.assertIn("/api/tasks/{task_id}", route_paths)
        self.assertIn("/api/tasks/{task_id}/steps", route_paths)
        self.assertIn("/api/tasks/{task_id}/trace", route_paths)
        self.assertIn("/api/tasks/{task_id}/events", route_paths)
        self.assertIn("/api/tasks/{task_id}/export-readiness", route_paths)
        self.assertIn("/api/records/generate", route_paths)

    def test_read_task_and_steps(self):
        result = MedicalRecordOrchestrator().run_from_text(
            "左手手掌被咬了，大概两个小时左右，用酒精冲洗，牙龈出血。"
        )

        task = read_task(result["task_id"])
        steps = read_task_steps(result["task_id"])

        self.assertEqual(task["id"], result["task_id"])
        self.assertEqual(task["status"], MedicalRecordOrchestrator.STATUS_WAITING_DOCTOR_REVIEW)
        self.assertIsInstance(task["result_json"], dict)
        self.assertIn("draft", task["result_json"])
        self.assertEqual(
            [step["step_name"] for step in steps],
            ["extract_fields", "generate_draft", "safety_check"],
        )

    def test_read_task_agent_trace_exposes_decision_boundary(self):
        result = MedicalRecordOrchestrator().run_from_text(
            "patient has fever for three days"
        )

        trace = read_task_agent_trace(result["task_id"])

        self.assertEqual(trace["agent_mode"], "Plan-and-Execute + Human-in-the-loop")
        self.assertEqual(trace["input_type"], "text")
        self.assertEqual(trace["llm"]["llm_provider"], "mock")
        self.assertEqual(trace["llm"]["model"], "mock-deterministic-extractor")
        self.assertFalse(trace["llm"]["fallback"])
        self.assertIn("TEXT_INPUT_NORMALIZE", trace["plan"])
        self.assertEqual(
            [step["step"] for step in trace["executed_steps"]],
            ["FIELD_EXTRACTION", "DRAFT_GENERATION", "SAFETY_CHECK"],
        )
        self.assertFalse(trace["decision"]["export_allowed"])
        self.assertEqual(trace["decision"]["reason"], "doctor_review_required")
        self.assertTrue(trace["decision"]["human_in_the_loop_required"])

    def test_audit_logs_can_be_mapped_to_sse_events(self):
        result = MedicalRecordOrchestrator().run_from_text(
            "左手手掌被咬了，大概两个小时左右，用酒精冲洗，牙龈出血。"
        )

        events = [
            event
            for event in (_event_from_audit_log(log) for log in get_audit_logs(result["task_id"]))
            if event is not None
        ]
        event_names = [event_name for event_name, _ in events]

        self.assertEqual(event_names[0], "CREATED")
        self.assertIn("EXTRACTING_FIELDS", event_names)
        self.assertIn("GENERATING_DRAFT", event_names)
        self.assertIn("SAFETY_CHECKING", event_names)
        self.assertIn("WAITING_DOCTOR_REVIEW", event_names)
        self.assertEqual(event_names[-1], "WAITING_DOCTOR_REVIEW")

    def test_read_missing_task_returns_404(self):
        with self.assertRaises(HTTPException) as context:
            read_task(999)

        self.assertEqual(context.exception.status_code, 404)

    def test_review_approve_and_export_flow(self):
        result = MedicalRecordOrchestrator().run_from_text(
            "左手手掌被咬了，大概两个小时左右，用酒精冲洗，牙龈出血。"
        )
        task_id = result["task_id"]

        fields = result["fields"]
        fields.chief_complaint.value = "左手手掌被咬伤后肿痛约2小时（医生修订）"
        reviewed = review_task(task_id, ReviewRequest(fields=fields))
        self.assertIn("医生修订", reviewed["result_json"]["fields"]["chief_complaint"]["value"])

        with self.assertRaises(HTTPException) as blocked:
            export_task(task_id)
        self.assertEqual(blocked.exception.status_code, 400)
        self.assertFalse(blocked.exception.detail["ready"])
        self.assertTrue(blocked.exception.detail["blocked"])
        self.assertIn("errors", blocked.exception.detail)

        readiness_before_approval = read_export_readiness(task_id)
        self.assertFalse(readiness_before_approval.ready)
        self.assertTrue(readiness_before_approval.blocked)
        self.assertIn("医生确认", readiness_before_approval.next_action)

        approved = approve_task(task_id)
        approved_fields = approved["result_json"]["fields"]
        self.assertTrue(approved_fields["chief_complaint"]["confirmed_by_doctor"])
        self.assertTrue(approved_fields["candidate_diagnoses"][0]["confirmed_by_doctor"])

        readiness_after_approval = read_export_readiness(task_id)
        self.assertTrue(readiness_after_approval.ready)
        self.assertFalse(readiness_after_approval.blocked)

        exported = export_task(task_id)
        self.assertIn("export_readiness", exported)
        self.assertTrue(exported["export_readiness"]["ready"])
        markdown_path = Path(exported["exports"]["markdown_path"])
        word_path = Path(exported["exports"]["word_path"])

        self.assertTrue(markdown_path.exists())
        self.assertTrue(word_path.exists())
        self.assertIn(WORD_NOTICE, markdown_path.read_text(encoding="utf-8"))
        with ZipFile(word_path) as docx:
            document_xml = docx.read("word/document.xml").decode("utf-8")
        self.assertIn(WORD_NOTICE, document_xml)

    def test_export_readiness_blocks_provider_fallback_trace(self):
        result = MedicalRecordOrchestrator().run_from_text(
            "左手手掌被咬了，大约两个小时左右，用酒精冲洗，牙龈出血。"
        )
        fields = result["fields"]
        for field in [
            fields.chief_complaint,
            fields.present_illness,
            fields.previous_treatment,
            fields.accompanying_symptoms,
            fields.past_history,
            fields.allergy_history,
            fields.physical_exam,
        ]:
            field.confirmed_by_doctor = True
        for diagnosis in fields.candidate_diagnoses:
            diagnosis.confirmed_by_doctor = True

        errors = _validate_export_ready(
            {
                "fields": fields.model_dump(),
                "safety_check": SafetyCheckResult(passed=True).model_dump(),
                "llm_trace": {"fallback": True, "fallback_reason": "provider failed"},
            }
        )

        self.assertTrue(any("降级模式" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
