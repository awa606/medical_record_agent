"""Medication context must survive the complete extraction and citation chain."""
import pytest

from app.services.clinical_facts import extract_clinical_facts
from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.base import LLMProviderResponse
from app.services.llm.llm_record_generator import LLMRecordGenerator


def run_recorded(monkeypatch, source, value, *, audio=False, key="previous_treatment", speaker="患者"):
    monkeypatch.setattr("app.services.llm.llm_record_generator.anonymize_text", lambda text: text)
    payload = MedicalRecordFields(**{
        key: MedicalField(value=value, source_spans=[SourceSpan(text=source, index=0)]),
        "past_history": MedicalField(value="既往身体健康", source_spans=[SourceSpan(text="既往身体健康", index=1)]),
    })

    class RecordedProvider:
        name = "fixed-regression-response"
        model = "no-real-model-call"
        calls = 0

        def generate_fields_json(self, text, *, timeout_seconds):
            self.calls += 1
            return LLMProviderResponse(provider=self.name, model=self.model, content=payload.model_dump_json(), latency_ms=0)

    provider = RecordedProvider()
    generator = LLMRecordGenerator(provider=provider, allow_mock_fallback=False)
    generator.max_retries = 0
    if audio:
        generator.source_segments = [
            {"segment_id": "p1", "text": source, "role": "患者"},
            {"segment_id": "p2", "text": "既往身体健康", "role": "患者"},
        ]
    fields = generator.extract_fields(f"{speaker}：{source}。\n患者：既往身体健康。")
    assert provider.calls == 1
    assert fields.past_history.value == "既往身体健康"
    assert fields.past_history.status == "complete"
    return generator, fields


@pytest.mark.parametrize("audio", [False, True])
@pytest.mark.parametrize("source,value", [
    ("没有服用布洛芬", "服用布洛芬"),
    ("医生建议服用布洛芬", "服用布洛芬"),
    ("计划服用布洛芬", "服用布洛芬"),
    ("不确定有没有服用布洛芬", "服用布洛芬"),
    ("没有吃布洛芬，但服用了退热药", "吃布洛芬"),
    ("医生问有没有服用布洛芬", "服用布洛芬"),
    ("我父亲服用布洛芬", "服用布洛芬"),
    ("服用后体温没有下降", "服用后体温下降"),
    ("服用5g布洛芬", "服用5mg布洛芬"),
    ("医生建议服用布洛芬", "医生建议服用布洛芬"),
])
def test_wrong_treatment_remains_conflicting(monkeypatch, source, value, audio):
    generator, fields = run_recorded(monkeypatch, source, value, audio=audio)
    field = fields.previous_treatment
    assert field.status == "conflicting"
    assert field.value == value  # Never repair a rejected answer by inventing one.
    assert field.source_spans[0].text == source
    field.confirmed_by_doctor = True
    assert generator.safety_check(generator.generate_draft(fields), fields).blocked


@pytest.mark.parametrize("source", [
    "已经服用布洛芬", "没有服用布洛芬", "不确定是否服用布洛芬",
    "没有吃布洛芬，但服用了退热药", "服用后体温下降", "服用后体温没有下降",
    "昨天服用5mg布洛芬", "不是没有服用布洛芬",
])
def test_supported_treatment_is_not_rewritten_or_rejected(monkeypatch, source):
    _, fields = run_recorded(monkeypatch, source, source)
    assert fields.previous_treatment.status == "complete"
    assert fields.previous_treatment.value == source


@pytest.mark.parametrize("source,assertion", [
    ("没有服用布洛芬", "absent"),
    ("不确定有没有服用布洛芬", "uncertain"),
    ("已经服用布洛芬", "present"),
    ("服用布洛芬后体温没有下降", "present"),
])
def test_treatment_fact_keeps_local_state_and_exact_content(source, assertion):
    facts = [f for f in extract_clinical_facts("患者：" + source) if f.type == "treatment"]
    assert len(facts) == 1
    assert facts[0].assertion == assertion
    assert facts[0].value == source


def test_drug_name_is_not_a_treatment_effect():
    facts = [f for f in extract_clinical_facts("患者：没有吃布洛芬，但服用了退热药") if f.type == "treatment"]
    assert [(f.value, f.assertion) for f in facts] == [("没有吃布洛芬", "absent"), ("服用了退热药", "present")]
    assert not any("体温下降" in f.value for f in facts)


@pytest.mark.parametrize("source", ["医生建议服用布洛芬", "计划服用布洛芬", "布洛芬", "布洛芬过敏"])
def test_non_actual_treatment_is_not_inferred(source):
    assert not [f for f in extract_clinical_facts(source) if f.type == "treatment"]


def test_parent_can_report_child_medication(monkeypatch):
    source = "孩子已经服用布洛芬"
    _, fields = run_recorded(monkeypatch, source, source, speaker="家长")
    assert fields.previous_treatment.status == "complete"
    facts = [f for f in extract_clinical_facts("家长：" + source) if f.type == "treatment"]
    assert facts[0].experiencer == "patient"


def test_source_subject_is_scoped_to_medication_action():
    facts = [f for f in extract_clinical_facts("患者：我父亲服用布洛芬，但患者服用了退热药") if f.type == "treatment"]
    assert [f.experiencer for f in facts] == ["family", "patient"]


def test_truncated_quote_cannot_drop_intake_negation():
    from app.services.field_grounding import ground_fields
    fields = MedicalRecordFields(previous_treatment=MedicalField(value="服用布洛芬", source_spans=[SourceSpan(text="服用布洛芬", index=0)]))
    result = ground_fields(fields, "患者：没有服用布洛芬")
    assert result.previous_treatment.status == "conflicting"


def test_recommendation_keeps_explicit_modality_in_present_illness(monkeypatch):
    source = "医生建议服用布洛芬"
    _, fields = run_recorded(monkeypatch, source, source, key="present_illness")
    assert fields.present_illness.status == "complete"


@pytest.mark.parametrize("source,value", [
    ("没有吃过布洛芬", "吃过布洛芬"),
    ("未用过布洛芬", "用过布洛芬"),
    ("不必服用布洛芬", "服用布洛芬"),
    ("如果没有发热就服用布洛芬", "服用布洛芬"),
    ("不确定是否已经按照医生建议服用布洛芬", "已经按照医生建议服用布洛芬"),
])
def test_common_intake_and_advice_variants_do_not_drop_qualifiers(monkeypatch, source, value):
    _, fields = run_recorded(monkeypatch, source, value)
    assert fields.previous_treatment.status == "conflicting"


@pytest.mark.parametrize("source,value", [
    ("没有服用布洛芬而是服用对乙酰氨基酚", "服用对乙酰氨基酚"),
    ("我没有吃早饭就服用布洛芬", "服用布洛芬"),
    ("已经按照医生建议服用布洛芬", "已经按照医生建议服用布洛芬"),
])
def test_completed_intake_is_not_rejected_by_other_predicates(monkeypatch, source, value):
    _, fields = run_recorded(monkeypatch, source, value)
    assert fields.previous_treatment.status == "complete"
