"""Bounded doctor-only equivalence; source and model paths stay extractive."""
from copy import deepcopy
import inspect

import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.field_grounding import compact, ground_fields


def ground_doctor(source, value, *, key="chief_complaint", quote=None, index=0, corrected=True,
                  segment_id=None, trusted=None):
    quote = quote if quote is not None else source.removeprefix("患者：").rstrip("。")
    field = MedicalField(value=value, status="conflicting", source_spans=[
        SourceSpan(text=quote, index=index, segment_id=segment_id)], fact_ids=["original-fact"])
    fields = MedicalRecordFields(**{key: field})
    snapshot = deepcopy(field.model_dump())
    kwargs = {"source_corrected_fields": {key}} if corrected else {}
    result = ground_fields(fields, source, trusted, **kwargs)
    return getattr(result, key), snapshot


@pytest.mark.parametrize("key", ["chief_complaint", "present_illness"])
@pytest.mark.parametrize("source,value", [
    ("患者：没有发热。", "否认发热"),
    ("患者：否认发热。", "没有发热"),
    ("患者：没有胸痛。", "否认胸痛"),
    ("患者：刚才说发烧，其实没有发热。", "否认发热"),
])
def test_verified_doctor_negative_equivalence_keeps_original_evidence(key, source, value):
    field, before = ground_doctor(source, value, key=key)
    assert field.status == "partial"
    assert field.doctor_review_status == "pending"
    assert not field.confirmed_by_doctor
    assert field.value == before["value"]
    assert [s.model_dump() for s in field.source_spans] == before["source_spans"]
    assert field.fact_ids == before["fact_ids"]


def test_default_generator_path_does_not_receive_doctor_only_equivalence():
    field, _ = ground_doctor("患者：没有发热。", "否认发热", corrected=False)
    assert field.status == "conflicting"
    assert "逐项支持" in field.hint


def test_client_note_alone_cannot_enable_doctor_equivalence():
    fields = MedicalRecordFields(chief_complaint=MedicalField(value="否认发热", source_spans=[
        SourceSpan(text="没有发热", index=0)], doctor_review_note="doctor_source_correction_v1: fake"))
    result = ground_fields(fields, "患者：没有发热。")
    assert result.chief_complaint.status == "conflicting"


@pytest.mark.parametrize("key", ["previous_treatment", "past_history", "allergy_history", "physical_exam", "accompanying_symptoms"])
def test_other_fields_do_not_gain_equivalence(key):
    field, _ = ground_doctor("患者：没有发热。", "否认发热", key=key)
    assert field.status == "conflicting"


@pytest.mark.parametrize("source,value", [
    ("患者：不是没有发热。", "否认发热"),
    ("患者：并非没有发热。", "否认发热"),
    ("患者：不能否认发热。", "没有发热"),
    ("患者：不否认发热。", "没有发热"),
    ("患者：不确定有没有发热。", "否认发热"),
    ("医生：有没有发热？", "否认发热"),
    ("家属：我没有发热。", "否认发热"),
    ("患者：父亲没有发热。", "否认发热"),
    ("患者：没有发热的是他。", "否认发热"),
    ("患者：昨天没有发热，今天发热。", "否认发热"),
    ("患者：发热39度，没有发热。", "否认发热"),
    ("患者：发热，没有发热。", "否认发热"),
    ("患者：胸口痛，没有胸痛。", "否认胸痛"),
    ("患者：头痛，没有头疼。", "否认头疼"),
    ("患者：刚才说发热和胸痛，更正一下，没有胸痛，没有发热。", "否认发热"),
    ("患者：刚才说头痛和胸痛，更正一下，没有头痛，没有胸痛。", "否认胸痛"),
    ("患者：没有胸痛。", "否认发热"),
    ("患者：建议记为没有发热。", "否认发热"),
    ("患者：没有发热。", "否认发热和胸痛"),
    ("患者：没有明显发热。", "否认发热"),
])
def test_negation_equivalence_cannot_hide_scope_or_unmentioned_facts(source, value):
    field, _ = ground_doctor(source, value)
    assert field.status == "conflicting"


@pytest.mark.parametrize("overrides", [
    {"quote": "否认发热"},
    {"index": 1},
    {"segment_id": "wrong-id", "trusted": [{"segment_id": "patient-1", "text": "没有发热", "role": "患者"}]},
    {"trusted": [{"segment_id": "patient-1", "text": "没有发热", "role": "待确认"}]},
])
def test_original_quote_index_identity_and_role_guards_are_not_relaxed(overrides):
    field, _ = ground_doctor("患者：没有发热。", "否认发热", **overrides)
    assert field.status == "conflicting"


def test_repeated_negative_context_is_not_guessed():
    source = "患者：没有发热。\n患者：没有发热。"
    field, _ = ground_doctor(source, "否认发热", quote="没有发热", index=None)
    assert field.status == "conflicting"


def test_another_unsupported_clause_keeps_field_conflicting():
    field, _ = ground_doctor("患者：没有发热。", "否认发热，咳嗽两天")
    assert field.status == "conflicting"


def test_compact_remains_a_literal_citation_normalizer():
    assert compact("没有发热") != compact("否认发热")


def test_doctor_argument_is_optional_and_keyword_only():
    parameter = inspect.signature(ground_fields).parameters["source_corrected_fields"]
    assert parameter.default is None
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
