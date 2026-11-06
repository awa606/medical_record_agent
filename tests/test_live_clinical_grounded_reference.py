"""Live text may expose facts and gaps, never unsupported clinical decisions."""
from copy import deepcopy

import pytest

from app.services.live_clinical import build_live_clinical_snapshot


def snapshot(*texts: str, role: str = "患者") -> dict:
    return build_live_clinical_snapshot(
        session_id="live-grounding", version=1, based_on_sequence=len(texts),
        updated_at="2026-11-06T12:00:00+08:00",
        stable_segments=[
            {"segment_id": f"s{i}", "role": role, "text": text}
            for i, text in enumerate(texts, 1)
        ],
    )


@pytest.mark.parametrize("text", ["我咽痛。", "我发热咳嗽。", "我胸痛气短。"])
def test_live_keywords_do_not_issue_diagnosis_or_test_recommendations(text):
    result = snapshot(text)
    assert result["differentials"] == []
    assert result["care_plan"] == []
    assert result["record_patch"]


@pytest.mark.parametrize("text", [
    "我发热两天，最高体温38.2℃。",
    "孩子发热两天，最高体温三十八点二度。",
])
def test_known_temperature_and_fever_duration_are_not_requested_again(text):
    result = snapshot(text, role="家属" if "孩子" in text else "患者")
    assert not any(i["id"] == "missing-temperature" for i in result["missing_items"])
    assert not any(i["id"] == "next-temperature" for i in result["next_questions"])


@pytest.mark.parametrize("text,needed,known", [
    ("我发热两天。", "体温", "持续"),
    ("我发热，最高体温38.2℃。", "持续", "体温"),
])
def test_partial_answer_only_asks_the_unanswered_part(text, needed, known):
    result = snapshot(text)
    question = next(i["question"] for i in result["next_questions"] if i["id"] == "next-temperature")
    assert needed in question
    assert known not in question


def test_cough_duration_does_not_answer_fever_duration():
    result = snapshot("我咳嗽两天，发热，最高体温38.2℃。")
    question = next(i["question"] for i in result["next_questions"] if i["id"] == "next-temperature")
    assert "持续" in question


def test_uncertain_temperature_does_not_silently_count_as_measured():
    result = snapshot("我发热两天，体温可能38.2℃，没有量。")
    assert any(i["id"] == "next-temperature" for i in result["next_questions"])


def test_negative_fever_does_not_generate_temperature_questions():
    result = snapshot("我咳嗽，没有发热。")
    assert not any(i["id"] == "next-temperature" for i in result["next_questions"])
    assert result["record_patch"]["chief_complaint"]["value"] == "咳嗽"


@pytest.mark.parametrize("text", ["我咳嗽，没有痰。", "我干咳。", "我咳嗽，有少量白痰。"])
def test_answered_sputum_question_is_not_repeated(text):
    result = snapshot(text)
    assert not any(i["id"] == "next-sputum" for i in result["next_questions"])
    assert not any(i["id"] == "missing-sputum" for i in result["missing_items"])


def test_each_field_and_alert_uses_its_own_source_even_after_five_segments():
    result = snapshot(
        "我发热两天。", "我咳嗽。", "我昨晚没睡好。", "我今天来就诊。",
        "我现在没有头痛。", "我没有药物过敏。", "我有胸痛。",
    )
    patch = result["record_patch"]
    assert patch["chief_complaint"]["evidence_segment_ids"] == ["s1", "s2"]
    assert patch["allergy_history"]["evidence_segment_ids"] == ["s6"]
    assert patch["associated_symptoms"]["evidence_segment_ids"] == ["s7"]
    alert = next(i for i in result["alerts"] if i["id"] == "danger-breathing")
    assert alert["evidence_segment_ids"] == ["s7"]


def test_long_summary_only_cites_segments_actually_displayed():
    result = snapshot("我" + "昨晚没有休息好，" * 24, "我没有药物过敏。")
    assert result["record_patch"]["present_illness"]["evidence_segment_ids"] == ["s1"]
    assert result["record_patch"]["allergy_history"]["evidence_segment_ids"] == ["s2"]


def test_question_and_family_answer_do_not_fill_patient_gaps():
    result = build_live_clinical_snapshot(
        session_id="live-filtered", version=1, based_on_sequence=3, updated_at="now",
        stable_segments=[
            {"segment_id": "q", "role": "医生", "text": "发热两天，体温38.2℃吗？"},
            {"segment_id": "f", "role": "家属", "text": "我自己发热两天，体温38.2℃。"},
            {"segment_id": "p", "role": "患者", "text": "我发热。"},
        ],
    )
    q = next(i["question"] for i in result["next_questions"] if i["id"] == "next-temperature")
    assert "体温" in q and "持续" in q
    assert result["record_patch"]["chief_complaint"]["evidence_segment_ids"] == ["p"]


def test_source_segments_are_not_modified():
    segments = [{"segment_id": "p", "role": "患者", "text": "我发热两天。"}]
    before = deepcopy(segments)
    build_live_clinical_snapshot(session_id="immutable", version=1, based_on_sequence=1,
                                 updated_at="now", stable_segments=segments)
    assert segments == before


def test_uncertain_sputum_description_still_needs_clarification():
    result = snapshot("我咳嗽，可能有少量白痰。")
    assert any(item["id"] == "next-sputum" for item in result["next_questions"])


def test_unknown_exposure_is_not_treated_as_a_negative_answer():
    result = snapshot("我发热两天，最高体温38.2度，接触史不清楚。")
    assert any(item["id"] == "next-exposure" for item in result["next_questions"])
