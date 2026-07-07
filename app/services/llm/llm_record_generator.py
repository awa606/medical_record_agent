from __future__ import annotations

import os
import time
from typing import Any

from pydantic import ValidationError

from app.schemas import MedicalRecordFields, SafetyCheckResult
from app.services.llm.base import LLMProvider
from app.services.llm.json_repair import parse_json_object
from app.services.llm.mock_provider import MockLLMProvider
from app.services.mock_llm import MockLLM


FIELD_KEYS = [
    "chief_complaint",
    "present_illness",
    "previous_treatment",
    "accompanying_symptoms",
    "past_history",
    "allergy_history",
    "physical_exam",
]
FIELD_ATTRS = ["value", "missing", "hint", "confidence", "source_spans"]
DIAGNOSIS_STATUS = "候选/待医生确认"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _safe_reason(exc: BaseException | str) -> str:
    reason = str(exc)
    return reason[:500] if reason else exc.__class__.__name__  # type: ignore[union-attr]


class LLMRecordGenerator:
    """LLM-backed field extraction with MockLLM fallback.

    Draft generation and safety checking deliberately stay on MockLLM in this
    first integration stage to keep the fever_01 demo deterministic.
    """

    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        mock_llm: MockLLM | None = None,
        requested_provider: str | None = None,
        requested_model: str | None = None,
        init_fallback_reason: str | None = None,
    ) -> None:
        self.provider = provider or MockLLMProvider()
        self.mock_llm = mock_llm or MockLLM()
        self.requested_provider = requested_provider or self.provider.name
        self.requested_model = requested_model or self.provider.model
        self.init_fallback_reason = init_fallback_reason
        self.timeout_seconds = _env_float("LLM_TIMEOUT_SECONDS", 30.0)
        self.max_retries = max(0, _env_int("LLM_MAX_RETRIES", 2))
        self.last_trace = self._default_trace()

    def extract_fields(self, conversation: str) -> MedicalRecordFields:
        if self.init_fallback_reason:
            return self._fallback_extract(conversation, self.init_fallback_reason)

        if self.provider.name == "mock":
            start = time.perf_counter()
            fields = self.mock_llm.extract_fields(conversation)
            self._set_trace(
                provider="mock",
                model=self.provider.model,
                latency_ms=int((time.perf_counter() - start) * 1000),
                fallback=False,
                fallback_reason=None,
                actual_provider="mock",
            )
            return fields

        start = time.perf_counter()
        last_error: BaseException | None = None
        for _attempt in range(1, self.max_retries + 2):
            try:
                response = self.provider.generate_fields_json(
                    conversation,
                    timeout_seconds=self.timeout_seconds,
                )
                fields = self._fields_from_response(response.content)
                self._set_trace(
                    provider=response.provider,
                    model=response.model,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    fallback=False,
                    fallback_reason=None,
                    actual_provider=response.provider,
                )
                return fields
            except Exception as exc:  # noqa: BLE001 - fallback is required for demo stability.
                last_error = exc

        return self._fallback_extract(
            conversation,
            f"{self.requested_provider} field extraction failed: {_safe_reason(last_error or 'unknown error')}",
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    def generate_draft(self, fields: MedicalRecordFields | dict) -> str:
        return self.mock_llm.generate_draft(fields)

    def safety_check(
        self,
        draft_text: str,
        fields: MedicalRecordFields | dict,
        *,
        allow_export: bool = False,
    ) -> SafetyCheckResult:
        return self.mock_llm.safety_check(draft_text, fields, allow_export=allow_export)

    def get_trace(self) -> dict[str, Any]:
        return dict(self.last_trace)

    def _fields_from_response(self, raw_text: str) -> MedicalRecordFields:
        data = parse_json_object(raw_text)
        fields_payload = data.get("fields") if isinstance(data.get("fields"), dict) else data
        if not isinstance(fields_payload, dict):
            raise ValueError("LLM response fields payload must be an object")
        normalized = self._normalize_fields_payload(fields_payload)
        try:
            return MedicalRecordFields.model_validate(normalized)
        except ValidationError as exc:
            raise ValueError(f"LLM fields JSON does not match MedicalRecordFields schema: {exc}") from exc

    def _normalize_fields_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        missing_keys = [
            key for key in [*FIELD_KEYS, "candidate_diagnoses"]
            if key not in payload
        ]
        if missing_keys:
            raise ValueError(f"LLM fields JSON missing required keys: {', '.join(missing_keys)}")

        normalized: dict[str, Any] = {"degraded": bool(payload.get("degraded", False))}
        for key in FIELD_KEYS:
            value = payload[key]
            if not isinstance(value, dict):
                raise ValueError(f"LLM field {key} must be an object")
            missing_attrs = [attr for attr in FIELD_ATTRS if attr not in value]
            if missing_attrs:
                raise ValueError(
                    f"LLM field {key} missing required attributes: {', '.join(missing_attrs)}"
                )
            normalized[key] = {
                "value": value.get("value"),
                "missing": bool(value.get("missing")),
                "hint": value.get("hint"),
                "confidence": value.get("confidence"),
                "source_spans": self._normalize_spans(value.get("source_spans")),
                "confirmed_by_doctor": bool(value.get("confirmed_by_doctor", False)),
            }

        diagnoses = payload["candidate_diagnoses"]
        if not isinstance(diagnoses, list):
            raise ValueError("LLM candidate_diagnoses must be a list")
        normalized["candidate_diagnoses"] = [
            self._normalize_diagnosis(item) for item in diagnoses
        ]
        return normalized

    def _normalize_spans(self, spans: Any) -> list[dict[str, Any]]:
        if spans is None:
            return []
        if not isinstance(spans, list):
            raise ValueError("source_spans must be a list")
        normalized = []
        for span in spans:
            if isinstance(span, str):
                normalized.append({"text": span, "index": None})
                continue
            if not isinstance(span, dict) or not isinstance(span.get("text"), str):
                raise ValueError("source_spans items must contain text")
            normalized.append(
                {
                    "text": span["text"],
                    "index": span.get("index"),
                    "start_time": span.get("start_time"),
                    "end_time": span.get("end_time"),
                }
            )
        return normalized

    def _normalize_diagnosis(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict) or not item.get("name"):
            raise ValueError("candidate diagnosis must contain name")
        status = str(item.get("status") or DIAGNOSIS_STATUS)
        if status in {"候选，待医生确认", "候选待医生确认", "candidate"}:
            status = DIAGNOSIS_STATUS
        return {
            "name": item["name"],
            "status": status,
            "evidence": self._normalize_spans(item.get("evidence", [])),
            "reason": item.get("reason"),
            "rule_id": item.get("rule_id"),
            "confidence": item.get("confidence"),
            "suggested_checks": self._normalize_string_list(item.get("suggested_checks")),
            "medication_notes": self._normalize_string_list(item.get("medication_notes")),
            "risk_warnings": self._normalize_string_list(item.get("risk_warnings")),
            "follow_up_questions": self._normalize_string_list(item.get("follow_up_questions")),
            "confirmed_by_doctor": bool(item.get("confirmed_by_doctor", False)),
        }

    def _normalize_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if not isinstance(value, list):
            raise ValueError("candidate diagnosis suggestion fields must be lists")
        return [str(item) for item in value if item]

    def _fallback_extract(
        self,
        conversation: str,
        fallback_reason: str,
        *,
        latency_ms: int | None = None,
    ) -> MedicalRecordFields:
        start = time.perf_counter()
        fields = self.mock_llm.extract_fields(conversation)
        fallback_latency = latency_ms
        if fallback_latency is None:
            fallback_latency = int((time.perf_counter() - start) * 1000)
        self._set_trace(
            provider=self.requested_provider,
            model=self.requested_model,
            latency_ms=fallback_latency,
            fallback=True,
            fallback_reason=fallback_reason,
            actual_provider="mock",
        )
        return fields

    def _default_trace(self) -> dict[str, Any]:
        return {
            "llm_provider": self.requested_provider,
            "model": self.requested_model,
            "latency_ms": None,
            "fallback": bool(self.init_fallback_reason),
            "fallback_reason": self.init_fallback_reason,
            "actual_provider": "mock" if self.init_fallback_reason else self.provider.name,
        }

    def _set_trace(
        self,
        *,
        provider: str,
        model: str,
        latency_ms: int,
        fallback: bool,
        fallback_reason: str | None,
        actual_provider: str,
    ) -> None:
        self.last_trace = {
            "llm_provider": provider,
            "model": model,
            "latency_ms": latency_ms,
            "fallback": fallback,
            "fallback_reason": fallback_reason,
            "actual_provider": actual_provider,
        }
