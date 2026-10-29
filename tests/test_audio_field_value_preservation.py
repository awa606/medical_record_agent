"""Audio identity binding must not expand a selected field to its whole segment."""
import pytest

from app.schemas import SourceSpan
from tests.test_generator_citation_guard import extract


@pytest.mark.parametrize("key,source,value,quote", [
    ("allergy_history", "没有胸痛，没有药物过敏史", "没有药物过敏史", "没有药物过敏史"),
    ("allergy_history", "没有胸痛，没有药物过敏史", "没有药物过敏史", "没有胸痛，没有药物过敏史"),
    ("accompanying_symptoms", "没有胸痛，没有药物过敏史", "没有胸痛", "没有胸痛"),
    ("previous_treatment", "这两天没有服用药物，以前没有慢性疾病", "这两天没有服用药物", "这两天没有服用药物"),
    ("chief_complaint", "发热两天，最高体温38.2℃，没有胸痛", "发热两天", "发热两天，最高体温38.2℃，没有胸痛"),
])
def test_audio_binding_preserves_selected_value_and_original_quote(key, source, value, quote):
    generator, fields = extract(
        value, [SourceSpan(text=quote, index=0)], "患者：" + source + "。",
        [{"segment_id": "p1", "text": source, "role": "患者", "start_time": 2.0, "end_time": 5.0}],
        key=key,
    )
    field = getattr(fields, key)
    assert field.value == value
    assert field.source_spans[0].text == quote
    assert field.source_spans[0].index == 0
    assert field.source_spans[0].segment_id == "p1"
    assert (field.source_spans[0].start_time, field.source_spans[0].end_time) == (2.0, 5.0)
    assert field.status != "conflicting"
    assert generator.field_repairs[key]["original_value_changed"] is False


def test_audio_binding_does_not_repair_an_unsupported_value():
    _, fields = extract(
        "咽痛", [SourceSpan(text="发热", index=0)], "患者：发热。",
        [{"segment_id": "p1", "text": "发热", "role": "患者"}],
    )
    assert fields.chief_complaint.value == "咽痛"
    assert fields.chief_complaint.status == "conflicting"
