"""Fixed model responses exercise the complete Generator; no inference calls."""
import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.clinical_facts import extract_clinical_facts
from app.services.llm.base import LLMProviderResponse
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.treatment_context import treatment_contexts


def generate(monkeypatch, source, value, *, speaker="患者", audio=False, quote=None):
    monkeypatch.setattr("app.services.llm.llm_record_generator.anonymize_text", lambda text: text)
    payload = MedicalRecordFields(
        previous_treatment=MedicalField(value=value, source_spans=[SourceSpan(text=quote or source, index=0)]),
        past_history=MedicalField(value="既往身体健康", source_spans=[SourceSpan(text="既往身体健康", index=1)]),
    )

    class RecordedProvider:
        name = "fixed-action-boundary-response"
        model = "no-real-model-call"
        calls = 0

        def generate_fields_json(self, text, *, timeout_seconds):
            self.calls += 1
            return LLMProviderResponse(provider=self.name, model=self.model,
                content=payload.model_dump_json(), latency_ms=0)

    provider = RecordedProvider()
    generator = LLMRecordGenerator(provider=provider, allow_mock_fallback=False)
    generator.max_retries = 0
    if audio:
        generator.source_segments = [
            {"segment_id": "p1", "text": source, "role": speaker},
            {"segment_id": "p2", "text": "既往身体健康", "role": "患者"},
        ]
    fields = generator.extract_fields(f"{speaker}：{source}。\n患者：既往身体健康。")
    assert provider.calls == 1
    assert fields.past_history.value == "既往身体健康"
    assert fields.past_history.status == "complete"
    assert fields.previous_treatment.value == value
    assert fields.previous_treatment.source_spans[0].text == (quote or source)
    return fields.previous_treatment


@pytest.mark.parametrize("audio", [False, True])
def test_second_completed_medication_not_negated_by_first_action(monkeypatch, audio):
    field = generate(monkeypatch, "没有服用布洛芬而服用了阿莫西林", "服用了阿莫西林", audio=audio)
    # The chosen B remains valid; a broad citation still asks the doctor to
    # address the omitted A negation. Do not suppress that separate coverage gate.
    assert field.status == "partial"
    assert "已引用但未写入：没有服用布洛芬（无）" in field.missing_elements


@pytest.mark.parametrize("audio", [False, True])
def test_narrow_second_action_citation_has_no_first_action_conflict(monkeypatch, audio):
    field = generate(monkeypatch, "没有服用布洛芬而服用了阿莫西林", "服用了阿莫西林",
        quote="服用了阿莫西林", audio=audio)
    assert field.status == "complete"


@pytest.mark.parametrize("audio", [False, True])
def test_first_negated_medication_cannot_become_completed(monkeypatch, audio):
    field = generate(monkeypatch, "没有服用布洛芬而服用了阿莫西林", "服用布洛芬", audio=audio)
    assert field.status == "conflicting"


@pytest.mark.parametrize("source,value", [
    ("医生建议没有服用布洛芬而服用阿莫西林", "服用阿莫西林"),
    ("如果没有服用布洛芬而服用了阿莫西林", "服用了阿莫西林"),
    ("不清楚有没有服用布洛芬而服用了阿莫西林", "服用了阿莫西林"),
    ("我父亲没有服用布洛芬而服用了阿莫西林", "服用了阿莫西林"),
    ("没有服用布洛芬而服用了5mg阿莫西林", "服用了5g阿莫西林"),
])
def test_boundary_does_not_remove_required_qualifier_or_subject(monkeypatch, source, value):
    assert generate(monkeypatch, source, value).status == "conflicting"


def test_doctor_question_remains_question(monkeypatch):
    assert generate(monkeypatch, "有没有服用布洛芬而服用了阿莫西林", "服用了阿莫西林",
        speaker="医生").status == "conflicting"


def test_guardian_own_treatment_remains_non_patient(monkeypatch):
    assert generate(monkeypatch, "我自己没有服用布洛芬而服用了阿莫西林", "服用了阿莫西林",
        speaker="家长").status == "conflicting"


