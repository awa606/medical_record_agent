import os
import tempfile
import unittest

from app.agents import MedicalRecordOrchestrator
from app.db import get_audit_logs, get_task, get_task_steps


SNAKE_BITE_CONVERSATION = """
你好，哪里不舒服，你是哪里被咬了吗？我是左手手掌被咬了。现在什么感受？
感觉这里有点肿痛。大概被咬了多久了？大概咬了两个小时左右。你被咬了后做没做过什么处理，酒精冲洗了一下，有没有包扎伤口，
我这伤口这里绑了绷带，你有没有吃过什么药？吃的季德胜蛇药片。你是直接来我们医院还是去过其他医院？直接来咱们医院的。
现在除了咬伤部位不舒服，还有什么其他难受的？我现在有一些畏寒，还有一些头晕胸闷，严重的时候还有心慌，
然后我感觉我的牙龈也有一些出血。
"""


class BrokenLLM:
    def extract_fields(self, conversation_text):
        raise RuntimeError("extract failed")


class MedicalRecordOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(
            self.temp_dir.name,
            "test.sqlite3",
        )

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        self.temp_dir.cleanup()

    def test_run_from_text_completes_snake_bite_flow(self):
        orchestrator = MedicalRecordOrchestrator()

        result = orchestrator.run_from_text(SNAKE_BITE_CONVERSATION)

        self.assertIsInstance(result["task_id"], int)
        self.assertEqual(result["status"], MedicalRecordOrchestrator.STATUS_WAITING_DOCTOR_REVIEW)
        self.assertIsNone(result["error_message"])
        self.assertEqual(orchestrator.status, MedicalRecordOrchestrator.STATUS_WAITING_DOCTOR_REVIEW)

        fields = result["fields"]
        self.assertFalse(fields.chief_complaint.missing)
        self.assertIn("左手手掌", fields.chief_complaint.value)
        self.assertTrue(fields.allergy_history.missing)
        self.assertEqual(fields.allergy_history.hint, "建议补问")
        self.assertTrue(fields.physical_exam.missing)
        self.assertGreaterEqual(len(fields.candidate_diagnoses), 1)
        self.assertEqual(fields.candidate_diagnoses[0].status, "候选/待医生确认")
        self.assertFalse(fields.candidate_diagnoses[0].confirmed_by_doctor)

        draft = result["draft"]
        self.assertIn("门诊病历草稿", draft)
        self.assertIn("候选/待医生确认", draft)
        self.assertIn("查体：待医生查体补充", draft)

        safety_check = result["safety_check"]
        self.assertTrue(safety_check.passed)
        self.assertFalse(safety_check.blocked)

        quality = result["quality_report"]
        self.assertIsNotNone(quality)
        self.assertIn("core_completeness", quality)
        self.assertFalse(quality["export_allowed"])
        self.assertTrue(quality["doctor_confirmation_required"])
        self.assertIn("candidate_diagnosis_status", quality)
        self.assertIn("diagnosis_quality", quality["candidate_diagnosis_status"])
        self.assertIn("treatment_safety", quality)
        self.assertIn("status", quality["treatment_safety"])
        self.assertIn("next_actions", quality["treatment_safety"])

        logs = result["step_logs"]
        succeeded_steps = [log["step"] for log in logs if log["event"] == "succeeded"]
        self.assertEqual(
            succeeded_steps,
            ["extract_fields", "generate_draft", "safety_check"],
        )
        self.assertIn(
            MedicalRecordOrchestrator.STATUS_EXTRACTING_FIELDS,
            [log["task_status"] for log in logs],
        )
        self.assertIn(
            MedicalRecordOrchestrator.STATUS_GENERATING_DRAFT,
            [log["task_status"] for log in logs],
        )
        self.assertIn(
            MedicalRecordOrchestrator.STATUS_RUNNING_SAFETY_CHECK,
            [log["task_status"] for log in logs],
        )

        task = get_task(result["task_id"])
        self.assertEqual(task["status"], MedicalRecordOrchestrator.STATUS_WAITING_DOCTOR_REVIEW)
        self.assertEqual(task["input_type"], "text")
        self.assertEqual(task["input_text"], SNAKE_BITE_CONVERSATION)
        self.assertEqual(task["current_stage"], "doctor_review")
        self.assertEqual(task["retry_count"], 0)
        self.assertIsNotNone(task["completed_at"])
        self.assertIn("门诊病历草稿", task["result_json"])
        self.assertIn("quality_report", task["result_json"])

        steps = get_task_steps(result["task_id"])
        self.assertEqual(
            [step["step_name"] for step in steps],
            ["extract_fields", "generate_draft", "safety_check"],
        )
        self.assertEqual([step["status"] for step in steps], ["SUCCEEDED"] * 3)
        self.assertTrue(all(step["ended_at"] for step in steps))
        self.assertTrue(all(step["duration_ms"] is not None for step in steps))
        self.assertEqual([step["attempt_no"] for step in steps], [1, 1, 1])
        self.assertIn("左手手掌被咬", steps[0]["input_snapshot_json"])
        self.assertIn("chief_complaint", steps[0]["output_snapshot_json"])

        audit_logs = get_audit_logs(result["task_id"])
        self.assertIn("task_created", [log["event_type"] for log in audit_logs])
        self.assertIn("status_changed", [log["event_type"] for log in audit_logs])

    def test_run_from_text_degrades_when_llm_steps_raise(self):
        orchestrator = MedicalRecordOrchestrator(llm=BrokenLLM())

        result = orchestrator.run_from_text("任意问诊文本")

        self.assertEqual(result["status"], MedicalRecordOrchestrator.STATUS_WAITING_DOCTOR_REVIEW)
        self.assertTrue(result["degraded"])
        self.assertTrue(result["fields"].degraded)
        self.assertTrue(result["fields"].chief_complaint.missing)
        self.assertEqual(result["fields"].chief_complaint.hint, "降级生成，建议人工补充")
        self.assertIn("降级生成，建议人工填写", result["draft"])
        self.assertFalse(result["safety_check"].passed)
        self.assertTrue(result["safety_check"].blocked)
        self.assertEqual(result["quality_report"]["status"], "needs_review")

        task = get_task(result["task_id"])
        self.assertEqual(task["status"], MedicalRecordOrchestrator.STATUS_WAITING_DOCTOR_REVIEW)
        self.assertGreaterEqual(task["retry_count"], 3)
        self.assertIn("降级生成，建议人工补充", task["result_json"])

        steps = get_task_steps(result["task_id"])
        self.assertEqual(
            [step["step_name"] for step in steps],
            ["extract_fields"] * 3 + ["generate_draft"] * 3 + ["safety_check"] * 3,
        )
        self.assertEqual(
            [step["status"] for step in steps],
            ["FAILED", "FAILED", "DEGRADED"] * 3,
        )
        self.assertEqual(
            [step["attempt_no"] for step in steps],
            [1, 2, 3] * 3,
        )

        audit_logs = get_audit_logs(result["task_id"])
        self.assertIn("llm_retry_failed", [log["event_type"] for log in audit_logs])
        self.assertIn("degraded", [log["event_type"] for log in audit_logs])


if __name__ == "__main__":
    unittest.main()
