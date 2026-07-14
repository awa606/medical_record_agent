from __future__ import annotations

from typing import Any

from fastapi import APIRouter


router = APIRouter(tags=["capabilities"])


@router.get("/capabilities")
def read_capabilities() -> dict[str, Any]:
    """Return reusable service capabilities without exposing runtime secrets."""

    return {
        "project": "Medical Record Agent",
        "version": "v1.2",
        "stage": "coursework_productized_api",
        "reusable": True,
        "privacy_boundary": {
            "uses_real_patient_data": False,
            "returns_api_keys": False,
            "doctor_confirmation_required": True,
        },
        "capabilities": [
            {
                "name": "asr_session_streaming",
                "path": "/api/asr/sessions",
                "method": "POST/GET/PATCH",
                "requires_model_dependency": True,
                "purpose": "Upload audio, stream ASR events, and save role corrections.",
            },
            {
                "name": "record_field_extraction",
                "path": "/api/records/extract-fields",
                "method": "POST",
                "requires_model_dependency": False,
                "purpose": "Extract structured fields from consultation text without creating a task.",
            },
            {
                "name": "record_draft_builder",
                "path": "/api/records/build-draft",
                "method": "POST",
                "requires_model_dependency": False,
                "purpose": "Build a draft, safety check, and quality report from structured fields.",
            },
            {
                "name": "record_quality",
                "path": "/api/records/quality",
                "method": "POST",
                "requires_model_dependency": False,
                "purpose": "Evaluate field completeness, evidence coverage, and doctor-review readiness.",
            },
            {
                "name": "record_generation_task",
                "path": "/api/records/generate",
                "method": "POST",
                "requires_model_dependency": False,
                "purpose": "Create a full task for doctor review and export.",
            },
            {
                "name": "doctor_review_export",
                "path": "/api/tasks/{task_id}",
                "method": "GET/POST",
                "requires_model_dependency": False,
                "purpose": "Review, approve, check export readiness, and export generated records.",
            },
            {
                "name": "model_status",
                "path": "/api/llm/status",
                "method": "GET",
                "requires_model_dependency": False,
                "purpose": "Inspect configured LLM provider without returning secrets.",
            },
        ],
        "migration_notes": {
            "reusable_without_change": [
                "task workflow",
                "quality report shape",
                "review/export guardrail",
                "SSE event pattern",
            ],
            "replace_for_other_domains": [
                "field schema",
                "domain knowledge rules",
                "prompt templates",
                "frontend labels",
            ],
        },
    }
