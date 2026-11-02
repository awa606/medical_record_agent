"""Signed files remain attributable to a particular revision and approval."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.api import tasks as task_routes
from app.db import get_connection, list_export_events_for_task
from app.main import app
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields
from tests.auth_helpers import create_user, login_as_user


@pytest.fixture
def signed_case(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "isolated.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "demo")
    with TestClient(app) as client:
        create_user(client, username="export-doctor")
        login_as_user(client, username="export-doctor")
        generated = client.post("/api/records/generate", json={"conversation_text": "患者：我发热两天，伴咳嗽、咽痛。"})
        assert generated.status_code == 200, generated.text
        task_id = generated.json()["task_id"]
        approve(client, task_id)
        yield client, task_id, tmp_path / "outputs"


def approve(client, task_id):
    fields = client.get(f"/api/tasks/{task_id}").json()["result_json"]["fields"]
    payload = approval_payload_for_fields(fields, task_id=task_id)
    # Partial fields with content are confirmed together, not accepted as missing.
    payload["fields"] = [item for item in payload["fields"] if not fields[item["key"]].get("value")]
    response = client.post(f"/api/tasks/{task_id}/approve", json=payload)
    assert response.status_code == 200, response.text


def export(client, task_id):
    response = client.post(f"/api/tasks/{task_id}/export")
    assert response.status_code == 200, response.text
    return response.json()["exports"]


def test_old_pdf_survives_revised_code_and_repeated_exports(signed_case):
    client, task_id, _ = signed_case
    first = export(client, task_id)
    old_path = Path(first["pdf_path"])
    old_bytes = old_path.read_bytes()
    fields = client.get(f"/api/tasks/{task_id}").json()["result_json"]["fields"]
    old_code = fields["candidate_diagnoses"][0].get("icd10_code")
    new_code = "J06.9" if old_code != "J06.9" else "R50.9"
    fields["candidate_diagnoses"][0]["icd10_code"] = new_code
    reviewed = client.post(f"/api/tasks/{task_id}/review", json=review_payload_for_fields(task_id, fields))
    assert reviewed.status_code == 200, reviewed.text
    assert client.get(f"/api/tasks/{task_id}/exports/pdf").status_code == 409
    approve(client, task_id)
    second, third = export(client, task_id), export(client, task_id)
    assert client.get(f"/api/tasks/{task_id}/exports/pdf", params={"sha256": first["pdf_sha256"]}).status_code != 200
    assert len({receipt["pdf_path"] for receipt in [first, second, third]}) == 3
    assert all(Path(r["pdf_path"]).match("task_*_medical_record.*") for r in (first, second, third))
    events = list_export_events_for_task(task_id)
    assert events[0]["revision_id"] != events[1]["revision_id"] == events[2]["revision_id"]
    assert events[0]["approval_id"] != events[1]["approval_id"] == events[2]["approval_id"]
    for event, receipt in zip(events, [first, second, third], strict=True):
        assert json.loads(event["exports_json"]) == receipt
        assert hashlib.sha256(Path(receipt["pdf_path"]).read_bytes()).hexdigest() == receipt["pdf_sha256"]
    assert old_path.read_bytes() == old_bytes
    downloaded = client.get(f"/api/tasks/{task_id}/exports/pdf")
    assert downloaded.status_code == 200
    assert downloaded.content == Path(third["pdf_path"]).read_bytes()
    with pymupdf.open(stream=downloaded.content, filetype="pdf") as doc:
        text = "".join(p.get_text() for p in doc)
    assert fields["chief_complaint"]["value"] in text and new_code in text
    with pymupdf.open(stream=old_bytes, filetype="pdf") as doc:
        assert new_code not in "".join(p.get_text() for p in doc)


def test_tampered_pdf_does_not_download(signed_case):
    client, task_id, _ = signed_case
    receipt = export(client, task_id)
    Path(receipt["pdf_path"]).write_bytes(b"%PDF-changed")
    response = client.get(f"/api/tasks/{task_id}/exports/pdf")
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "export_integrity_mismatch"


def test_parallel_exports_use_separate_artifacts(signed_case, monkeypatch):
    client, task_id, _ = signed_case
    both_ready = Barrier(2)
    render = task_routes.export_record

    def simultaneous_render(*args, **kwargs):
        both_ready.wait(timeout=10)
        return render(*args, **kwargs)

    monkeypatch.setattr(task_routes, "export_record", simultaneous_render)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: export(client, task_id), range(2)))
    assert receipts[0]["pdf_path"] != receipts[1]["pdf_path"]
    events = list_export_events_for_task(task_id)
    assert len(events) == 2 and events[0]["approval_id"] == events[1]["approval_id"]
    latest = json.loads(events[-1]["exports_json"])
    assert hashlib.sha256(client.get(f"/api/tasks/{task_id}/exports/pdf").content).hexdigest() == latest["pdf_sha256"]
    assert len({r["pdf_sha256"] for r in receipts}) == 2
    for receipt in receipts:
        response = client.get(f"/api/tasks/{task_id}/exports/pdf", params={"sha256": receipt["pdf_sha256"]})
        assert response.status_code == 200, response.text
        assert response.content == Path(receipt["pdf_path"]).read_bytes()
        assert "_R1_" in response.headers["content-disposition"]
    for unknown in ("0" * 64, "invalid"):
        assert client.get(f"/api/tasks/{task_id}/exports/pdf", params={"sha256": unknown}).status_code != 200


def test_save_during_export_keeps_new_revision_and_removes_unregistered_file(signed_case, monkeypatch):
    client, task_id, output_dir = signed_case
    render = task_routes.export_record

    def save_after_render(*args, **kwargs):
        receipt = render(*args, **kwargs)
        fields = client.get(f"/api/tasks/{task_id}").json()["result_json"]["fields"]
        fields["candidate_diagnoses"][0]["icd10_code"] = "J06.9"
        reviewed = client.post(f"/api/tasks/{task_id}/review", json=review_payload_for_fields(task_id, fields))
        assert reviewed.status_code == 200, reviewed.text
        return receipt

    monkeypatch.setattr(task_routes, "export_record", save_after_render)
    blocked = client.post(f"/api/tasks/{task_id}/export")
    assert blocked.status_code == 409
    assert not list_export_events_for_task(task_id)
    assert not list(output_dir.glob("*.pdf"))
    latest = client.get(f"/api/tasks/{task_id}").json()
    assert latest["current_stage"] == "waiting_doctor_review"
    assert latest["result_json"]["fields"]["candidate_diagnoses"][0]["icd10_code"] == "J06.9"


def test_legacy_receipt_without_digest_can_still_download(signed_case, monkeypatch):
    client, task_id, output_dir = signed_case
    fields = client.get(f"/api/tasks/{task_id}").json()["result_json"]["fields"]
    fields["family_history"].update(value="家属有高血压史", status="complete", missing=False)
    review = client.post(f"/api/tasks/{task_id}/review", json=review_payload_for_fields(task_id, fields))
    assert review.status_code == 200, review.text
    # Simulate a real signed file from the former seven-field approval policy.
    with monkeypatch.context() as older:
        current_signoff = task_routes._signoff_fields
        older.setattr(task_routes, "_signoff_fields", lambda f: (i for i in current_signoff(f) if i[0] != "family_history"))
        approve(client, task_id)
        receipt = export(client, task_id)
    denied = client.post(f"/api/tasks/{task_id}/export")
    assert denied.status_code == 400 and "家族史" in denied.text
    legacy = output_dir / f"task_{task_id}_medical_record.pdf"
    Path(receipt["pdf_path"]).rename(legacy)
    with closing(get_connection()) as conn, conn:
        conn.execute("UPDATE export_event SET exports_json = ? WHERE task_id = ?",
                     (json.dumps({"pdf_path": str(legacy)}), task_id))
    pdf = client.get(f"/api/tasks/{task_id}/exports/pdf")
    assert pdf.status_code == 200 and pdf.content == legacy.read_bytes()
    assert "_R2_" in pdf.headers["content-disposition"]
    assert client.get(f"/api/tasks/{task_id}/exports/pdf", params={"sha256": receipt["pdf_sha256"]}).status_code != 200
