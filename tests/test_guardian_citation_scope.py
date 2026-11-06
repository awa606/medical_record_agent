"""A wide truthful quote must not assign an adjacent parent's fact to a child."""
import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.llm_record_generator import LLMRecordGenerator
from tests.test_generation_failure_contract import ResponseProvider


SOURCE = "家长：孩子八岁，咳嗽两天。 我自己有高血压，孩子的药物过敏我不清楚。"
QUOTE = "我自己有高血压，孩子的药物过敏我不清楚"


def extract(value, *, index=1):
    fields = MedicalRecordFields(
        chief_complaint=MedicalField(value="孩子八岁，咳嗽两天", source_spans=[SourceSpan(text="孩子八岁，咳嗽两天", index=0)]),
        allergy_history=MedicalField(value=value, source_spans=[SourceSpan(text=QUOTE, index=index)]),
    )
    provider = ResponseProvider(fields.model_dump(mode="json"))
    generator = LLMRecordGenerator(provider=provider, mode="live", allow_mock_fallback=False)
    generator.max_retries = 0
    result = generator.extract_fields(SOURCE)
    assert provider.calls == 1
    return result


def test_explicit_child_clause_preserves_unknown_allergy_with_wide_quote():
    value = "孩子的药物过敏我不清楚"
    field = extract(value).allergy_history
    assert field.status != "conflicting"
    assert field.value == value
    assert field.source_spans[0].text == QUOTE
    assert field.source_spans[0].index == 1


@pytest.mark.parametrize("value", [
    "我自己有高血压",
    "孩子的药物过敏我不清楚；我自己有高血压",
    "药物过敏我不清楚",  # Do not infer the child merely from nearby text.
])
def test_parent_or_unanchored_value_stays_conflicting(value):
    field = extract(value).allergy_history
    assert field.status == "conflicting"
    assert field.value == value
    assert field.source_spans[0].text == QUOTE


def test_child_value_does_not_repair_wrong_original_index():
    assert extract("孩子的药物过敏我不清楚", index=0).allergy_history.status == "conflicting"
