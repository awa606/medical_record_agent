import os
import tempfile
import unittest

from fastapi import BackgroundTasks

from app.agents import MedicalRecordOrchestrator
from app.api.records import GenerateRecordRequest, generate_record, run_record_generation_task
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
            conversation_text="左手手掌被咬了，大概两个小时左右，用酒精冲洗，牙龈出血。"
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


if __name__ == "__main__":
    unittest.main()
