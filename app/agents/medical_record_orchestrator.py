from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, TypeVar

from app.db import (
    create_audit_log,
    create_task,
    create_task_step,
    finish_task_step,
    get_task,
    increment_task_retry_count,
    json_dumps,
    update_task,
)
from app.schemas import MedicalRecordFields, SafetyCheckResult
from app.services import create_llm_record_generator
from app.services.record_quality import build_record_quality_report


T = TypeVar("T")


class MedicalRecordOrchestrator:
    STATUS_CREATED = "CREATED"
    STATUS_PENDING = STATUS_CREATED
    STATUS_EXTRACTING_FIELDS = "EXTRACTING_FIELDS"
    STATUS_GENERATING_DRAFT = "GENERATING_DRAFT"
    STATUS_RUNNING_SAFETY_CHECK = "SAFETY_CHECKING"
    STATUS_WAITING_DOCTOR_REVIEW = "WAITING_DOCTOR_REVIEW"
    STATUS_COMPLETED = "DONE"
    STATUS_DEGRADED = "DEGRADED"
    STATUS_FAILED = "FAILED"

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm or create_llm_record_generator()
        self.status = self.STATUS_PENDING
        self.step_logs: list[dict[str, Any]] = []
        self.error_message: str | None = None
        self.fields: MedicalRecordFields | None = None
        self.draft: str | None = None
        self.safety_check: SafetyCheckResult | None = None
        self.quality_report: dict[str, Any] | None = None
        self.llm_trace: dict[str, Any] | None = None
        self.task_id: int | None = None
        self.conversation_text: str | None = None
        self.degraded = False
        self.degraded_messages: list[str] = []

    def create_text_task(self, conversation_text: str | None = None) -> int:
        self._reset()
        self.task_id = create_task(
            input_type="text",
            status=self.STATUS_CREATED,
            current_stage="created",
            input_text=conversation_text,
        )
        self.conversation_text = conversation_text
        self.status = self.STATUS_CREATED
        create_audit_log(
            self.task_id,
            "task_created",
            {"status": self.STATUS_CREATED, "input_type": "text"},
        )
        return self.task_id

    def run_from_text(self, conversation_text: str) -> dict[str, Any]:
        task_id = self.create_text_task(conversation_text)
        return self.run_existing_text_task(task_id, conversation_text)

    def run_existing_text_task(self, task_id: int, conversation_text: str) -> dict[str, Any]:
        self._reset()
        self.task_id = task_id
        self.conversation_text = conversation_text
        task = get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} does not exist")
        if not task.get("input_text"):
            update_task(task_id, input_text=conversation_text)
        self.status = task["status"]

        try:
            self.fields = self._run_llm_step(
                "extract_fields",
                self.STATUS_EXTRACTING_FIELDS,
                lambda: self.llm.extract_fields(conversation_text),
                self._degraded_fields,
                input_snapshot={"conversation_text": conversation_text},
            )
            self._capture_llm_trace()
            self._persist_result()

            self.draft = self._run_llm_step(
                "generate_draft",
                self.STATUS_GENERATING_DRAFT,
                lambda: self.llm.generate_draft(self.fields),
                lambda: self._rule_based_draft(self.fields),
                input_snapshot={"fields": self._snapshot(self.fields)},
            )
            self._capture_llm_trace()
            self._persist_result()

            self.safety_check = self._run_llm_step(
                "safety_check",
                self.STATUS_RUNNING_SAFETY_CHECK,
                lambda: self.llm.safety_check(self.draft, self.fields),
                self._degraded_safety_check,
                input_snapshot={
                    "draft": self.draft,
                    "fields": self._snapshot(self.fields),
                },
            )
            self._capture_llm_trace()
            self.quality_report = build_record_quality_report(
                self.fields,
                self.safety_check,
                draft=self.draft,
            )
            self._persist_result()

            self._set_status(self.STATUS_WAITING_DOCTOR_REVIEW, "doctor_review")
            self._persist_result()
            return self._result()
        except Exception as exc:
            self.error_message = str(exc)
            self._set_status(self.STATUS_FAILED, "failed")
            if self.task_id is not None:
                update_task(
                    self.task_id,
                    status=self.STATUS_FAILED,
                    current_stage="failed",
                    error_message=self.error_message,
                    result_json=json_dumps(self._result_payload()),
                )
            self._log_step("orchestrator", "failed", self.error_message)
            return self._result()

    def _reset(self) -> None:
        self.status = self.STATUS_PENDING
        self.step_logs = []
        self.error_message = None
        self.fields = None
        self.draft = None
        self.safety_check = None
        self.quality_report = None
        self.llm_trace = None
        self.task_id = None
        self.conversation_text = None
        self.degraded = False
        self.degraded_messages = []

    def _set_status(self, status: str, current_stage: str | None = None) -> None:
        previous_status = self.status
        self.status = status
        if self.task_id is not None:
            update_task(
                self.task_id,
                status=status,
                current_stage=current_stage,
            )
            create_audit_log(
                self.task_id,
                "status_changed",
                {
                    "previous_status": previous_status,
                    "status": status,
                    "current_stage": current_stage,
                },
            )

    def _run_step(self, step_name: str, status: str, operation: Callable[[], T]) -> T:
        self._set_status(status, step_name)
        self._log_step(step_name, "started")
        step_id = create_task_step(self._require_task_id(), step_name, "RUNNING")
        try:
            result = operation()
            finish_task_step(step_id, status="SUCCEEDED", output_snapshot=self._snapshot(result))
            self._log_step(step_name, "succeeded")
            return result
        except Exception as exc:
            error_message = str(exc)
            finish_task_step(step_id, status="FAILED", error_message=error_message)
            self._log_step(step_name, "failed", error_message)
            raise

    def _run_llm_step(
        self,
        step_name: str,
        status: str,
        operation: Callable[[], T],
        fallback: Callable[[], T],
        *,
        input_snapshot: Any | None = None,
    ) -> T:
        self._set_status(status, step_name)
        self._log_step(step_name, "started")

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            step_id = create_task_step(
                self._require_task_id(),
                step_name,
                "RUNNING",
                attempt_no=attempt,
                input_snapshot=input_snapshot,
            )
            try:
                result = operation()
                finish_task_step(
                    step_id,
                    status="SUCCEEDED",
                    output_snapshot=self._snapshot(result),
                )
                self._log_step(step_name, "succeeded")
                return result
            except Exception as exc:
                error_message = str(exc)
                retry_count = increment_task_retry_count(self._require_task_id())
                create_audit_log(
                    self._require_task_id(),
                    "llm_retry_failed",
                    {
                        "step": step_name,
                        "attempt": attempt,
                        "retry_count": retry_count,
                        "error": error_message,
                    },
                )
                if attempt < max_attempts:
                    finish_task_step(step_id, status="FAILED", error_message=error_message)
                    self._log_step(
                        step_name,
                        "retry_failed",
                        f"{step_name} attempt {attempt} failed: {error_message}",
                    )
                    continue

                self.degraded = True
                self.degraded_messages.append(f"{step_name} failed after retries: {error_message}")
                self._set_status(self.STATUS_DEGRADED, f"{step_name}_degraded")
                fallback_result = fallback()
                finish_task_step(
                    step_id,
                    status="DEGRADED",
                    error_message=error_message,
                    output_snapshot=self._snapshot(fallback_result),
                )
                self._log_step(step_name, "degraded", error_message)
                create_audit_log(
                    self._require_task_id(),
                    "degraded",
                    {"step": step_name, "error": error_message},
                )
                return fallback_result

        raise RuntimeError(f"{step_name} failed without returning a result")

    def _log_step(self, step: str, event: str, message: str | None = None) -> None:
        log: dict[str, Any] = {
            "step": step,
            "event": event,
            "task_status": self.status,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if message:
            log["message"] = message
        self.step_logs.append(log)

    def _capture_llm_trace(self) -> None:
        getter = getattr(self.llm, "get_trace", None)
        if not callable(getter):
            return
        trace = getter()
        if isinstance(trace, dict):
            self.llm_trace = trace

    def _require_task_id(self) -> int:
        if self.task_id is None:
            raise RuntimeError("task has not been created")
        return self.task_id

    def _persist_result(self) -> None:
        if self.task_id is None:
            return
        update_task(
            self.task_id,
            result_json=json_dumps(self._result_payload()),
        )

    def _degraded_fields(self) -> MedicalRecordFields:
        fields = MedicalRecordFields(degraded=True)
        for field in self._medical_fields(fields):
            field.hint = "降级生成，建议人工补充"
        return fields

    def _rule_based_draft(self, fields: MedicalRecordFields | None) -> str:
        record = fields or self._degraded_fields()
        record.degraded = True

        return "\n".join(
            [
                "门诊病历草稿（降级生成，建议人工填写）",
                f"主诉：{self._field_value(record.chief_complaint)}",
                f"现病史：{self._field_value(record.present_illness)}",
                f"既往处理：{self._field_value(record.previous_treatment)}",
                f"伴随症状：{self._field_value(record.accompanying_symptoms)}",
                f"既往史：{self._field_value(record.past_history)}",
                f"过敏史：{self._field_value(record.allergy_history)}",
                "查体：待医生查体补充",
                "候选诊断：未提及，待医生确认",
            ]
        )

    def _degraded_safety_check(self) -> SafetyCheckResult:
        return SafetyCheckResult(
            passed=False,
            blocked=True,
            errors=["安全校验失败，禁止导出。"],
            warnings=["当前任务已降级，建议医生人工核对所有字段。"],
        )

    def _field_value(self, field: Any) -> str:
        if field is None or field.missing:
            return "未提及，待补充"
        return field.value or "未提及，待补充"

    def _snapshot(self, value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if isinstance(value, list):
            return [self._snapshot(item) for item in value]
        if isinstance(value, dict):
            return {key: self._snapshot(item) for key, item in value.items()}
        return value

    def _medical_fields(self, fields: MedicalRecordFields) -> list[Any]:
        return [
            fields.chief_complaint,
            fields.present_illness,
            fields.previous_treatment,
            fields.accompanying_symptoms,
            fields.past_history,
            fields.allergy_history,
            fields.physical_exam,
        ]

    def _result_payload(self) -> dict[str, Any]:
        return {
            "conversation_text": self.conversation_text,
            "fields": self.fields.model_dump() if self.fields else None,
            "draft": self.draft,
            "safety_check": self.safety_check.model_dump() if self.safety_check else None,
            "quality_report": self.quality_report,
            "llm_trace": self.llm_trace,
            "step_logs": self.step_logs,
            "error_message": self.error_message,
            "degraded": self.degraded,
            "degraded_messages": self.degraded_messages,
        }

    def _result(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "fields": self.fields,
            "draft": self.draft,
            "safety_check": self.safety_check,
            "quality_report": self.quality_report,
            "llm_trace": self.llm_trace,
            "step_logs": self.step_logs,
            "error_message": self.error_message,
            "degraded": self.degraded,
            "degraded_messages": self.degraded_messages,
        }