def test_non_action_conjunction_is_not_split():
    source = "没有因为发热而服用布洛芬"
    rows = treatment_contexts(source)
    assert [(r.text, r.assertion) for r in rows] == [(source, "absent")]


def test_causal_link_between_actions_is_not_treated_as_contrast():
    source = "没有因为服用布洛芬而服用阿莫西林"
    rows = treatment_contexts(source)
    assert len(rows) == 2
    assert all(r.text == source and r.assertion == "absent" for r in rows)


def test_intended_second_action_is_not_completed_treatment(monkeypatch):
    source = "我没有服用布洛芬而服用阿莫西林的打算"
    assert generate(monkeypatch, source, "服用阿莫西林").status == "conflicting"


@pytest.mark.parametrize("condition", ["假如", "假设", "倘若", "要是"])
@pytest.mark.parametrize("narrow_quote", [False, True])
def test_conditional_second_action_cannot_become_actual_intake(monkeypatch, condition, narrow_quote):
    source = f"{condition}没有服用布洛芬而服用了阿莫西林"
    field = generate(monkeypatch, source, "服用了阿莫西林",
        quote="服用了阿莫西林" if narrow_quote else None)
    assert field.status == "conflicting"


def test_hypothetical_word_in_previous_clause_does_not_block_real_action(monkeypatch):
    source = "刚才讨论的是假设情况，实际没有服用布洛芬而服用了阿莫西林"
    field = generate(monkeypatch, source, "服用了阿莫西林", quote="服用了阿莫西林")
    assert field.status == "complete"


@pytest.mark.parametrize("condition", ["假如", "假设", "倘若", "要是"])
@pytest.mark.parametrize("actions", ["服用了阿莫西林", "服用了布洛芬而服用了阿莫西林"])
@pytest.mark.parametrize("narrow_quote", [False, True])
def test_conditional_action_without_negation_is_not_actual_intake(monkeypatch, condition, actions, narrow_quote):
    source = condition + actions
    field = generate(monkeypatch, source, "服用了阿莫西林",
        quote="服用了阿莫西林" if narrow_quote else None)
    assert field.status == "conflicting"


@pytest.mark.parametrize("condition", ["假如", "假设", "倘若", "要是"])
@pytest.mark.parametrize("actions", ["服用了阿莫西林", "服用了布洛芬而服用了阿莫西林"])
def test_conditional_medication_not_in_fact_list(condition, actions):
    source = condition + actions
    contexts = treatment_contexts(source)
    assert contexts and all(context.proposed for context in contexts)
    assert not [fact for fact in extract_clinical_facts("患者：" + source) if fact.type == "treatment"]


def test_factual_medication_after_hypothesis_keeps_exact_fact():
    source = "刚才讨论的是假设情况，实际没有服用布洛芬而服用了阿莫西林"
    facts = [fact for fact in extract_clinical_facts("患者：" + source) if fact.type == "treatment"]
    assert [(fact.value, fact.assertion) for fact in facts] == [
        ("实际没有服用布洛芬", "absent"), ("服用了阿莫西林", "present")]


def test_mainly_took_medication_is_not_conditional(monkeypatch):
    source = "这两天主要是服用了布洛芬"
    assert generate(monkeypatch, source, source).status == "complete"


def test_mainly_took_medication_remains_in_fact_list():
    source = "这两天主要是服用了布洛芬"
    facts = [fact for fact in extract_clinical_facts("患者：" + source) if fact.type == "treatment"]
    assert [(fact.value, fact.assertion) for fact in facts] == [(source, "present")]


def test_exact_offsets_and_separate_states_for_two_actions():
    source = "患者：没有服用布洛芬而服用了阿莫西林"
    rows = treatment_contexts(source)
    assert [(r.text, r.assertion) for r in rows] == [
        ("没有服用布洛芬", "absent"), ("服用了阿莫西林", "present")]
    assert [source[r.action_start:r.action_start + 2] for r in rows] == ["服用", "服用"]
