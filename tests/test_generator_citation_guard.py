"""Exercise the complete extraction pipeline, before source canonicalization."""
import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.base import LLMProviderResponse
from app.services.llm.llm_record_generator import LLMRecordGenerator


def extract(value, spans, source, trusted, *, key="chief_complaint"):
    payload = MedicalRecordFields(**{key: MedicalField(value=value, source_spans=spans)})

    class RecordedProvider:
        name = "recorded-test-response"
        model = "no-model-call"

        def generate_fields_json(self, text, *, timeout_seconds):
            return LLMProviderResponse(
                provider=self.name, model=self.model,
                content=payload.model_dump_json(), latency_ms=0,
            )

    generator = LLMRecordGenerator(provider=RecordedProvider(), allow_mock_fallback=False)
    generator.max_retries = 0
    generator.source_segments = trusted
    return generator, generator.extract_fields(source)


@pytest.mark.parametrize("index", [1, 8, -1])
def test_generator_keeps_wrong_index_conflicting(index):
    generator, fields = extract(
        "发热38.2℃", [SourceSpan(text="发热38.2℃", index=index)],
        "[患者] 发热38.2℃。\n[医生] 有没有胸痛？",
        [{"segment_id": "p1", "text": "发热38.2℃", "role": "患者"},
         {"segment_id": "d1", "text": "有没有胸痛？", "role": "医生"}],
    )
    field = fields.chief_complaint
    assert field.status == "conflicting"
    assert field.value == "发热38.2℃"
    assert field.source_spans[0].index == index
    assert "序号" in field.hint
    field.confirmed_by_doctor = True
    field.high_risk_confirmed_by_doctor = True
    assert generator.safety_check(generator.generate_draft(fields), fields).blocked


@pytest.mark.parametrize("value,quote,key", [
    ("花生过敏", "我没有花生过敏", "allergy_history"),
    ("花生过敏", "我父亲有花生过敏", "allergy_history"),
    ("今天胸痛", "昨天胸痛", "present_illness"),
    ("体温39℃", "体温38℃", "present_illness"),
    ("服用5mg", "服用5g", "previous_treatment"),
    ("发烧39度", "头痛", "accompanying_symptoms"),
])
def test_generator_cannot_replace_a_wrong_value_with_a_valid_quote(value, quote, key):
    generator, fields = extract(
        value, [SourceSpan(text=quote, index=0)], "[患者] " + quote + "。",
        [{"segment_id": "p1", "text": quote, "role": "患者"}], key=key,
    )
    field = getattr(fields, key)
    assert field.status == "conflicting"
    assert field.value == value
    assert field.source_spans[0].text == quote
    assert generator.safety_check(generator.generate_draft(fields), fields).blocked


@pytest.mark.parametrize("quote,index,segment_id", [
    ("发热", 0, "invented"),
    ("发热", 0, "d1"),
    ("原文没有的病史", 0, None),
    ("", 0, None),
    ("有没有胸痛", 1, "d1"),
])
def test_generator_preserves_invalid_or_doctor_citations(quote, index, segment_id):
    _, fields = extract(
        "发热", [SourceSpan(text=quote, index=index, segment_id=segment_id)],
        "患者：发热。\n医生：有没有胸痛？",
        [{"segment_id": "p1", "text": "发热", "role": "患者"},
         {"segment_id": "d1", "text": "有没有胸痛？", "role": "医生"}],
    )
    assert fields.chief_complaint.status == "conflicting"
    assert fields.chief_complaint.value == "发热"
    assert fields.chief_complaint.source_spans[0].index == index


def test_generator_does_not_drop_one_bad_span_and_accept_the_rest():
    _, fields = extract(
        "发热", [SourceSpan(text="发热", index=0), SourceSpan(text="发热", index=1)],
        "患者：发热。\n医生：有没有胸痛？",
        [{"segment_id": "p1", "text": "发热", "role": "患者"},
         {"segment_id": "d1", "text": "有没有胸痛？", "role": "医生"}],
    )
    assert fields.chief_complaint.status == "conflicting"
    assert [s.index for s in fields.chief_complaint.source_spans] == [0, 1]


@pytest.mark.parametrize("quote,key,role", [
    ("发热38.2℃", "chief_complaint", "患者"),
    ("我没有花生过敏", "allergy_history", "患者"),
    ("服用5mg", "previous_treatment", "患者"),
    ("昨天胸痛", "present_illness", "患者"),
    ("体温38℃", "physical_exam", "医生"),
])
def test_generator_keeps_supported_extracts_and_audio_identity(quote, key, role):
    _, fields = extract(
        quote, [SourceSpan(text=quote, index=0)], f"[{role}] {quote}。",
        [{"segment_id": "s1", "text": quote, "role": role, "start_time": 1, "end_time": 2}],
        key=key,
    )
    field = getattr(fields, key)
    assert field.status == "complete"
    assert field.value == quote
    assert field.source_spans[0].segment_id == "s1"
    assert field.source_spans[0].start_time == 1


@pytest.mark.parametrize("segment_id,expected", [(None, "conflicting"), ("p2", "complete")])
def test_generator_repeated_text_requires_unambiguous_audio_identity(segment_id, expected):
    _, fields = extract(
        "发热", [SourceSpan(text="发热", index=1, segment_id=segment_id)],
        "患者：发热。\n患者：发热。",
        [{"segment_id": "p1", "text": "发热", "role": "患者"},
         {"segment_id": "p2", "text": "发热", "role": "患者"}],
    )
    assert fields.chief_complaint.status == expected
    if segment_id:
        assert fields.chief_complaint.source_spans[0].segment_id == segment_id


def test_generator_conflict_survives_revision_and_blocks_approval_and_export(tmp_path, monkeypatch):
    import json
    from fastapi import HTTPException
    from app.agents import MedicalRecordOrchestrator
    from app.api.tasks import TaskApprovalRequest, approve_task, export_task
    from app.db import get_task, get_active_approval_for_task
    from tests.approval_helpers import approval_payload_for_fields

    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "exports"))
    source = "患者：发热38.2℃。\n医生：有没有胸痛？"
    segments = [{"segment_id": "p1", "text": "发热38.2℃", "role": "患者"},
                {"segment_id": "d1", "text": "有没有胸痛？", "role": "医生"}]
    generator, _ = extract("发热38.2℃", [SourceSpan(text="发热38.2℃", index=1)], source, segments)
    orchestrator = MedicalRecordOrchestrator(llm=generator)
    task_id = orchestrator.create_text_task(source)
    result = orchestrator.run_existing_text_task(task_id, source, asr_source={"segments": segments})
    assert result["status"] == "WAITING_DOCTOR_REVIEW"
    stored = get_task(task_id)
    assert stored["current_record_revision_id"] is not None
    fields = json.loads(stored["result_json"])["fields"]
    assert fields["chief_complaint"]["status"] == "conflicting"
    assert fields["chief_complaint"]["source_spans"][0]["index"] == 1
    # Even an explicit confirm_content action must not approve an unresolved conflict.
    payload = TaskApprovalRequest(**approval_payload_for_fields(fields, task_id=task_id))
    with pytest.raises(HTTPException) as approval:
        approve_task(task_id, payload)
    assert approval.value.status_code == 409
    assert get_active_approval_for_task(task_id) is None
    with pytest.raises(HTTPException) as export:
        export_task(task_id)
    assert export.value.status_code == 400
    assert not list((tmp_path / "exports").rglob("*.docx"))
