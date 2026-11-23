"""Doctor-owned revisions with multiple source selections, with no model or audio inference."""
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from app.agents import MedicalRecordOrchestrator
from app.db import get_record_revision, get_task, set_task_owner
from app.main import app
from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.field_grounding import ground_fields
from app.services.llm.llm_record_generator import LLMRecordGenerator
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields
from tests.auth_helpers import create_user, login_as_user
from tests.test_generation_failure_contract import ResponseProvider


SOURCE = "[患者] 否认胸痛。\n[患者] 发热两天。\n[患者] 发热两天。"
TURNS = [
    {"text": "否认胸痛", "segment_id": "p1", "role": "患者", "start_time": 0, "end_time": 2},
    {"text": "发热两天", "segment_id": "p2", "role": "患者", "start": 4, "end": 6},
    {"text": "发热两天", "segment_id": "p3", "role": "患者"},
]


@pytest.mark.parametrize("mode", ["demo", "edge"])
def test_doctor_review_persists_checked_spans_and_blocks_invalid_identity_and_timing(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "isolated.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP", "1")
    monkeypatch.delenv("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "demo")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    source_field = MedicalField(value="否认胸痛", source_spans=[SourceSpan(text="否认胸痛", index=0)])
    initial = MedicalRecordFields(chief_complaint=source_field, present_illness=source_field)
    generator = LLMRecordGenerator(provider=ResponseProvider(initial.model_dump(mode="json")),
                                   mode="edge", allow_mock_fallback=False)
    monkeypatch.setattr("app.api.tasks.create_llm_record_generator", lambda: generator)
    with TestClient(app) as client:
        owner = create_user(client, username="citation-doctor")
        login_as_user(client, username="citation-doctor")
        monkeypatch.setenv("RECORD_PROVIDER_MODE", mode)
        variants = [
            ("subrange", {"index": 1, "segment_id": "p2", "start_time": 4.5}, None),
            ("wrong_turn", {"index": 1, "segment_id": "p3"}, "无法相互核实"),
            ("wrong_clock", {"index": 1, "segment_id": "p2", "start_time": 0, "end_time": 2}, "无法相互核实"),
            ("untimed_turn_with_clock", {"index": 2, "segment_id": "p3", "start_time": 0, "end_time": 2}, "无法相互核实"),
            ("untimed", {"index": 2, "segment_id": "p3"}, None),
            ("missing_turns", {"index": 1}, "录音缺少可核实的原始音段"),
            ("same_quote_twice", {"text": "否认胸痛", "segment_id": "p1", "start_time": 0.5}, "同一原文被重复选取"),
        ]
        for case, selection, error in variants:
            orchestrator = MedicalRecordOrchestrator(generator)
            tid = orchestrator.create_text_task(SOURCE)
            set_task_owner(tid, owner["id"])
            turns = [] if case == "missing_turns" else TURNS
            generated = orchestrator.run_existing_text_task(tid, SOURCE, {"segments": turns, "engine": "fixture"})
            assert generated["status"] == "WAITING_DOCTOR_REVIEW", case
            old = deepcopy(get_record_revision(get_task(tid)["current_record_revision_id"]))
            fields = json.loads(old["result_json"])["fields"]
            previous = deepcopy(fields["present_illness"]["source_spans"])
            addition = {"text": "发热两天", **selection}
            fields["present_illness"].update(value="否认胸痛；发热两天", source_spans=[*previous, addition])
            payload = {**review_payload_for_fields(tid, fields), "source_corrected_fields": ["present_illness"]}
            saved = client.post(f"/api/tasks/{tid}/review", json=payload)
            assert saved.status_code == 200, saved.text
            current = client.get(f"/api/tasks/{tid}").json()["result_json"]
            field = current["fields"]["present_illness"]
            assert field["source_spans"][0] == previous[0] and len(field["source_spans"]) == 2
            assert (field["status"] == "conflicting") == bool(error), field
            assert field["doctor_review_status"] == "pending" and not current["approved"]
            assert get_record_revision(old["id"]) == old
            assert client.post(f"/api/tasks/{tid}/review", json=payload).status_code == 409
            if error:
                assert error in field["hint"]
                assert not field["doctor_review_note"].startswith("doctor_source_correction_v1:")
                approval = approval_payload_for_fields(current["fields"], task_id=tid)
                assert client.post(f"/api/tasks/{tid}/approve", json=approval).status_code == 409
            else:
                last = field["source_spans"][-1]
                clocks = (4.5, 6) if selection["segment_id"] == "p2" else (None, None)
                assert (last["start_time"], last["end_time"]) == clocks
                assert field["doctor_review_note"].startswith("doctor_source_correction_v1:")


@pytest.mark.parametrize("source,turns,span,expected_conflict", [
    ("[患者] 发热两天。", None, {"text": "发热两天", "index": 0}, False),
    ("[患者] 发热两天。", None, {"text": "发热两天", "index": 0, "start_time": 0}, True),
    ("[患者] 发热两天。", None, {"text": "发烧两天", "index": 0}, True),
    ("[医生] 发热两天。", None, {"text": "发热两天", "index": 0}, True),
    ("[患者] 发热两天。", [{"text": "发热两天", "role": "patient", "start": 0, "end": 2}],
     {"text": "发热两天", "index": 0}, False),
])
def test_explicit_selection_preserves_text_or_real_legacy_audio_identity(source, turns, span, expected_conflict):
    fields = MedicalRecordFields(present_illness=MedicalField(value="发热两天", source_spans=[SourceSpan(**span)]))
    stored = ground_fields(fields, source, turns, source_corrected_fields={"present_illness"}, only_corrected=True)
    field = stored.present_illness
    assert (field.status == "conflicting") == expected_conflict, field
    assert field.source_spans[0].segment_id is None
    if turns and not expected_conflict:
        assert (field.source_spans[0].start_time, field.source_spans[0].end_time) == (0, 2)
