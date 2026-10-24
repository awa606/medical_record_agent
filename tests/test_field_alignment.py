"""Recorded-provider regressions: no network, model or production database."""
from __future__ import annotations

import json

import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.field_grounding import ground_fields
from app.services.llm.base import LLMProviderResponse
from app.services.llm.llm_record_generator import LLMRecordGenerator


class RecordedFieldsProvider:
    name = "recorded_alignment"
    model = "fixed-response"

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def generate_fields_json(self, conversation_text, *, timeout_seconds):
        self.calls += 1
        return LLMProviderResponse(self.name, self.model, json.dumps(self.payload, ensure_ascii=False), 0)


def grounded_case(key, value, quotes, *, source=None):
    quotes = [quotes] if isinstance(quotes, str) else quotes
    source = source or "患者：" + "。患者：".join(quotes)
    fields = MedicalRecordFields(**{key: MedicalField(value=value, source_spans=[SourceSpan(text=q) for q in quotes])})
    return ground_fields(fields, source)


@pytest.mark.parametrize("key,value,quotes,expected", [
    ("allergy_history", "没有胸痛，没有药物过敏史", ["没有胸痛，没有药物过敏史"], "conflicting"),
    ("accompanying_symptoms", "没有胸痛，没有药物过敏史", ["没有胸痛，没有药物过敏史"], "conflicting"),
    ("previous_treatment", "这两天没有服用药物", ["这两天没有服用药物", "这次还没有做检查"], "partial"),
])
def test_generator_reports_alignment_without_rewriting_recorded_fields(monkeypatch, key, value, quotes, expected):
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    source = "患者：发热两天。患者：" + "。患者：".join(quotes)
    original = MedicalRecordFields(
        chief_complaint=MedicalField(value="发热两天", source_spans=[SourceSpan(text="发热两天", index=0)]),
        **{key: MedicalField(value=value, source_spans=[SourceSpan(text=q, index=i + 1) for i, q in enumerate(quotes)])},
    )
    provider = RecordedFieldsProvider(original.model_dump(mode="json"))
    generator = LLMRecordGenerator(provider=provider, mode="live", allow_mock_fallback=False)
    result = generator.extract_fields(source)
    actual = getattr(result, key)
    assert actual.status == expected
    assert actual.value == value
    assert [s.model_dump() for s in actual.source_spans] == [s.model_dump() for s in getattr(original, key).source_spans]
    assert result.chief_complaint.value == "发热两天"
    assert result.chief_complaint.status == "complete"
    assert provider.calls == generator.attempt_count == 1


