"""A fixed response must not manufacture a clause across citation boundaries."""
import pytest

from app.schemas import SourceSpan
from tests.test_generator_citation_guard import extract


SOURCE = "患者：否认胸痛。\n患者：发热两天。"
SEGMENTS = [
    {"segment_id": "s1", "text": "否认胸痛", "role": "患者"},
    {"segment_id": "s2", "text": "发热两天", "role": "患者"},
]


@pytest.mark.parametrize("audio", [False, True], ids=["text", "reviewed-audio"])
def test_separate_citations_cannot_create_an_unsupported_negative(audio):
    spans = [SourceSpan(text="否认", index=0), SourceSpan(text="发热", index=1)]
    generator, fields = extract("否认发热", spans, SOURCE, SEGMENTS if audio else [])

    rejected = fields.chief_complaint
    assert rejected.status == "conflicting"
    assert "字段改写不能由引用逐项支持" in rejected.hint
    assert rejected.value == "否认发热"
    assert [(s.text, s.index) for s in rejected.source_spans] == [("否认", 0), ("发热", 1)]
    assert fields.past_history.status == "complete"
    assert fields.past_history.value == "既往身体健康"
    assert "否认发热" not in generator.generate_draft(fields)
    assert "待核对" in generator.generate_draft(fields)
    assert generator.safety_check(generator.generate_draft(fields), fields).blocked
    assert generator.attempt_count == 1


@pytest.mark.parametrize("audio", [False, True], ids=["text", "reviewed-audio"])
def test_multiple_citations_support_independent_clauses_without_rewriting(audio):
    spans = [SourceSpan(text="否认胸痛", index=0), SourceSpan(text="发热两天", index=1)]
    generator, fields = extract("否认胸痛；发热两天", spans, SOURCE, SEGMENTS if audio else [])

    accepted = fields.chief_complaint
    assert accepted.status == "complete"
    assert accepted.value == "否认胸痛；发热两天"
    assert [(s.text, s.index) for s in accepted.source_spans] == [("否认胸痛", 0), ("发热两天", 1)]
    assert accepted.value in generator.generate_draft(fields)
    assert generator.attempt_count == 1


def test_one_citation_still_supports_a_legitimate_partial_extract():
    _, fields = extract("发热", [SourceSpan(text="发热两天", index=1)], SOURCE, [])
    assert fields.chief_complaint.status == "complete"
    assert fields.chief_complaint.value == "发热"
    assert fields.chief_complaint.source_spans[0].text == "发热两天"
