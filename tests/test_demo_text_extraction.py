"""Synthetic workbench input through the normal Mock field generator."""
import pytest

from app.services.clinical_facts import extract_clinical_facts
from app.services.live_clinical import build_live_clinical_snapshot, normalize_live_segment
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.treatment_context import treatment_grounding_errors
from scripts.demo_flow import DEFAULT_CONVERSATION


def generate(text):
    generator = LLMRecordGenerator(allow_mock_fallback=False)
    fields = generator.extract_fields(text)
    assert generator.get_trace()["actual_provider"] == "mock"
    return fields


def test_showcase_history_keeps_frequency_and_separates_allergy_from_its_full_quote():
    fields = generate(DEFAULT_CONVERSATION)
    assert fields.previous_treatment.value == "昨天吃过一次布洛芬"
    assert fields.previous_treatment.missing_elements == ["用药剂量"]
    assert "昨天吃过一次布洛芬" in fields.present_illness.value
    assert "处理经过尚未提及" not in fields.present_illness.value
    assert "退热" not in fields.previous_treatment.value
    assert fields.previous_treatment.source_spans[0].index == 3
    assert fields.previous_treatment.source_spans[0].text in DEFAULT_CONVERSATION.splitlines()[3]
    assert fields.allergy_history.value == "没有药物过敏史"
    quote = fields.allergy_history.source_spans[0]
    assert quote.index == 1 and quote.text == DEFAULT_CONVERSATION.splitlines()[1].rstrip("。")


@pytest.mark.parametrize(("row", "value", "assertion"), [
    ("患者：没有吃过一次布洛芬。", "没有吃过一次布洛芬", "absent"),
    ("患者：不确定是否吃过一次布洛芬。", "不确定是否吃过一次布洛芬", "uncertain"),
    ("医生：建议吃一次布洛芬。", None, None),
    ("患者：我父亲昨天吃过一次布洛芬。", None, None),
    ("家长：孩子昨天吃过一次布洛芬。", "孩子昨天吃过一次布洛芬", "present"),
    ("患者：昨天吃过一次晚饭。", None, None),
])
def test_medication_count_keeps_assertion_subject_and_drug_boundary(row, value, assertion):
    source = "患者：发热两天。\n" + row
    fields = generate(source)
    assert fields.previous_treatment.value == value
    facts = [f for f in extract_clinical_facts(source) if f.type == "treatment" and f.experiencer == "patient"]
    assert [f.assertion for f in facts] == ([assertion] if assertion else [])


def test_four_fever_demo_terms_cannot_replace_a_medication_denial_with_a_canned_response():
    source = "患者：发热、咳嗽、咳痰，最高体温38.2℃。\n患者：昨天没有吃过一次布洛芬。"
    fields = generate(source)
    assert fields.previous_treatment.value == "昨天没有吃过一次布洛芬"
    assert "服用布洛芬后可退热" not in fields.present_illness.value
    assert "卫生院" not in fields.previous_treatment.value


@pytest.mark.parametrize(("source", "expected"), [
    ("患者：咳嗽、发热，没有药物过敏史。", "没有药物过敏史"),
    ("患者：没有胸痛，药物过敏不清楚。", "药物过敏不清楚"),
    ("患者：青霉素过敏，表现为胸闷。", "青霉素过敏，表现为胸闷"),
    ("患者：以前青霉素过敏，现在已经脱敏了。", "以前青霉素过敏，现在已经脱敏了"),
    ("患者：我不确定，可能是药物过敏。", "我不确定，可能是药物过敏"),
    ("患者：我父亲有药物过敏，我本人没有药物过敏史。", "我本人没有药物过敏史"),
    ("患者：昨天吃过一次布洛芬，没有药物过敏史。", "没有药物过敏史"),
    ("患者：药物过敏，回想起来我说错了。", "药物过敏，回想起来我说错了"),
])
def test_allergy_body_preserves_reaction_and_qualifiers(source, expected):
    field = generate(source).allergy_history
    assert field.value == expected
    assert field.source_spans[0].text == source.rstrip("。")


def test_temporary_allergy_uses_same_statement_and_retains_segment_identity():
    raw = {"segment_id": "demo-1", "role": "患者", "text": "没有胸痛，没有药物过敏史。"}
    snapshot = build_live_clinical_snapshot(session_id="E1-synthetic",
        stable_segments=[normalize_live_segment(raw, sequence=1)], version=1,
        based_on_sequence=1, updated_at="2026-11-02T00:00:00Z")
    field = snapshot["record_patch"]["allergy_history"]
    assert field["temporary"] and field["evidence_segment_ids"] == ["demo-1"]
    assert field["value"] == "没有药物过敏史"


@pytest.mark.parametrize(("source", "expected"), [
    ("患者：医生说如果发热，吃一次布洛芬。", None),
    ("患者：医生建议，吃一次布洛芬。", None),
    ("患者：医生说如果发热，吃一次布洛芬，但我昨天已经吃过一次布洛芬。", "我昨天已经吃过一次布洛芬"),
    ("患者：昨天发热，吃过一次布洛芬。", "吃过一次布洛芬"),
])
def test_suggested_intake_after_comma_is_not_documented_as_taken(source, expected):
    assert generate(source).previous_treatment.value == expected


def test_truncated_quote_cannot_turn_conditional_advice_into_patient_intake():
    assert treatment_grounding_errors("吃一次布洛芬", "患者：医生说如果发热，吃一次布洛芬。", previous_treatment=True)


@pytest.mark.parametrize(("source", "expected"), [
    ("患者：没有药物过敏史，我妈妈对青霉素过敏。", "没有药物过敏史"),
    ("患者：我爸爸对青霉素过敏，我本人对头孢过敏。", "我本人对头孢过敏"),
    ("家长：孩子咳嗽，我是孩子妈妈，我对青霉素过敏。", None),
    ("患者：我有发热咳嗽两天，最高烧到38.2度，无咳血，没有药物过敏史。", "没有药物过敏史"),
    ("患者：我对青霉素过敏，过敏后出现咳嗽和气短。", "我对青霉素过敏，过敏后出现咳嗽和气短"),
    ("患者：我对氯化钾过敏，也对碘酒过敏。", "我对氯化钾过敏；也对碘酒过敏"),
])
def test_allergy_body_shows_patient_fact_but_quote_keeps_other_history(source, expected):
    field = generate(source).allergy_history
    assert field.value == expected
    if expected:
        assert field.source_spans[0].text == source.rstrip("。")
