"""Observed B01/I01/P01 failures; no model, network or clinical data."""
import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.clinical_facts import extract_clinical_facts, split_clinical_segments
from app.services.field_grounding import ground_fields


def states(source):
    return {(f.name, f.assertion, f.experiencer) for f in extract_clinical_facts(source)}


def test_unanswered_following_doctor_questions_do_not_create_negations():
    source = "医生：什么时候开始不舒服？有没有胸痛？有没有药物过敏？体重多少？"
    assert extract_clinical_facts(source) == []


def test_negations_come_from_answer_not_doctor_question():
    source = "医生：什么时候开始不舒服？有没有胸痛或者药物过敏？\n患者：发热两天。没有胸痛，也没有药物过敏史。"
    facts = extract_clinical_facts(source)
    for fact in facts:
        if fact.name in {"胸痛", "药物过敏"}:
            assert fact.assertion == "absent"
            assert fact.source_span.index == 3
            assert fact.source_span.text in split_clinical_segments(source)[3]


@pytest.mark.parametrize("source,expected", [
    ("患者：没有胸痛及气促。", {("胸痛", "absent", "patient"), ("气促", "absent", "patient")}),
    ("患者：没有胸痛，但咳嗽两天。", {("胸痛", "absent", "patient"), ("咳嗽", "present", "patient")}),
    ("患者：不是没有胸痛。", {("胸痛", "present", "patient")}),
    ("患者：并非没有咳嗽。", {("咳嗽", "present", "patient")}),
    ("患者：咳嗽两天，咽痛，药物过敏不清楚。", {("咳嗽", "present", "patient"), ("咽痛", "present", "patient"), ("药物过敏", "uncertain", "patient")}),
    ("患者：咳嗽已缓解，但仍有咽痛。", {("咳嗽", "resolved", "patient"), ("咽痛", "present", "patient")}),
    ("患者：我父亲有药物过敏，我自己咳嗽两天。", {("药物过敏", "present", "family"), ("咳嗽", "present", "patient")}),
    ("家长：孩子咳嗽两天，咽痛，我自己有药物过敏。", {("咳嗽", "present", "patient"), ("咽痛", "present", "patient"), ("药物过敏", "present", "family")}),
    ("家长：孩子咳嗽两天，咽痛，孩子的药物过敏我不清楚。", {("咳嗽", "present", "patient"), ("咽痛", "present", "patient"), ("药物过敏", "uncertain", "patient")}),
    ("患者：孩子咳嗽两天。", {("咳嗽", "present", "family")}),
    ("家属：我咳嗽两天。", {("咳嗽", "present", "family")}),
])
def test_scope_and_experiencer(source, expected):
    assert expected <= states(source)


@pytest.mark.parametrize("phrase,value", [("三十八点二度", "38.2℃"), ("三十九点五摄氏度", "39.5℃"), ("四十点零度", "40℃")])
def test_chinese_decimal_temperature_keeps_original_evidence(phrase, value):
    source = f"患者：最高体温{phrase}。"
    facts = extract_clinical_facts(source)
    temperature = next(f for f in facts if f.type == "measurement")
    assert temperature.value == value
    assert phrase in temperature.source_span.text
    assert temperature.source_span.text == split_clinical_segments(source)[0]


@pytest.mark.parametrize("condition", ["高血压", "糖尿病", "罕见病甲"])
def test_family_history_is_rejected_without_condition_dictionary(condition):
    quote = f"我父亲有{condition}"
    fields = MedicalRecordFields(past_history=MedicalField(value=quote, source_spans=[SourceSpan(text=quote, index=0)]))
    checked = ground_fields(fields, f"患者：{quote}。")
    assert checked.past_history.status == "conflicting"
    assert checked.past_history.value == quote
    assert checked.past_history.source_spans[0].text == quote


def test_unlabelled_second_doctor_question_cannot_be_patient_field():
    fields = MedicalRecordFields(allergy_history=MedicalField(value="有没有药物过敏", source_spans=[SourceSpan(text="有没有药物过敏", index=1)]))
    assert ground_fields(fields, "医生：有什么不舒服？有没有药物过敏？").allergy_history.status == "conflicting"


def test_explicit_child_subject_can_be_grounded_from_guardian_text():
    source = "医生：孩子多大？\n家长：孩子咳嗽两天，咽痛。"
    quote = "孩子咳嗽两天，咽痛"
    fields = MedicalRecordFields(present_illness=MedicalField(value=quote, source_spans=[SourceSpan(text=quote, index=1)]))
    assert ground_fields(fields, source).present_illness.status == "complete"


def test_guardian_text_does_not_bypass_unconfirmed_audio_role():
    source = "家长：孩子咳嗽两天。"
    quote = "孩子咳嗽两天"
    fields = MedicalRecordFields(present_illness=MedicalField(value=quote, source_spans=[SourceSpan(text=quote, index=0, segment_id="s1")]))
    trusted = [{"segment_id": "s1", "text": quote, "role": "待确认"}]
    assert ground_fields(fields, source, trusted).present_illness.status == "conflicting"
