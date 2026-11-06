"""Natural intake wording: detect omissions, never complete a model answer."""
from __future__ import annotations

import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.clinical_facts import split_clinical_segments
from app.services.episode_medication_coverage import episode_medication_gaps
from app.services.llm.base import LLMProviderResponse
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.treatment_context import treatment_contexts


@pytest.mark.parametrize("reported", [
    "患者：昨天晚上吃过一次布洛芬。",
    "患者：昨晚吃的那个布洛芬。",
    "患者：昨天晚上吃的那个布洛芬一次。",
    "患者：昨日晚上服用了两次阿莫西林。",
    "家长：孩子昨天晚上吃过一次布洛芬。",
])
def test_unquoted_colloquial_intake_is_reported_as_a_gap(reported):
    assert len(episode_medication_gaps(reported, "发热、咳嗽两天")) == 1


@pytest.mark.parametrize("reported", [
    "患者：昨天晚上没有吃过布洛芬。",
    "患者：昨天晚上可能吃过一次布洛芬。",
    "患者：昨天晚上医生建议吃一次布洛芬。",
    "患者：计划吃的那个布洛芬。",
    "患者：如果昨晚吃的那个布洛芬有效就好了。",
    "医生：昨天晚上吃过一次布洛芬吗？",
    "患者：昨天晚上吃过一次布洛芬？",
    "患者：我父亲昨天晚上吃过一次布洛芬。",
    "家长：我自己昨天晚上吃过一次布洛芬。",
    "家长：本人昨天晚上吃过一次布洛芬。",
    "患者：昨晚吃的那个布洛芬。患者：刚才说错了，其实没有吃布洛芬。",
    "患者：昨天晚上吃过一次布洛芬。患者：刚才说错了，其实昨晚没有吃布洛芬。",
    "患者：昨天晚上布洛芬。",
    "昨天晚上吃过一次布洛芬。",
    "患者：吃的那个布洛芬。",  # No episode date: keep this guard's narrow contract.
])
def test_non_actual_or_unattributed_intake_does_not_become_a_required_patient_fact(reported):
    assert episode_medication_gaps(reported, "发热两天") == []


@pytest.mark.parametrize("charted,expected_gap", [
    ("昨晚服用布洛芬1次", False),
    ("昨日晚上吃过一次布洛芬", False),
    ("昨晚吃过两次布洛芬", True),
    ("昨晚吃过一次阿莫西林", True),
    ("昨天早上吃过一次布洛芬", True),
    ("昨晚没有吃过一次布洛芬", True),
    ("昨晚可能吃过一次布洛芬", True),
])
def test_evening_alias_does_not_discard_count_drug_or_assertion(charted, expected_gap):
    gaps = episode_medication_gaps("患者：昨天晚上吃过一次布洛芬。", charted)
    assert bool(gaps) is expected_gap


@pytest.mark.parametrize("denial,expected_gap", [
    ("昨天没有吃布洛芬", False),
    ("昨日没有吃过药", False),
    ("昨天早上没有吃布洛芬", True),
    ("昨天上午没有吃布洛芬", True),
    ("今天没有吃布洛芬", True),
])
def test_evening_intake_retraction_distinguishes_whole_day_from_other_period(denial, expected_gap):
    source = f"患者：昨天晚上吃过一次布洛芬。患者：刚才说错了，其实{denial}。"
    assert bool(episode_medication_gaps(source, "发热两天")) is expected_gap


def _replay(monkeypatch, source, value, quote):
    # Fixed response, not a successful model sample; no DB/network is involved.
    monkeypatch.setattr("app.services.llm.llm_record_generator.anonymize_text", lambda text: text)
    raw = MedicalRecordFields(
        present_illness=MedicalField(value=value, source_spans=[SourceSpan(text=quote, index=0)]),
        past_history=MedicalField(value="既往身体健康", source_spans=[SourceSpan(
            text="既往身体健康", index=len(split_clinical_segments(source)))]),
    )

    class RecordedProvider:
        name = "recorded-colloquial-regression"
        model = "no-inference"
        calls = 0

        def generate_fields_json(self, text, *, timeout_seconds):
            self.calls += 1
            return LLMProviderResponse(self.name, self.model, raw.model_dump_json(), 0)

    provider = RecordedProvider()
    generator = LLMRecordGenerator(provider=provider, mode="edge", allow_mock_fallback=False)
    generator.max_retries = 0
    actual = generator.extract_fields(source + "。\n患者：既往身体健康。")
    assert provider.calls == 1
    assert actual.past_history.value == raw.past_history.value
    assert actual.past_history.status == "complete"
    assert actual.present_illness.value == raw.present_illness.value
    assert actual.present_illness.source_spans == raw.present_illness.source_spans
    return actual.present_illness


def test_full_generator_detects_evening_intake_outside_selected_quote(monkeypatch):
    field = _replay(monkeypatch, "患者：发热两天。\n患者：昨天晚上吃过一次布洛芬", "发热两天", "发热两天")
    assert field.status == "partial"
    assert any("本次病程用药待核对" in item for item in field.missing_elements)


def test_full_generator_detects_colloquial_intake_inside_selected_quote(monkeypatch):
    source = "患者：发热两天，吃的那个布洛芬"
    field = _replay(monkeypatch, source, "发热两天", source)
    assert field.status == "partial"
    assert any("已引用但未写入：吃的那个布洛芬" in item for item in field.missing_elements)


@pytest.mark.parametrize("source,assertion,proposed", [
    ("吃的那个布洛芬", "present", False),
    ("没有吃的那个布洛芬", "absent", False),
    ("不确定吃的那个布洛芬", "uncertain", False),
    ("医生建议吃的那个布洛芬", "present", True),
    ("明天吃的那个布洛芬", "present", True),
    ("要吃的那个布洛芬", "present", True),
    ("想吃的那个布洛芬", "present", True),
])
def test_colloquial_action_keeps_scope_and_original_offsets(source, assertion, proposed):
    rows = treatment_contexts(source)
    assert len(rows) == 1
    row = rows[0]
    assert (row.text, row.assertion, row.proposed) == (source, assertion, proposed)
    assert source[row.action_start:].startswith("吃的那个")


@pytest.mark.parametrize("source,value", [
    ("没有吃的那个布洛芬", "吃的那个布洛芬"),
    ("不确定吃的那个布洛芬", "吃的那个布洛芬"),
    ("医生建议吃的那个布洛芬", "吃的那个布洛芬"),
    ("要吃的那个布洛芬", "吃的那个布洛芬"),
    ("我父亲吃的那个布洛芬", "吃的那个布洛芬"),
])
def test_full_generator_does_not_accept_dropped_colloquial_qualifiers(monkeypatch, source, value):
    from tests.test_treatment_grounding import run_recorded

    _, result = run_recorded(monkeypatch, source, value)
    field = result.previous_treatment
    assert field.status == "conflicting"
    assert field.value == value
    assert field.source_spans[0].text == source
