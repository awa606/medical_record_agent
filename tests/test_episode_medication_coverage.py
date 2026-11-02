"""A recent patient-reported intake omitted altogether from HPI's citations."""
from __future__ import annotations

import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.field_alignment import refresh_existing_coverage_hints
from app.services.llm.llm_record_generator import LLMRecordGenerator
from tests.test_generation_failure_contract import ResponseProvider


PREFIX = "本次病程用药待核对（原文第"
SYMPTOM = "发热、咳嗽、咽痛两天，最高体温38.2℃，没有胸痛，没有药物过敏史"
MED = "昨天吃过一次布洛芬"
SOURCE = f"医生：您哪里不舒服？\n患者：{SYMPTOM}。\n医生：用过什么药？\n患者：{MED}。"


def replay(source=SOURCE, body=SYMPTOM):
    raw = MedicalRecordFields(
        present_illness=MedicalField(value=body, source_spans=[SourceSpan(text=SYMPTOM, index=1)]),
        previous_treatment=MedicalField(value=MED, source_spans=[SourceSpan(text=MED, index=3)]),
    )
    provider = ResponseProvider(raw.model_dump(mode="json"))
    gen = LLMRecordGenerator(provider=provider, mode="edge", allow_mock_fallback=False)
    gen.max_retries = 0
    result = gen.extract_fields(source)
    assert provider.calls == 1
    return result, raw


def test_first_output_replay_detects_uncited_e1_medication_without_copying_or_crediting_other_field():
    fields, raw = replay()
    hpi = fields.present_illness
    assert hpi.status == "partial"
    assert hpi.missing_elements == [f"{PREFIX}4段）：患者：{MED}"]
    assert hpi.value == raw.present_illness.value
    assert hpi.source_spans == raw.present_illness.source_spans
    assert fields.previous_treatment.value == MED and fields.previous_treatment.status == "complete"


@pytest.mark.parametrize(("reported", "expect_gap"), [
    ("家长：孩子昨天吃过一次布洛芬。", True),
    ("家长：本人昨天吃过一次布洛芬。", False),
    ("家长：我自己昨天吃过一次布洛芬。", False),
    ("患者：我母亲昨天吃过一次布洛芬。", False),
    ("医生：昨天吃过一次布洛芬吗？", False),
    ("昨天吃过一次布洛芬。", False),
    ("患者：昨天没有吃过布洛芬。", False),
    ("患者：昨天可能吃过一次布洛芬。", False),
    ("患者：昨天医生建议吃一次布洛芬。", False),
    ("患者：如果明天还发热，就用一次布洛芬。", False),
    ("患者：小时候吃过一次布洛芬。", False),
    ("患者：昨天吃过一次布洛芬。患者：刚才说错了，其实没吃布洛芬。", False),
])
def test_only_explicit_patient_recent_actual_intake_is_a_required_source_fact(reported, expect_gap):
    fields = MedicalRecordFields(present_illness=MedicalField(value="发热", source_spans=[SourceSpan(text="发热",index=0)]))
    source = "患者：发热。" + reported if "：" in reported else reported
    revised = refresh_existing_coverage_hints(fields, source=source)
    assert any(x.startswith(PREFIX) for x in revised.present_illness.missing_elements) is expect_gap
    assert revised.present_illness.value == "发热"


@pytest.mark.parametrize(("chart", "gap"), [
    ("昨天吃过一次布洛芬", False), ("昨日服用布洛芬1次", False),
    ("昨天吃过一次阿司匹林", True), ("昨天没有吃过一次布洛芬", True),
    ("昨天可能吃过一次布洛芬", True), ("昨天吃过两次布洛芬", True),
    ("昨天建议服用一次布洛芬", True), ("去年吃过一次布洛芬", True),
])
def test_manual_review_rederives_from_source_not_submitted_status_or_previous_treatment(chart, gap):
    fields = MedicalRecordFields(present_illness=MedicalField(value=f"{SYMPTOM}；{chart}",
        status="partial", hint="医生手工修改；原始转写证据仅供对照，需在当前Revision中明确审核。",
        source_spans=[SourceSpan(text=SYMPTOM,index=1)], doctor_review_note="manual_doctor_edit_v1: 医生手工修改"),
        previous_treatment=MedicalField(value=MED, source_spans=[SourceSpan(text=MED,index=3)]))
    original = fields.model_dump()
    revised = refresh_existing_coverage_hints(fields, source=SOURCE)
    assert any(x.startswith(PREFIX) for x in revised.present_illness.missing_elements) is gap
    assert revised.present_illness.value == fields.present_illness.value
    assert revised.present_illness.hint == fields.present_illness.hint
    assert fields.model_dump() == original


@pytest.mark.parametrize(("source", "expected"), [
    ("患者：发热两天，昨天吃过一次布洛芬，没有胸痛。", True),
    ("患者：昨天吃过一次布洛芬。患者：刚才咳嗽说错了。", True),
    ("患者：昨天吃过一次布洛芬。患者：其实没有胸痛。", True),
    ("患者：昨天吃过一次布洛芬。患者：刚才说错了，我没吃过阿司匹林。", True),
    ("患者：昨天吃过一次布洛芬。患者：刚才说错了，其实我没吃过药。", False),
    ("患者：昨天吃过一次布洛芬。患者：刚才说错了，其实没吃布洛芬。", False),
    ("患者：我父亲发热，昨天吃过一次布洛芬。", False),
    ("患者：如果我昨天发热，昨天吃过一次布洛芬。", False),
    ("患者：昨天吃过一次布洛芬？", False),
])
def test_whole_original_sentence_anchor_and_local_retraction_scope(source, expected):
    fields = MedicalRecordFields(present_illness=MedicalField(value="发热两天"))
    revised = refresh_existing_coverage_hints(fields, source=source)
    issues = [item for item in revised.present_illness.missing_elements if item.startswith(PREFIX)]
    assert issues == ([f"{PREFIX}1段）：{source.split('。')[0]}"] if expected else [])


def test_second_sentence_of_one_labeled_turn_is_attributed_but_an_unlabeled_new_turn_is_not():
    fields = MedicalRecordFields(present_illness=MedicalField(value="发热"))
    for separator, gap in [("。", True), ("。\n", False)]:
        revised = refresh_existing_coverage_hints(fields, source=f"患者：发热{separator}{MED}。")
        assert any(item.startswith(PREFIX) for item in revised.present_illness.missing_elements) is gap


@pytest.mark.parametrize(("source", "gap"), [
    ("患者：我父亲发热。昨天吃过一次布洛芬。", False),
    ("患者：我父亲发热。患者：昨天吃过一次布洛芬。", False),
    ("患者：我父亲发热。我昨天吃过一次布洛芬。", True),
    ("家长：孩子昨天吃过一次布洛芬。", True),
    ("患者：昨天吃过一次布洛芬。患者：医生说其实没吃布洛芬会更好。", True),
    ("患者：昨天吃过一次布洛芬。患者：如果其实没吃布洛芬。", True),
    ("患者：昨天吃过一次布洛芬。患者：假设我其实没吃药。", True),
    ("患者：昨天吃过一次布洛芬。患者：刚才说错了，其实没吃布洛芬。", False),
    ("患者：昨天吃过一次布洛芬。患者：刚才说错了，其实我没吃过药。", False),
])
def test_cross_sentence_subject_and_direct_intake_retraction_boundaries(source, gap):
    fields = MedicalRecordFields(present_illness=MedicalField(value="发热"))
    revised = refresh_existing_coverage_hints(fields, source=source)
    assert any(item.startswith(PREFIX) for item in revised.present_illness.missing_elements) is gap