@pytest.mark.parametrize("key,value,quotes,expected", [
    ("allergy_history", "没有胸痛，没有药物过敏史", "没有胸痛，没有药物过敏史", "conflicting"),
    ("accompanying_symptoms", "没有胸痛，没有药物过敏史", "没有胸痛，没有药物过敏史", "conflicting"),
    ("allergy_history", "没有药物过敏史", "没有胸痛，没有药物过敏史", "complete"),
    ("accompanying_symptoms", "没有胸痛", "没有胸痛，没有药物过敏史", "complete"),
    ("allergy_history", "青霉素过敏时胸闷", "青霉素过敏时胸闷", "complete"),
    ("allergy_history", "青霉素过敏，表现为胸闷", "青霉素过敏，表现为胸闷", "complete"),
    ("allergy_history", "青霉素过敏，表现为胸闷，还伴有气促", "青霉素过敏，表现为胸闷，还伴有气促", "complete"),
    ("allergy_history", "青霉素过敏，表现为胸闷，没有气促", "青霉素过敏，表现为胸闷，没有气促", "complete"),
    ("allergy_history", "青霉素过敏，表现为胸闷。没有胸痛", ["青霉素过敏，表现为胸闷", "没有胸痛"], "conflicting"),
    ("allergy_history", "青霉素过敏，表现为胸闷，此外没有胸痛", "青霉素过敏，表现为胸闷，此外没有胸痛", "conflicting"),
    ("accompanying_symptoms", "胸闷，是青霉素过敏引起", "胸闷，是青霉素过敏引起", "complete"),
    ("accompanying_symptoms", "青霉素过敏，表现为胸闷", "青霉素过敏，表现为胸闷", "complete"),
    ("accompanying_symptoms", "服用布洛芬后恶心", "服用布洛芬后恶心", "complete"),
    ("accompanying_symptoms", "胃里像打结一样难受", "胃里像打结一样难受", "complete"),
    ("chief_complaint", "发热两天", "发热两天，最高体温38.2℃，没有胸痛", "complete"),
    ("present_illness", "发热两天", "发热两天，最高体温38.2℃，没有胸痛", "partial"),
    ("present_illness", "发热两天，最高体温38.2℃，没有胸痛", "发热两天，最高体温38.2℃，没有胸痛", "complete"),
    ("previous_treatment", "这两天没有服用药物", "这两天没有服用药物", "complete"),
    ("previous_treatment", "这两天没有服用药物", "这两天没有服用药物，以前没有慢性疾病", "complete"),
    ("previous_treatment", "这两天没有服用药物", ["这两天没有服用药物", "这次还没有做检查"], "partial"),
    ("previous_treatment", "这两天没有服用药物；这次还没有做检查", ["这两天没有服用药物", "这次还没有做检查"], "complete"),
    ("previous_treatment", "这次还没有做检查", "患者：这次还没有做检查", "complete"),
    ("previous_treatment", "这次未进行过检查", "这次未进行过检查", "complete"),
    ("previous_treatment", "昨天服用布洛芬200mg", "昨天服用布洛芬200 mg", "complete"),
    ("previous_treatment", "昨天服用布洛芬0.2g", "昨天服用布洛芬0.2g", "complete"),
    ("present_illness", "体温38.20℃", "最高体温38.20摄氏度", "complete"),
    ("present_illness", "体温38.2", "体温38.2℃", "partial"),
    ("present_illness", "发热2天", "发热2 天", "complete"),
    ("present_illness", "昨天发热，今天咳嗽", ["昨天发热", "今天咳嗽"], "complete"),
    ("previous_treatment", "昨天服用布洛芬，今天未用药", ["昨天服用布洛芬", "今天未用药"], "complete"),
])
def test_alignment_reports_only_known_gaps_preserving_content(key, value, quotes, expected):
    from app.services.field_alignment import validate_field_alignment

    grounded = grounded_case(key, value, quotes)
    before = grounded.model_dump(mode="json")
    assert getattr(grounded, key).status == "complete"
    checked, diagnostics = validate_field_alignment(grounded)
    assert grounded.model_dump(mode="json") == before
    assert checked is not grounded
    assert getattr(checked, key).status == expected
    for field_key in ("chief_complaint", "present_illness", "previous_treatment", "accompanying_symptoms", "past_history", "allergy_history", "physical_exam"):
        old, new = getattr(grounded, field_key), getattr(checked, field_key)
        assert old.value == new.value
        assert [s.model_dump() for s in old.source_spans] == [s.model_dump() for s in new.source_spans]
    assert bool(diagnostics) is (expected != "complete")
    if expected == "partial":
        assert getattr(checked, key).missing_elements
        assert "未自动补写" in getattr(checked, key).hint
        assert diagnostics[key]["kind"] == "cited_same_field_coverage_gap"
    if expected == "conflicting":
        assert diagnostics[key]["kind"] == "independent_clause_field_mismatch"


@pytest.mark.parametrize("key,value,source,quotes", [
    ("previous_treatment", "昨天服用布洛芬0.2g", "患者：昨天服用布洛芬200mg", ["昨天服用布洛芬200mg"]),
    ("present_illness", "发热2天", "患者：发热两天", ["发热两天"]),
    ("previous_treatment", "这次还没有做检查", "患者：这次未进行检查", ["这次未进行检查"]),
    ("physical_exam", "查体正常", "患者：这次还没有做检查", ["这次还没有做检查"]),
    ("past_history", "父亲有高血压", "患者：父亲有高血压", ["父亲有高血压"]),
    ("allergy_history", "有没有药物过敏", "医生：有没有药物过敏？", ["有没有药物过敏"]),
    ("previous_treatment", "我没有服用药物", "家属：我服用布洛芬。患者：我没有服用药物", ["家属：我服用布洛芬", "患者：我没有服用药物"]),
    ("present_illness", "体温38.2℉", "患者：体温38.2℃", ["体温38.2℃"]),
])
def test_existing_grounding_refusals_are_never_replaced(key, value, source, quotes):
    from app.services.field_alignment import validate_field_alignment

    grounded = grounded_case(key, value, quotes, source=source)
    assert getattr(grounded, key).status == "conflicting"
    before = grounded.model_dump(mode="json")
    checked, diagnostics = validate_field_alignment(grounded)
    assert checked.model_dump(mode="json") == before
    assert diagnostics == {}


