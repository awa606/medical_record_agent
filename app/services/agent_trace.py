from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
AGENT_MODE = "Plan-and-Execute + Human-in-the-loop"
AUTONOMOUS_EXPORT_REASON = "doctor_review_required"

STEP_NAME_MAP = {
    "extract_fields": "FIELD_EXTRACTION",
    "generate_draft": "DRAFT_GENERATION",
    "safety_check": "SAFETY_CHECK",
}


def _decode_json(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _result_payload(task: dict[str, Any] | None) -> dict[str, Any]:
    if not task:
        return {}
    result = _decode_json(task.get("result_json"))
    return result if isinstance(result, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _medical_keywords(asr_result: dict[str, Any] | None) -> dict[str, list[Any]]:
    keywords = asr_result.get("medical_keywords") if asr_result else None
    if not isinstance(keywords, dict):
        return {"expected": [], "recognized": [], "missing": []}
    return {
        "expected": _safe_list(keywords.get("expected")),
        "recognized": _safe_list(keywords.get("recognized")),
        "missing": _safe_list(keywords.get("missing")),
    }


def _input_type(task: dict[str, Any] | None, asr_result: dict[str, Any] | None) -> str:
    if asr_result and asr_result.get("audio_id") not in (None, "", "text-import"):
        return "audio"
    return str((task or {}).get("input_type") or "text")


def _plan_for(input_type: str) -> list[str]:
    plan = ["FIELD_EXTRACTION", "DRAFT_GENERATION", "SAFETY_CHECK", "DOCTOR_REVIEW"]
    if input_type == "audio":
        return ["ASR_TRANSCRIBE", *plan]
    return ["TEXT_INPUT_NORMALIZE", *plan]


def _executed_steps(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    executed: list[dict[str, Any]] = []
    for step in steps or []:
        step_name = str(step.get("step_name") or "")
        output_snapshot = _decode_json(step.get("output_snapshot_json"))
        executed.append(
            {
                "step": STEP_NAME_MAP.get(step_name, step_name.upper() or "UNKNOWN_STEP"),
                "source_step": step_name,
                "status": step.get("status") or "UNKNOWN",
                "attempt_no": step.get("attempt_no"),
                "duration_ms": step.get("duration_ms"),
                "output_summary": _summary_for_output(output_snapshot),
            }
        )
    return executed


def _summary_for_output(output_snapshot: Any) -> dict[str, Any]:
    if isinstance(output_snapshot, dict):
        return {
            "type": "object",
            "keys": list(output_snapshot.keys())[:10],
        }
    if isinstance(output_snapshot, list):
        return {"type": "list", "count": len(output_snapshot)}
    if output_snapshot is None:
        return {"type": "none"}
    return {"type": type(output_snapshot).__name__}


def _perception(
    *,
    input_type: str,
    task: dict[str, Any] | None,
    asr_result: dict[str, Any] | None,
) -> dict[str, Any]:
    if input_type == "audio":
        return {
            "source": "audio_asr",
            "asr_engine": (asr_result or {}).get("engine"),
            "audio_id": (asr_result or {}).get("audio_id"),
            "role_strategy": (asr_result or {}).get("role_strategy"),
            "warnings": _safe_list((asr_result or {}).get("warnings")),
            "duration": (asr_result or {}).get("duration"),
            "segments_count": len(_safe_list((asr_result or {}).get("segments"))),
            "medical_keywords": _medical_keywords(asr_result),
        }

    input_text = str((task or {}).get("input_text") or "")
    return {
        "source": "text_input",
        "text_length": len(input_text),
        "warnings": [],
    }


def _decision(task: dict[str, Any] | None, safety_check: dict[str, Any]) -> dict[str, Any]:
    status = (task or {}).get("status") or "UNKNOWN"
    return {
        "next_state": status,
        "export_allowed": False,
        "reason": AUTONOMOUS_EXPORT_REASON,
        "human_in_the_loop_required": True,
        "doctor_review_required": True,
        "safety_passed": safety_check.get("passed"),
        "safety_blocked": safety_check.get("blocked"),
        "safety_errors": _safe_list(safety_check.get("errors")),
        "safety_warnings": _safe_list(safety_check.get("warnings")),
    }


def _llm_trace(result: dict[str, Any]) -> dict[str, Any]:
    trace = result.get("llm_trace") if isinstance(result.get("llm_trace"), dict) else {}
    return {
        "llm_provider": trace.get("llm_provider") or "mock",
        "model": trace.get("model") or "mock-deterministic-extractor",
        "latency_ms": trace.get("latency_ms"),
        "fallback": bool(trace.get("fallback", False)),
        "fallback_reason": trace.get("fallback_reason"),
        "actual_provider": trace.get("actual_provider") or trace.get("llm_provider") or "mock",
    }


def build_agent_trace(
    *,
    task: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None,
    asr_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _result_payload(task)
    safety_check = result.get("safety_check") if isinstance(result.get("safety_check"), dict) else {}
    input_type = _input_type(task, asr_result)

    return {
        "agent_mode": AGENT_MODE,
        "input_type": input_type,
        "perception": _perception(input_type=input_type, task=task, asr_result=asr_result),
        "llm": _llm_trace(result),
        "plan": _plan_for(input_type),
        "executed_steps": _executed_steps(steps),
        "decision": _decision(task, safety_check),
        "feedback": {
            "task_id": (task or {}).get("id"),
            "task_status": (task or {}).get("status"),
            "current_stage": (task or {}).get("current_stage"),
            "steps_count": len(steps or []),
        },
    }


def load_asr_result_for_audio(
    audio_id: str | None,
    *,
    upload_dir: Path | None = None,
) -> dict[str, Any] | None:
    if not audio_id:
        return None

    resolved_upload_dir = upload_dir or Path(
        os.environ.get("MEDICAL_RECORD_AGENT_UPLOAD_DIR", DEFAULT_UPLOAD_DIR),
    )
    path = resolved_upload_dir / f"{audio_id}.transcript.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None
