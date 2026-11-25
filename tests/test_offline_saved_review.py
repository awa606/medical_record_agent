"""A saved doctor's revision renders locally and retains its grounding policy."""
from pathlib import Path

import pytest

from app.api.tasks import _requires_strict_review
from app.db import get_record_revision, list_export_events_for_task
from app.services.llm import LLMRecordGenerator
from tests.approval_helpers import approval_payload_for_fields
from tests.test_clinician_assessment import doctor_case, review_payload, signed_pdf


def test_local_revision_preserves_signed_pdf_and_extraction_when_generation_is_unavailable(doctor_case, monkeypatch):
    client, task_id, _ = doctor_case
    task = f"/api/tasks/{task_id}"
    original = client.get(task).json()["result_json"]["llm_trace"]
    receipt, old_pdf, _ = signed_pdf(client, task_id)
    payload = review_payload(client, task_id)
    signed_revision = dict(get_record_revision(payload["expected_revision_id"]))
    original_export = dict(list_export_events_for_task(task_id)[0])
    payload["fields"]["auxiliary_exam"].update(value="当次资料待回。", missing=False, status="partial")

    # The case already has an R1 and a signed file. No provider is valid for
    # new records under this edge configuration.
    monkeypatch.setenv("RECORD_PROVIDER_MODE", " EdGe ")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    generated = client.post("/api/records/generate", json={"conversation_text": "本次前来核对记录。"})
    assert generated.status_code == 503
    monkeypatch.setattr(LLMRecordGenerator, "__init__", lambda *a, **kw: pytest.fail("unexpected model construction"))
    response = client.post(task + "/review", json=payload)
    assert response.status_code == 200, response.text
    revised = response.json()["result_json"]
    assert revised["fields"]["auxiliary_exam"]["value"] == "当次资料待回。"
    trace = revised["llm_trace"]
    assert all(trace[key] == value for key, value in original.items())
    assert trace["review_components"]["actual_provider"] == "local_rules"
    assert trace["review_components"]["strict_grounding"] is True
    assert dict(get_record_revision(payload["expected_revision_id"])) == signed_revision
    assert Path(receipt["pdf_path"]).read_bytes() == old_pdf
    assert original_export in [dict(event) for event in list_export_events_for_task(task_id)]
    assert client.get(task + "/export-readiness").json()["ready"] is False


def test_invalid_mode_retains_saved_record_and_checked_citation_still_blocks_approval(doctor_case, monkeypatch):
    client, task_id, _ = doctor_case
    task = f"/api/tasks/{task_id}"
    payload = review_payload(client, task_id)
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "unsupported")
    rejected = client.post(task + "/review", json=payload)
    assert rejected.status_code == 503
    assert review_payload(client, task_id) == payload

    monkeypatch.setenv("RECORD_PROVIDER_MODE", "LIVE")
    payload["fields"]["chief_complaint"].update(value="前来核对资料。", source_spans=[{"text": "以前来取过资料", "index": 0}])
    payload["source_corrected_fields"] = ["chief_complaint"]
    revised = client.post(task + "/review", json=payload)
    assert revised.status_code == 200, revised.text
    result = revised.json()["result_json"]
    assert result["fields"]["chief_complaint"]["status"] == "conflicting"
    assert result["safety_check"]["blocked"] is True
    approval = client.post(task + "/approve", json=approval_payload_for_fields(result["fields"], task_id=task_id))
    assert approval.status_code == 409
    assert client.post(task + "/export").status_code == 400


@pytest.mark.parametrize("mode,stored,strict", [
    ("DeMo", {}, False),
    ("demo", {"mode": "edge", "review_components": "unknown-legacy-shape"}, True),
    ("demo", {"mode": "demo"}, False),
    ("edge", {}, True),
    ("demo", {"mode": "Edge"}, True),
    ("demo", {"mode": "live", "review_components": {"mode": "demo"}}, True),
    ("demo", {"review_components": {"mode": "edge"}}, True),
    ("demo", {"mode": "demo", "review_components": {"strict_grounding": True}}, True),
    ("demo", {"mode": "unrecognized-historical-mode"}, True),
])
def test_saved_mode_never_weakens_evidence_checks(monkeypatch, mode, stored, strict):
    monkeypatch.setenv("RECORD_PROVIDER_MODE", mode)
    assert _requires_strict_review(stored) is strict