@pytest.mark.parametrize("note", [
    "manual_doctor_edit_v1: 医生补录，原文仅作参考。",
    "doctor_source_correction_v1: 医生根据原文修正，等待审核。",
])
def test_manual_sources_do_not_receive_new_classification(note):
    from app.services.field_alignment import validate_field_alignment

    original = MedicalRecordFields(allergy_history=MedicalField(
        value="没有胸痛，没有药物过敏史", status="partial", doctor_review_note=note,
        source_spans=[SourceSpan(text="没有胸痛，没有药物过敏史")],
    ))
    checked, diagnostics = validate_field_alignment(original)
    assert checked.model_dump() == original.model_dump()
    assert diagnostics == {}


def test_missing_existing_conflict_and_confirmed_fields_are_unchanged():
    from app.services.field_alignment import validate_field_alignment

    original = MedicalRecordFields(
        allergy_history=MedicalField(value="没有胸痛，没有药物过敏史", status="conflicting", hint="原始冲突"),
        accompanying_symptoms=MedicalField(value="没有胸痛，没有药物过敏史", confirmed_by_doctor=True, doctor_review_status="content_confirmed"),
    )
    checked, diagnostics = validate_field_alignment(original)
    assert checked.model_dump() == original.model_dump()
    assert diagnostics == {}


def test_coverage_details_are_idempotent_and_do_not_require_unrelated_allergy():
    from app.services.field_alignment import validate_field_alignment

    original = grounded_case("present_illness", "发热两天", "发热两天，没有胸痛，没有药物过敏史")
    once, diagnostics = validate_field_alignment(original)
    twice, _ = validate_field_alignment(once)
    assert once.model_dump() == twice.model_dump()
    assert once.present_illness.status == "partial"
    assert "胸痛" in "；".join(diagnostics["present_illness"]["items"])
    assert "过敏" not in "；".join(diagnostics["present_illness"]["items"])


@pytest.mark.parametrize("source,value,expected", [
    ("没有服用布洛芬而是服用对乙酰氨基酚", "服用对乙酰氨基酚", "complete"),
    ("我没有吃早饭就服用布洛芬", "服用布洛芬", "complete"),
    ("没有服用布洛芬而是服用对乙酰氨基酚200mg", "服用对乙酰氨基酚200mg", "complete"),
    ("没有服用布洛芬而是服用对乙酰氨基酚200mg", "服用对乙酰氨基酚", "partial"),
    ("没有服用布洛芬但服用对乙酰氨基酚", "服用对乙酰氨基酚", "partial"),
    ("我没有吃早饭就服用布洛芬200mg", "服用布洛芬200mg", "complete"),
    ("我没有吃早饭就服用布洛芬200mg", "服用布洛芬", "partial"),
    ("饭后服用布洛芬", "服用布洛芬", "partial"),
    ("我没有吃早饭就服用布洛芬后恶心", "服用布洛芬后恶心", "complete"),
    ("我没有吃早饭就服用布洛芬后恶心", "服用布洛芬", "partial"),
    ("服用新药X200mg后恶心", "服用新药X200mg后恶心", "complete"),
])
def test_treatment_coverage_keeps_replacement_and_action_scope(source, value, expected):
    from app.services.field_alignment import validate_field_alignment

    grounded = grounded_case("previous_treatment", value, source)
    assert grounded.previous_treatment.status == "complete"
    before = grounded.model_dump()
    checked, _ = validate_field_alignment(grounded)
    assert checked.previous_treatment.status == expected
    assert grounded.model_dump() == before
    assert checked.previous_treatment.value == value
    assert checked.previous_treatment.source_spans == grounded.previous_treatment.source_spans
