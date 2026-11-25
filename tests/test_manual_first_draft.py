from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.db import sqlite as store
from app.main import app
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields
from tests.auth_helpers import create_user, login_as_admin, login_as_user


@pytest.fixture
def failed_visit(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "visit.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "pdf"))
    monkeypatch.setenv("MRA_IDENTITY_MAP_PATH", str(tmp_path / "identities.sqlite3"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "demo")
    source = "患者：我来咨询上次报告。"

    def failed_extraction(task_id, text):
        store.update_task(
            task_id,
            status="FAILED",
            current_stage="failed",
            error_message="LLM_NO_SUPPORTED_FACTS: no usable structured data",
            result_json=json.dumps({"conversation_text": text, "fields": None, "draft": None}),
        )

    monkeypatch.setattr("app.api.records.run_record_generation_task", failed_extraction)
    with TestClient(app) as client:
        owner = create_user(client, username="first-draft-owner", display_name="合成执笔医生")
        other = create_user(client, username="first-draft-other", display_name="合成其他医生")
        login_as_user(client, username=owner["username"])
        encounter = client.post(
            "/api/encounters", json={"patient_deidentified_id": "SIM-MANUAL-FIRST"}
        ).json()["id"]
        ep = f"/api/encounters/{encounter}"
        for action in ("check-in", "start"):
            assert client.post(ep + "/" + action, json={}).is_success
        generated = client.post(
            "/api/records/generate", json={"encounter_id": encounter, "conversation_text": source}
        )
        assert generated.is_success
        yield client, ep, generated.json()["task_id"], owner, other


def test_first_save_permissions_idempotency_and_concurrency(failed_visit):
    client, ep, failed, owner, other = failed_visit
    dest = ep + "/manual-first-draft"
    body = {"failed_task_id": failed, "request_id": str(uuid4()), "chief_complaint": "咨询旧报告"}
    original = store.get_task(failed)
    assert client.get(ep).json()["task"]["manual_first_draft_available"]
    assert client.get(f"/api/tasks/{failed}").json()["manual_first_draft_available"]
    for changes in (
        {"chief_complaint": "  "},
        {"present_illness": "甲" * 4001},
        {"recorded_by": other["id"]},
    ):
        assert client.post(dest, json={**body, **changes}).status_code == 422
    login_as_admin(client)
    assert not client.get(ep).json()["task"]["manual_first_draft_available"]
    assert client.post(dest, json=body).status_code == 403
    login_as_user(client, username=other["username"])
    assert client.post(dest, json=body).status_code == 403
    login_as_user(client, username=owner["username"])
    with TestClient(app) as second:
        login_as_user(second, username=owner["username"])
        another = {**body, "request_id": str(uuid4()), "chief_complaint": "核对旧报告"}
        with ThreadPoolExecutor(2) as pool:
            futures = [
                pool.submit(session.post, dest, json=payload)
                for session, payload in ((client, body), (second, another))
            ]
            results = [f.result() for f in futures]
    assert sorted(r.status_code for r in results) == [201, 409]
    winner = next(i for i, r in enumerate(results) if r.status_code == 201)
    saved = results[winner].json()
    submitted = [body, another][winner]
    replay = client.post(dest, json=submitted)
    assert replay.status_code == 200 and replay.json() == saved
    assert client.post(dest, json={**submitted, "chief_complaint": "新文字"}).status_code == 409
    assert client.get(f"/api/tasks/{failed}").status_code == 403
    assert store.get_task(failed) == original
    assert len(client.get(ep).json()["revisions"]) == 1
    assert not client.get(ep).json()["task"]["manual_first_draft_available"]
    assert client.get(ep).json()["task"]["manual_first_draft_request_id"] == submitted["request_id"]
    assert (
        client.get(f"/api/tasks/{saved['task_id']}").json()["manual_first_draft_request_id"]
        == submitted["request_id"]
    )
    result = client.get(f"/api/tasks/{saved['task_id']}").json()["result_json"]
    assert result["fields"]["chief_complaint"]["value"] == submitted["chief_complaint"]
    assert not result["fields"]["chief_complaint"]["source_spans"]
    assert result["fields"]["candidate_diagnoses"] == []
    assert result["conversation_text"] == original["input_text"]
    assert result["clinician_draft_origin"] == saved["clinician_draft_origin"]
    login_as_admin(client)
    assert "manual_first_draft_request_id" not in client.get(ep).json()["task"]


def test_manual_history_offline_signatures_and_protocol(failed_visit, monkeypatch):
    client, ep, failed, owner, _other = failed_visit
    dest = ep + "/manual-first-draft"

    def model_is_down(*args, **kwargs):
        pytest.fail("handwritten records must be editable when the generator is unavailable")

    monkeypatch.setattr("app.services.llm.LLMRecordGenerator.__init__", model_is_down)
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "edge")
    body = {"failed_task_id": failed, "request_id": str(uuid4()), "present_illness": "今天来咨询既往报告。"}
    response = client.post(dest, json=body)
    assert response.status_code == 201, response.text
    receipt = response.json()
    origin = receipt["clinician_draft_origin"]
    assert (
        origin["recorded_by"],
        origin["recorded_by_name"],
        origin["previous_failed_task_id"],
        origin["failure_category"],
    ) == (owner["id"], owner["display_name"], failed, "no_supported_facts")
    task_id = receipt["task_id"]
    task = f"/api/tasks/{task_id}"
    assert not client.get(task + "/export-readiness").json()["ready"]
    digests = []
    for number in range(1, 4):
        result = client.get(task).json()["result_json"]
        if number > 1:
            fields = result["fields"]
            fields["previous_treatment"].update(
                value=f"医生补录第{number}次沟通。", missing=False, status="complete"
            )
            payload = review_payload_for_fields(task_id, fields)
            payload["manual_takeover_fields"] = ["previous_treatment"]
            assert (
                client.post(task + "/review", json={**payload, "clinician_draft_origin": None}).status_code
                == 422
            )
            revised = client.post(task + "/review", json=payload)
            assert revised.is_success, revised.text
            result = revised.json()["result_json"]
        assert result["clinician_draft_origin"] == origin and "首稿执笔" in result["draft"]
        quality = result["quality_report"]
        section = next(item for item in quality["field_quality"] if item["key"] == "present_illness")
        assert section["evidence_count"] == 0 and "由医生书写" in section["reason"]
        assert "现病史" not in quality["evidence_missing_fields"]
        for f in ("present_illness", "previous_treatment"):
            assert result["fields"][f]["source_spans"] == []
        fields = result["fields"]
        checks = approval_payload_for_fields(fields, task_id=task_id)
        for item in checks["fields"]:
            if fields[item["key"]]["value"]:
                item["action"] = "confirm_content"
        signed = client.post(task + "/approve", json=checks)
        assert signed.is_success, signed.text
        ready = client.get(task + "/export-readiness").json()
        exported = client.post(
            task + "/export",
            params={
                "expected_revision_id": ready["revision_id"],
                "expected_approval_id": ready["approval_id"],
            },
        )
        assert exported.is_success, exported.text
        digest = exported.json()["exports"]["pdf_sha256"]
        downloaded = client.get(task + "/exports/pdf", params={"sha256": digest})
        assert downloaded.is_success and sha256(downloaded.content).hexdigest() == digest
        with pymupdf.open(stream=downloaded.content, filetype="pdf") as pages:
            text = "".join("".join(p.get_text().split()) for p in pages)
        assert f"首稿执笔：{owner['display_name']}" in text and f"原生成任务T{failed}" in text
        assert "未找到可用病历信息" in text and "AI辅助生成" not in text
        approval = client.get(task).json()["result_json"]["approval"]
        assert (
            f"本版软件分项审核人：{owner['display_name']}（账号{owner['id']}）" in text
            and "医师签名：" in text
        )
        for label, stamp in (("手录时间", origin["recorded_at"]), ("审核时间", approval["created_at"])):
            expected = (
                datetime.fromisoformat(stamp)
                .astimezone(timezone(timedelta(hours=8)))
                .strftime("%Y-%m-%d%H:%MUTC+08:00")
            )
            assert f"{label}：{expected}" in text
        assert "AI候选诊断必须" not in text and origin["recorded_at"] not in text
        digests.append(digest)
    assert len(set(digests)) == 3
    assert client.post(dest, json=body).json() == receipt
    with closing(store.get_connection()) as conn:
        assert conn.execute("SELECT min_writer_protocol FROM encounter").fetchone()[0] == 3
        for table in ("record_revision", "approval", "export_event"):
            assert [r[0] for r in conn.execute(f"SELECT writer_protocol FROM {table}")] == [3] * 3
        assert all(
            json.loads(r[0])["clinician_draft_origin"] == origin
            for r in conn.execute("SELECT result_json FROM record_revision")
        )


@pytest.mark.parametrize("table", ["clinician_first_draft_request", "audit_log"])
def test_interrupted_first_write_rolls_back_and_same_request_recovers(failed_visit, table):
    _client, ep, failed, owner, _other = failed_visit
    dest = ep + "/manual-first-draft"
    body = {"failed_task_id": failed, "request_id": str(uuid4()), "chief_complaint": "咨询办理流程。"}
    original = store.get_task(failed)
    with TestClient(app, raise_server_exceptions=False) as browser:
        login_as_user(browser, username=owner["username"])
        with closing(store.get_connection()) as conn, conn:
            conn.execute(f"""CREATE TRIGGER interrupt_first_draft BEFORE INSERT ON {table}
                            BEGIN SELECT RAISE(ABORT, 'synthetic interrupted write'); END""")
        interrupted = browser.post(dest, json=body)
        assert interrupted.status_code == 500
        with closing(store.get_connection()) as conn, conn:
            assert conn.execute(
                "SELECT task_id,current_revision_id,min_writer_protocol FROM encounter"
            ).fetchone()[:] == (failed, None, 1)
            for name in ("record_revision", "clinician_first_draft_request", "approval", "export_event"):
                assert conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM agent_task").fetchone()[0] == 1
            conn.execute("DROP TRIGGER interrupt_first_draft")
        assert store.get_task(failed) == original
        saved = browser.post(dest, json=body)
        repeated = browser.post(dest, json=body)
        assert (saved.status_code, repeated.status_code) == (201, 200)
        assert saved.json() == repeated.json()
        assert len(browser.get(ep).json()["revisions"]) == 1


def test_failed_audio_requires_review_for_source_citations(failed_visit):
    client, ep, failed, _owner, _other = failed_visit
    # Pre-existing audio snapshot: an automatic quality pass is distinct from a doctor's review.
    text = "我来咨询上次报告。"
    asr = {
        "audio_id": "synth-audio",
        "engine": "mock",
        "segments": [{"segment_id": "s0", "text": text, "role": "患者"}],
        "role_quality": {"status": "passed"},
        "reviewed_by_doctor": False,
    }
    store.update_task(failed, result_json=json.dumps({"conversation_text": text, "asr_source": asr}))
    saved = client.post(
        ep + "/manual-first-draft",
        json={"failed_task_id": failed, "request_id": str(uuid4()), "chief_complaint": "就诊办理。"},
    )
    assert saved.status_code == 201
    task = saved.json()["task_id"]
    tp = f"/api/tasks/{task}"
    fields = client.get(tp).json()["result_json"]["fields"]
    fields["chief_complaint"].update(
        value=text, source_spans=[{"text": text, "segment_id": "s0", "index": 0}]
    )
    body = review_payload_for_fields(task, fields)
    assert (
        client.post(tp + "/review", json={**body, "source_corrected_fields": ["chief_complaint"]}).status_code
        == 409
    )
    typed = client.post(tp + "/review", json=body)
    assert typed.is_success, typed.text
    assert typed.json()["result_json"]["fields"]["chief_complaint"]["source_spans"] == []
