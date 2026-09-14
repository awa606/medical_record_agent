import os
import tempfile
import unittest

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents import MedicalRecordOrchestrator
from app.api.tasks import (
    ReviewRequest,
    TaskApprovalRequest,
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
from app.db import get_audit_logs, set_task_owner
from app.db import (
    get_active_approval_for_task,
    list_approval_items_for_approval,
    list_record_revisions_for_task,
)
from app.main import app
from app.services import WORD_NOTICE
from app.schemas import CandidateDiagnosis, MedicalField, MedicalRecordFields, SafetyCheckResult, SourceSpan
from tests.auth_helpers import create_user, login_as_user


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

    def approval_payload_for_task(self, task_id: int) -> dict:
        task = read_task(task_id)
        fields = task["result_json"]["fields"]
        readiness = read_export_readiness(task_id)
        field_items = []
        for key, field in fields.items():
            if key == "candidate_diagnoses":
                continue
            if isinstance(field, dict) and (field.get("missing") or not field.get("value")):
                field_items.append({"key": key, "action": "accept_missing", "note": "测试接受本次缺失"})
        diagnoses = [
            {
                "index": index,
                "action": "confirm_candidate",
                "high_risk_confirmed": bool(diagnosis.get("risk_warnings")),
            }
            for index, diagnosis in enumerate(fields.get("candidate_diagnoses") or [])
        ]
        return {
            "revision_id": readiness.revision_id,
            "content_hash": readiness.content_hash,
            "confirm_all_regular_fields": True,
            "fields": field_items,
            "diagnoses": diagnoses,
        }

    def _custom_fields(
        self,
        *,
        include_candidate: bool = True,
        candidate_high_risk: bool = False,
        field_conflict: bool = False,
    ) -> MedicalRecordFields:
        chief_status = "conflicting" if field_conflict else "complete"
        candidates = []
        if include_candidate:
            candidates.append(
                CandidateDiagnosis(
                    name="发热待查",
                    evidence=[SourceSpan(text="发热")],
                    reason="测试候选诊断",
                    risk_warnings=["高热需进一步评估"] if candidate_high_risk else [],
                )
            )
        return MedicalRecordFields(
            chief_complaint=MedicalField(
                value="发热3天",
                missing=False,
                status=chief_status,
                source_spans=[SourceSpan(text="发热3天")],
            ),
            present_illness=MedicalField(
                value="患者自述发热3天。",
                missing=False,
                status="complete",
                source_spans=[SourceSpan(text="发热3天")],
            ),
            previous_treatment=MedicalField.missing_field("未询问既往处理"),
            accompanying_symptoms=MedicalField.missing_field("未询问伴随症状"),
            past_history=MedicalField.missing_field("未询问既往史"),
            allergy_history=MedicalField.missing_field("未询问过敏史"),
            physical_exam=MedicalField.missing_field("待医生查体补充"),
            candidate_diagnoses=candidates,
        )

    def _create_reviewed_task(self, fields: MedicalRecordFields | None = None) -> int:
        result = MedicalRecordOrchestrator().run_from_text("seed task for approval tests")
        task_id = result["task_id"]
        review_task(task_id, self._review_request(task_id, fields or self._custom_fields()))
        return task_id

    def _review_request(self, task_id: int, fields: MedicalRecordFields) -> ReviewRequest:
        readiness = read_export_readiness(task_id)
        return ReviewRequest(
            fields=fields,
            expected_revision_id=readiness.revision_id,
            expected_content_hash=readiness.content_hash,
        )

    def _minimal_payload(
        self,
        task_id: int,
        *,
        include_missing: bool = True,
        include_candidates: bool = True,
        include_high_risk: bool = False,
        stale: dict | None = None,
    ) -> dict:
        task = read_task(task_id)
        fields = task["result_json"]["fields"]
        readiness = read_export_readiness(task_id)
        payload = {
            "revision_id": readiness.revision_id,
            "content_hash": readiness.content_hash,
            "confirm_all_regular_fields": True,
            "fields": [],
            "diagnoses": [],
            "high_risk_conflicts": [],
        }
        if include_missing:
            for key, field in fields.items():
                if key == "candidate_diagnoses":
                    continue
                if isinstance(field, dict) and (field.get("missing") or not field.get("value")):
                    payload["fields"].append({"key": key, "action": "accept_missing"})
        if include_candidates:
            for index, _diagnosis in enumerate(fields.get("candidate_diagnoses") or []):
                payload["diagnoses"].append({"index": index, "action": "confirm_candidate"})
        if include_high_risk:
            for index, diagnosis in enumerate(fields.get("candidate_diagnoses") or []):
                if diagnosis.get("risk_warnings"):
                    payload["high_risk_conflicts"].append(
                        {"key": f"diagnosis:{index}", "confirmed": True}
                    )
            for key, field in fields.items():
                if key == "candidate_diagnoses":
                    continue
                if isinstance(field, dict) and field.get("status") == "conflicting":
                    payload["high_risk_conflicts"].append(
                        {"key": f"field:{key}", "confirmed": True}
                    )
        if stale:
            payload.update(stale)
        return payload

    def test_task_routes_are_registered(self):
        route_paths = set(app.openapi()["paths"])

        self.assertIn("/api/tasks/{task_id}", route_paths)
        self.assertIn("/api/tasks/{task_id}/steps", route_paths)
        self.assertIn("/api/tasks/{task_id}/trace", route_paths)
        self.assertIn("/api/tasks/{task_id}/events", route_paths)
        self.assertIn("/api/tasks/{task_id}/export-readiness", route_paths)
        self.assertIn("/api/tasks/{task_id}/exports/{export_format}", route_paths)
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
        reviewed = review_task(task_id, self._review_request(task_id, fields))
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

        approved = approve_task(
            task_id,
            TaskApprovalRequest.model_validate(self.approval_payload_for_task(task_id)),
        )
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
        self.assertIn("门诊病历", document_xml)
        self.assertIn("主诉", document_xml)
        self.assertIn("现病史", document_xml)
        self.assertIn("医生修订", document_xml)
        self.assertNotIn("鍙戠儹", document_xml)
        self.assertNotIn("涓昏瘔", document_xml)

    def test_export_download_route_returns_docx_after_approval(self):
        client = TestClient(app)
        doctor = create_user(client, username="download-doctor")
        result = MedicalRecordOrchestrator().run_from_text("patient has fever for three days")
        task_id = result["task_id"]
        set_task_owner(task_id, doctor["id"])

        login_as_user(client, username="download-doctor")
        approved = client.post(f"/api/tasks/{task_id}/approve", json=self.approval_payload_for_task(task_id))
        self.assertEqual(approved.status_code, 200, approved.text)
        exported = client.post(f"/api/tasks/{task_id}/export")
        self.assertEqual(exported.status_code, 200, exported.text)

        downloaded = client.get(f"/api/tasks/{task_id}/exports/docx")
        self.assertEqual(downloaded.status_code, 200, downloaded.text)
        self.assertEqual(
            downloaded.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn(
            f"task_{task_id}_medical_record.docx",
            downloaded.headers.get("content-disposition", ""),
        )
        with ZipFile(BytesIO(downloaded.content)) as docx:
            document_xml = docx.read("word/document.xml").decode("utf-8")
        self.assertIn(WORD_NOTICE, document_xml)
        self.assertIn("门诊病历", document_xml)
        self.assertIn("主诉", document_xml)
        self.assertIn("现病史", document_xml)
        self.assertNotIn("鍙戠儹", document_xml)
        self.assertNotIn("涓昏瘔", document_xml)

    def test_export_download_route_enforces_task_owner(self):
        client = TestClient(app)
        doctor_a = create_user(client, username="download-owner")
        create_user(client, username="download-other")
        result = MedicalRecordOrchestrator().run_from_text("patient has fever for three days")
        task_id = result["task_id"]
        set_task_owner(task_id, doctor_a["id"])

        login_as_user(client, username="download-owner")
        self.assertEqual(client.post(f"/api/tasks/{task_id}/approve", json=self.approval_payload_for_task(task_id)).status_code, 200)
        self.assertEqual(client.post(f"/api/tasks/{task_id}/export").status_code, 200)
        client.post("/api/auth/logout")

        login_as_user(client, username="download-other")
        forbidden = client.get(f"/api/tasks/{task_id}/exports/docx")
        self.assertEqual(forbidden.status_code, 403)

    def test_empty_approval_request_is_rejected(self):
        task_id = self._create_reviewed_task()
        client = TestClient(app)
        doctor = create_user(client, username="empty-approval-doctor")
        set_task_owner(task_id, doctor["id"])
        login_as_user(client, username="empty-approval-doctor")

        response = client.post(f"/api/tasks/{task_id}/approve", json={})

        self.assertIn(response.status_code, {400, 422})
        self.assertIsNone(get_active_approval_for_task(task_id))

    def test_explicit_regular_field_confirmation_persists_approval_items(self):
        task_id = self._create_reviewed_task()

        approved = approve_task(
            task_id,
            TaskApprovalRequest.model_validate(self._minimal_payload(task_id)),
        )

        approval = get_active_approval_for_task(task_id)
        self.assertIsNotNone(approval)
        self.assertEqual(
            approval["content_hash"],
            approved["result_json"]["record_revision"]["content_hash"],
        )
        items = list_approval_items_for_approval(int(approval["id"]))
        self.assertTrue(
            any(item["item_type"] == "field" and item["action"] == "confirm_content" for item in items)
        )
        self.assertTrue(
            any(item["item_type"] == "field" and item["action"] == "accept_missing" for item in items)
        )

    def test_missing_items_block_completion_until_explicitly_handled(self):
        task_id = self._create_reviewed_task()

        with self.assertRaises(HTTPException) as blocked:
            approve_task(
                task_id,
                TaskApprovalRequest.model_validate(
                    self._minimal_payload(task_id, include_missing=False)
                ),
            )

        self.assertEqual(blocked.exception.status_code, 409)
        self.assertIsNone(get_active_approval_for_task(task_id))

    def test_unprocessed_candidate_diagnosis_blocks_completion(self):
        task_id = self._create_reviewed_task()

        with self.assertRaises(HTTPException) as blocked:
            approve_task(
                task_id,
                TaskApprovalRequest.model_validate(
                    self._minimal_payload(task_id, include_candidates=False)
                ),
            )

        self.assertEqual(blocked.exception.status_code, 409)
        self.assertIsNone(get_active_approval_for_task(task_id))

    def test_high_risk_candidate_requires_separate_confirmation(self):
        task_id = self._create_reviewed_task(
            self._custom_fields(candidate_high_risk=True)
        )

        with self.assertRaises(HTTPException) as blocked:
            approve_task(
                task_id,
                TaskApprovalRequest.model_validate(self._minimal_payload(task_id)),
            )

        self.assertEqual(blocked.exception.status_code, 409)
        self.assertIsNone(get_active_approval_for_task(task_id))

        approved = approve_task(
            task_id,
            TaskApprovalRequest.model_validate(
                self._minimal_payload(task_id, include_high_risk=True)
            ),
        )
        self.assertTrue(
            approved["result_json"]["fields"]["candidate_diagnoses"][0][
                "high_risk_confirmed_by_doctor"
            ]
        )

    def test_conflicting_field_is_not_covered_by_bulk_regular_confirmation(self):
        task_id = self._create_reviewed_task(self._custom_fields(field_conflict=True))

        with self.assertRaises(HTTPException) as blocked:
            approve_task(
                task_id,
                TaskApprovalRequest.model_validate(self._minimal_payload(task_id)),
            )

        self.assertEqual(blocked.exception.status_code, 409)
        payload = self._minimal_payload(task_id, include_high_risk=True)
        payload["fields"].append({"key": "chief_complaint", "action": "confirm_content"})
        approved = approve_task(task_id, TaskApprovalRequest.model_validate(payload))
        self.assertTrue(
            approved["result_json"]["fields"]["chief_complaint"][
                "high_risk_confirmed_by_doctor"
            ]
        )

    def test_approval_is_bound_to_current_revision_and_content_hash(self):
        task_id = self._create_reviewed_task()
        payload = self._minimal_payload(task_id)
        approved = approve_task(task_id, TaskApprovalRequest.model_validate(payload))

        approval = get_active_approval_for_task(task_id)
        self.assertIsNotNone(approval)
        self.assertEqual(int(approval["revision_id"]), payload["revision_id"])
        self.assertEqual(approval["content_hash"], payload["content_hash"])
        self.assertEqual(
            approved["result_json"]["approval"]["content_hash"],
            payload["content_hash"],
        )

    def test_stale_revision_approval_returns_409(self):
        task_id = self._create_reviewed_task()
        stale_payload = self._minimal_payload(task_id)
        updated_fields = self._custom_fields()
        updated_fields.chief_complaint.value = "发热4天"
        review_task(task_id, self._review_request(task_id, updated_fields))

        with self.assertRaises(HTTPException) as blocked:
            approve_task(task_id, TaskApprovalRequest.model_validate(stale_payload))

        self.assertEqual(blocked.exception.status_code, 409)

    def test_edit_creates_new_revision_and_invalidates_old_approval(self):
        task_id = self._create_reviewed_task()
        approve_task(task_id, TaskApprovalRequest.model_validate(self._minimal_payload(task_id)))
        old_approval = get_active_approval_for_task(task_id)
        self.assertIsNotNone(old_approval)

        updated_fields = self._custom_fields()
        updated_fields.chief_complaint.value = "发热4天"
        reviewed = review_task(task_id, self._review_request(task_id, updated_fields))

        revisions = list_record_revisions_for_task(task_id)
        self.assertGreaterEqual(len(revisions), 3)
        self.assertNotEqual(
            reviewed["current_record_revision_id"],
            int(old_approval["revision_id"]),
        )
        self.assertIsNone(get_active_approval_for_task(task_id))

    def test_old_approval_cannot_export_new_revision(self):
        task_id = self._create_reviewed_task()
        approve_task(task_id, TaskApprovalRequest.model_validate(self._minimal_payload(task_id)))
        updated_fields = self._custom_fields()
        updated_fields.chief_complaint.value = "发热4天"
        review_task(task_id, self._review_request(task_id, updated_fields))

        with self.assertRaises(HTTPException) as blocked:
            export_task(task_id)

        self.assertEqual(blocked.exception.status_code, 400)
        self.assertFalse(blocked.exception.detail["ready"])

    def test_current_revision_full_approval_allows_export(self):
        task_id = self._create_reviewed_task(
            self._custom_fields(candidate_high_risk=True, field_conflict=True)
        )
        payload = self._minimal_payload(task_id, include_high_risk=True)
        payload["fields"].append({"key": "chief_complaint", "action": "confirm_content"})
        approve_task(task_id, TaskApprovalRequest.model_validate(payload))

        exported = export_task(task_id)

        self.assertTrue(exported["export_readiness"]["ready"])
        self.assertTrue(Path(exported["exports"]["word_path"]).exists())

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
