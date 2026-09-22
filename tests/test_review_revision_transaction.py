from __future__ import annotations

import json
import os
import tempfile
import unittest
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi import HTTPException

from app.agents import MedicalRecordOrchestrator
from app.api.tasks import ReviewRequest, TaskApprovalRequest, approve_task, export_task, review_task
from app.db import (
    create_record_revision_for_task,
    get_active_approval_for_task,
    get_audit_logs,
    get_record_revision,
    get_task,
    list_approvals_for_task,
    list_record_revisions_for_task,
)
from app.schemas import CandidateDiagnosis, ClinicalReference, MedicalRecordFields, SourceSpan
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields


class ReviewRevisionTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "MEDICAL_RECORD_AGENT_DB",
                "MEDICAL_RECORD_AGENT_OUTPUT_DIR",
                "LLM_PROVIDER",
                "RECORD_PROVIDER_MODE",
                "ONLINE_LLM_API_BASE",
                "ONLINE_LLM_API_KEY",
                "ONLINE_LLM_MODEL",
                "OLLAMA_BASE_URL",
                "OLLAMA_MODEL",
            ]
        }
        for key in [
            "LLM_PROVIDER",
            "RECORD_PROVIDER_MODE",
            "ONLINE_LLM_API_BASE",
            "ONLINE_LLM_API_KEY",
            "ONLINE_LLM_MODEL",
            "OLLAMA_BASE_URL",
            "OLLAMA_MODEL",
        ]:
            os.environ.pop(key, None)
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "review-transaction.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(self.temp_dir.name, "outputs")

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def _approved_task(self) -> tuple[int, MedicalRecordFields]:
        result = MedicalRecordOrchestrator().run_from_text("patient has fever for three days")
        task_id = int(result["task_id"])
        approved = approve_task(
            task_id,
            TaskApprovalRequest(**approval_payload_for_fields(result["fields"], task_id=task_id)),
        )
        return task_id, MedicalRecordFields.model_validate(approved["result_json"]["fields"])

    def _review_payload(self, task_id: int, fields: MedicalRecordFields) -> dict:
        edited = fields.model_copy(deep=True)
        edited.chief_complaint = edited.chief_complaint.model_copy(
            update={
                "value": "atomic transaction edited complaint",
                "missing": False,
                "status": "partial",
                "missing_elements": ["duration"],
            }
        )
        return review_payload_for_fields(task_id, edited)

    def _review_request(self, task_id: int, fields: MedicalRecordFields) -> ReviewRequest:
        return ReviewRequest(**self._review_payload(task_id, fields))

    def _snapshot(self, task_id: int) -> dict:
        task = get_task(task_id)
        assert task is not None
        payload = json.loads(task["result_json"])
        active_approval = get_active_approval_for_task(task_id)
        return {
            "task_status": task["status"],
            "task_current_stage": task["current_stage"],
            "task_revision_id": task["current_record_revision_id"],
            "chief_complaint": payload["fields"]["chief_complaint"]["value"],
            "revision_ids": [row["id"] for row in list_record_revisions_for_task(task_id)],
            "approvals": [
                {
                    "id": row["id"],
                    "revision_id": row["revision_id"],
                    "status": row["status"],
                    "invalidated_at": row["invalidated_at"],
                    "invalidation_reason": row["invalidation_reason"],
                }
                for row in list_approvals_for_task(task_id)
            ],
            "active_approval_id": active_approval["id"] if active_approval else None,
            "audit_types": [row["event_type"] for row in get_audit_logs(task_id)],
        }

    def _assert_failed_review_rolls_back(self, patched_name: str) -> None:
        task_id, fields = self._approved_task()
        before = self._snapshot(task_id)
        with patch(f"app.db.sqlite.{patched_name}", side_effect=RuntimeError("injected failure")):
            with self.assertRaises(RuntimeError):
                review_task(task_id, self._review_request(task_id, fields))
        after = self._snapshot(task_id)
        self.assertEqual(after, before)

    def test_review_transaction_rolls_back_when_revision_insert_fails(self):
        self._assert_failed_review_rolls_back("_insert_record_revision_row")

    def test_review_transaction_rolls_back_when_task_update_fails(self):
        self._assert_failed_review_rolls_back("_update_task_result_revision_row")

    def test_review_transaction_rolls_back_when_approval_invalidation_fails(self):
        self._assert_failed_review_rolls_back("_invalidate_active_approvals")

    def test_review_transaction_rolls_back_when_audit_insert_fails(self):
        self._assert_failed_review_rolls_back("_insert_audit_log_row")

    def test_review_transaction_success_creates_one_revision_and_blocks_stale_export(self):
        task_id, fields = self._approved_task()
        before = self._snapshot(task_id)

        reviewed = review_task(task_id, self._review_request(task_id, fields))
        after = self._snapshot(task_id)

        self.assertEqual(reviewed["current_stage"], "waiting_doctor_review")
        self.assertEqual(after["task_current_stage"], "waiting_doctor_review")
        self.assertEqual(after["task_status"], "WAITING_DOCTOR_REVIEW")
        self.assertEqual(len(after["revision_ids"]), len(before["revision_ids"]) + 1)
        self.assertNotEqual(after["task_revision_id"], before["task_revision_id"])
        self.assertEqual(len(after["approvals"]), len(before["approvals"]))
        self.assertIsNone(after["active_approval_id"])
        self.assertEqual(after["approvals"][0]["status"], "invalidated")
        self.assertEqual(after["chief_complaint"], "atomic transaction edited complaint")
        self.assertIn("doctor_review_saved", after["audit_types"])

        with self.assertRaises(HTTPException) as blocked:
            export_task(task_id)
        self.assertEqual(blocked.exception.status_code, 400)

    def test_review_revision_preserves_field_evidence_and_knowledge_references_after_reload(self):
        task_id, fields = self._approved_task()
        evidence_span = SourceSpan(
            text="patient has fever for three days",
            segment_id="seg-patient-001",
            index=1,
            start_time=12.3,
            end_time=14.7,
        )
        fields.chief_complaint = fields.chief_complaint.model_copy(
            update={"source_spans": [evidence_span]}
        )
        fields.candidate_diagnoses = [
            CandidateDiagnosis(
                name="fever syndrome under review",
                evidence=[evidence_span],
                reason="Patient fever evidence requires doctor confirmation.",
                references=[
                    ClinicalReference(
                        reference_id="NHC_TEST_GUIDELINE_2025",
                        title="Synthetic guideline reference for revision test",
                        organization="Synthetic test publisher",
                        source_type="national_guideline",
                        version="2025-test",
                        published_at="2025-01-01",
                        url="https://example.invalid/guideline",
                        evidence_scope="Test-only traceability fixture.",
                        verification_status="source_verified",
                        clinical_review_status="needs_medical_review",
                        retrieved_at="2026-09-22",
                    )
                ],
            )
        ]

        seeded_result = json.loads(get_task(task_id)["result_json"])
        seeded_result["fields"] = fields.model_dump(mode="json")
        seeded_revision = create_record_revision_for_task(
            task_id,
            seeded_result,
            source="evidence_lineage_spike",
            workflow_status="pending_review",
        )

        edited = MedicalRecordFields.model_validate(seeded_result["fields"])
        edited.present_illness = edited.present_illness.model_copy(
            update={
                "value": "Patient fever history reviewed; evolution remains to be completed.",
                "missing": False,
                "status": "partial",
                "missing_elements": ["symptom evolution"],
            }
        )
        review_task(task_id, self._review_request(task_id, edited))

        task_after = get_task(task_id)
        assert task_after is not None
        reviewed_revision = get_record_revision(int(task_after["current_record_revision_id"]))
        assert reviewed_revision is not None
        before = json.loads(seeded_revision["result_json"])
        after = json.loads(reviewed_revision["result_json"])
        revisions = list_record_revisions_for_task(task_id)

        self.assertEqual(reviewed_revision["encounter_id"], seeded_revision["encounter_id"])
        self.assertEqual(reviewed_revision["task_id"], seeded_revision["task_id"])
        self.assertEqual(reviewed_revision["revision_no"], seeded_revision["revision_no"] + 1)
        self.assertEqual([row["revision_no"] for row in revisions], list(range(1, len(revisions) + 1)))
        self.assertNotEqual(
            before["fields"]["present_illness"]["value"],
            after["fields"]["present_illness"]["value"],
        )
        self.assertEqual(
            after["fields"]["chief_complaint"]["source_spans"],
            before["fields"]["chief_complaint"]["source_spans"],
        )
        self.assertEqual(
            after["fields"]["candidate_diagnoses"][0]["evidence"],
            before["fields"]["candidate_diagnoses"][0]["evidence"],
        )
        self.assertEqual(
            after["fields"]["candidate_diagnoses"][0]["references"],
            before["fields"]["candidate_diagnoses"][0]["references"],
        )
        persisted_span = after["fields"]["chief_complaint"]["source_spans"][0]
        self.assertEqual(persisted_span["segment_id"], "seg-patient-001")
        self.assertEqual(persisted_span["start_time"], 12.3)
        self.assertEqual(persisted_span["end_time"], 14.7)

    def test_review_rejects_stale_revision_id(self):
        task_id, fields = self._approved_task()
        payload = self._review_payload(task_id, fields)
        payload["expected_revision_id"] = int(payload["expected_revision_id"]) - 1
        before = self._snapshot(task_id)

        with self.assertRaises(HTTPException) as stale:
            review_task(task_id, ReviewRequest(**payload))

        self.assertEqual(stale.exception.status_code, 409)
        self.assertEqual(stale.exception.detail["error_code"], "stale_record_revision")
        self.assertEqual(self._snapshot(task_id), before)

    def test_review_rejects_stale_content_hash(self):
        task_id, fields = self._approved_task()
        payload = self._review_payload(task_id, fields)
        payload["expected_content_hash"] = "0" * 64
        before = self._snapshot(task_id)

        with self.assertRaises(HTTPException) as stale:
            review_task(task_id, ReviewRequest(**payload))

        self.assertEqual(stale.exception.status_code, 409)
        self.assertEqual(stale.exception.detail["error_code"], "stale_record_revision")
        self.assertEqual(self._snapshot(task_id), before)

    def test_stale_review_creates_no_revision(self):
        task_id, fields = self._approved_task()
        payload = self._review_payload(task_id, fields)
        payload["expected_content_hash"] = "stale"
        before = self._snapshot(task_id)

        with self.assertRaises(HTTPException):
            review_task(task_id, ReviewRequest(**payload))

        after = self._snapshot(task_id)
        self.assertEqual(after["revision_ids"], before["revision_ids"])

    def test_stale_review_does_not_invalidate_current_approval(self):
        task_id, fields = self._approved_task()
        payload = self._review_payload(task_id, fields)
        payload["expected_revision_id"] = 0
        before = self._snapshot(task_id)

        with self.assertRaises(HTTPException):
            review_task(task_id, ReviewRequest(**payload))

        after = self._snapshot(task_id)
        self.assertEqual(after["active_approval_id"], before["active_approval_id"])
        self.assertEqual(after["approvals"], before["approvals"])

    def test_stale_review_does_not_change_task_or_encounter(self):
        task_id, fields = self._approved_task()
        payload = self._review_payload(task_id, fields)
        payload["expected_content_hash"] = "stale"
        before = self._snapshot(task_id)

        with self.assertRaises(HTTPException):
            review_task(task_id, ReviewRequest(**payload))

        after = self._snapshot(task_id)
        self.assertEqual(after["task_revision_id"], before["task_revision_id"])
        self.assertEqual(after["task_current_stage"], before["task_current_stage"])
        self.assertEqual(after["task_status"], before["task_status"])
        self.assertEqual(after["chief_complaint"], before["chief_complaint"])

    def test_retry_with_latest_revision_succeeds(self):
        task_id, fields = self._approved_task()
        stale_payload = self._review_payload(task_id, fields)
        stale_payload["expected_content_hash"] = "stale"

        with self.assertRaises(HTTPException):
            review_task(task_id, ReviewRequest(**stale_payload))

        reviewed = review_task(task_id, self._review_request(task_id, fields))
        self.assertEqual(reviewed["current_stage"], "waiting_doctor_review")
        self.assertEqual(self._snapshot(task_id)["chief_complaint"], "atomic transaction edited complaint")

    def test_concurrent_reviews_only_one_succeeds(self):
        result = MedicalRecordOrchestrator().run_from_text("patient has fever for three days")
        task_id = int(result["task_id"])
        fields = result["fields"]
        payload = self._review_payload(task_id, fields)

        def submit(value: str):
            local_payload = deepcopy(payload)
            local_payload["fields"]["chief_complaint"]["value"] = value
            try:
                review_task(task_id, ReviewRequest(**local_payload))
                return {"status_code": 200, "detail": None}
            except HTTPException as exc:
                return {"status_code": exc.status_code, "detail": exc.detail}

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(submit, ["concurrent first", "concurrent second"]))

        statuses = sorted(response["status_code"] for response in responses)
        self.assertEqual(statuses, [200, 409])
        stale = next(response for response in responses if response["status_code"] == 409)
        self.assertEqual(stale["detail"]["error_code"], "stale_record_revision")
        revisions = list_record_revisions_for_task(task_id)
        self.assertEqual(len(revisions), 2)
        final_value = json.loads(get_task(task_id)["result_json"])["fields"]["chief_complaint"]["value"]
        self.assertIn(final_value, {"concurrent first", "concurrent second"})


if __name__ == "__main__":
    unittest.main()
