from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import closing
from copy import deepcopy

from fastapi.testclient import TestClient

from app.main import app
from app.db import (
    create_approval_for_task,
    create_record_revision_for_task,
    create_task,
    get_connection,
    set_task_owner,
    update_task,
)
from app.schemas import CandidateDiagnosis, ClinicalReference, MedicalField, MedicalRecordFields, SourceSpan
from tests.auth_helpers import create_user, login_as_admin, login_as_user


class EncountersApiTests(unittest.TestCase):
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
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "encounters.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(self.temp_dir.name, "outputs")

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_doctor_worklist_returns_owned_generated_encounter_and_restores_draft(self):
        client = TestClient(app)
        doctor = create_user(client, username="worklist-doctor")
        login_as_user(client, username="worklist-doctor")

        generated = client.post(
            "/api/records/generate",
            json={"conversation_text": "patient has fever for three days"},
        )
        self.assertEqual(generated.status_code, 200, generated.text)
        task_id = generated.json()["task_id"]

        worklist = client.get("/api/encounters?mine=true")
        self.assertEqual(worklist.status_code, 200, worklist.text)
        encounters = worklist.json()["encounters"]
        self.assertEqual(len(encounters), 1)
        self.assertEqual(encounters[0]["doctor_user_id"], doctor["id"])
        self.assertEqual(encounters[0]["task_id"], task_id)
        self.assertEqual(encounters[0]["status"], "pending_review")

        detail = client.get(f"/api/encounters/{encounters[0]['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        payload = detail.json()
        self.assertEqual(payload["task"]["id"], task_id)
        self.assertIn("fields", payload["task"]["result_json"])
        self.assertEqual(payload["current_revision"]["revision_no"], 1)
        self.assertEqual(len(payload["revisions"]), 1)

    def test_doctor_cannot_read_other_doctor_encounter_but_admin_can(self):
        client = TestClient(app)
        create_user(client, username="encounter-owner")
        create_user(client, username="encounter-other")
        login_as_user(client, username="encounter-owner")
        created = client.post(
            "/api/encounters",
            json={"patient_deidentified_id": "P-001", "patient_display_name": "模拟患者A"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        encounter_id = created.json()["id"]
        client.post("/api/auth/logout")

        login_as_user(client, username="encounter-other")
        forbidden = client.get(f"/api/encounters/{encounter_id}")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(client.get("/api/encounters?mine=true").json()["encounters"], [])
        client.post("/api/auth/logout")

        login_as_admin(client)
        admin_list = client.get("/api/encounters?mine=false")
        self.assertEqual(admin_list.status_code, 200)
        self.assertEqual(len(admin_list.json()["encounters"]), 1)
        admin_detail = client.get(f"/api/encounters/{encounter_id}")
        self.assertEqual(admin_detail.status_code, 200)

    def test_worklist_filters_by_status_and_deidentified_patient_query(self):
        client = TestClient(app)
        create_user(client, username="filter-doctor")
        login_as_user(client, username="filter-doctor")

        draft = client.post(
            "/api/encounters",
            json={"patient_deidentified_id": "P-FILTER-001", "patient_display_name": "Filter Patient"},
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        generated = client.post(
            "/api/records/generate",
            json={"conversation_text": "patient has fever for three days"},
        )
        self.assertEqual(generated.status_code, 200, generated.text)

        draft_only = client.get("/api/encounters?status=draft")
        self.assertEqual(draft_only.status_code, 200)
        self.assertEqual(
            [item["patient_deidentified_id"] for item in draft_only.json()["encounters"]],
            ["P-FILTER-001"],
        )

        searched = client.get("/api/encounters?q=FILTER")
        self.assertEqual(searched.status_code, 200)
        self.assertEqual(len(searched.json()["encounters"]), 1)
        self.assertEqual(searched.json()["encounters"][0]["status"], "draft")

    def _persist_history_fixture(self, owner_id):
        """Persist synthetic snapshots only; this fixture never calls a model."""
        span = {"text": "患者说发热两天", "index": 1, "segment_id": "history-patient-1",
                "start_time": 2.0, "end_time": 4.5}
        reference = ClinicalReference(
            reference_id="history-guide-v1", title="历史读取验收资料",
            organization="验收资料发布者", source_type="official_clinical_resource",
            version="test-v1", published_at="2026-01-01", url="https://example.invalid/history",
            evidence_scope="仅用于历史关联读取验收", retrieved_at="2026-10-20",
        ).model_dump(mode="json")
        fields = MedicalRecordFields(
            chief_complaint=MedicalField(value="发热两天", source_spans=[SourceSpan(**span)]),
            candidate_diagnoses=[CandidateDiagnosis(
                name="历史候选参考", evidence=[SourceSpan(**span)],
                references=[ClinicalReference(**reference)],
            )],
        )
        original = {
            "conversation_text": span["text"],
            "fields": fields.model_dump(mode="json"),
            "draft": "主诉：发热两天",
        }
        # An unrelated record makes global primary keys differ from version numbers.
        other_task = create_task("text", "WAITING_DOCTOR_REVIEW", input_text="另一次就诊")
        set_task_owner(other_task, owner_id)
        create_record_revision_for_task(other_task, original, actor_user_id=owner_id,
                                        source="generation", workflow_status="pending_review")
        task_id = create_task("text", "WAITING_DOCTOR_REVIEW", input_text=span["text"])
        set_task_owner(task_id, owner_id)
        update_task(task_id, result_json=json.dumps(original, ensure_ascii=False))
        before = create_record_revision_for_task(task_id, original, actor_user_id=owner_id,
                                                source="generation", workflow_status="pending_review")
        reviewed = deepcopy(original)
        reviewed["fields"]["chief_complaint"]["value"] = "发热2天"
        reviewed["fields"]["chief_complaint"]["confirmed_by_doctor"] = True
        reviewed["draft"] = "主诉：发热2天"
        after = create_record_revision_for_task(task_id, reviewed, actor_user_id=owner_id,
                                               source="doctor_review", workflow_status="waiting_review")
        update_task(task_id, result_json=json.dumps(reviewed, ensure_ascii=False))
        create_approval_for_task(task_id, actor_user_id=owner_id)
        return before["encounter_id"], before, after, span, reference

    def _business_snapshot(self):
        tables = ("patient", "encounter", "agent_task", "record_revision", "approval",
                  "approval_item", "export_event", "audit_log")
        with closing(get_connection()) as connection:
            return {table: [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")]
                    for table in tables}

    def test_history_contains_prior_fields_and_evidence_without_changing_current_approval(self):
        client = TestClient(app)
        doctor = create_user(client, username="history-owner")
        login_as_user(client, username="history-owner")
        encounter_id, old, current, span, reference = self._persist_history_fixture(doctor["id"])
        before = self._business_snapshot()

        first = client.get(f"/api/encounters/{encounter_id}")
        self.assertEqual(first.status_code, 200, first.text)
        detail = first.json()
        self.assertEqual(detail["current_revision_id"], current["id"])
        self.assertEqual(detail["current_revision"]["revision_no"], 2)
        self.assertEqual([row["revision_no"] for row in detail["revisions"]], [1, 2])
        self.assertEqual([row["id"] for row in detail["revisions"]], [old["id"], current["id"]])
        self.assertNotEqual(old["id"], old["revision_no"])
        prior, latest = detail["revisions"]
        self.assertEqual(json.loads(prior["fields_json"])["chief_complaint"]["value"], "发热两天")
        self.assertEqual(json.loads(latest["fields_json"])["chief_complaint"]["value"], "发热2天")
        self.assertEqual(prior["source"], "generation")
        self.assertEqual(latest["source"], "doctor_review")
        self.assertNotEqual(prior["content_hash"], latest["content_hash"])
        for row in detail["revisions"]:
            result = json.loads(row["result_json"])
            self.assertEqual(result["fields"]["chief_complaint"]["source_spans"], [span])
            self.assertEqual(result["fields"]["candidate_diagnoses"][0]["references"], [reference])
            self.assertEqual(row["created_by_user_id"], doctor["id"])
        second = client.get(f"/api/encounters/{encounter_id}")
        self.assertEqual(second.json(), detail)
        self.assertEqual(self._business_snapshot(), before)
        self.assertEqual(before["approval"][-1]["status"], "active")
        self.assertEqual(before["approval"][-1]["revision_id"], current["id"])

    def test_populated_history_is_denied_to_other_doctor_and_anonymous(self):
        client = TestClient(app)
        owner = create_user(client, username="history-author")
        create_user(client, username="history-stranger")
        login_as_user(client, username="history-author")
        encounter_id, _, current, _, _ = self._persist_history_fixture(owner["id"])
        client.post("/api/auth/logout")

        login_as_user(client, username="history-stranger")
        before = self._business_snapshot()
        forbidden = client.get(f"/api/encounters/{encounter_id}")
        self.assertEqual(forbidden.status_code, 403)
        self.assertNotIn("revisions", forbidden.json())
        self.assertNotIn("发热", forbidden.text)
        self.assertEqual(self._business_snapshot(), before)
        client.post("/api/auth/logout")

        before = self._business_snapshot()
        anonymous = client.get(f"/api/encounters/{encounter_id}")
        self.assertEqual(anonymous.status_code, 401)
        self.assertNotIn("revisions", anonymous.json())
        self.assertEqual(self._business_snapshot(), before)

        login_as_admin(client)
        before = self._business_snapshot()
        allowed = client.get(f"/api/encounters/{encounter_id}")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["current_revision_id"], current["id"])
        self.assertEqual(len(allowed.json()["revisions"]), 2)
        self.assertEqual(self._business_snapshot(), before)


if __name__ == "__main__":
    unittest.main()
