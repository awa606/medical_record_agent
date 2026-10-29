from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.records import PreviewRecordRequest, preview_record
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.llm.mock_provider import MockLLMProvider


def _segment(speaker_id="spk1", **overrides):
    return {
        "segment_id": f"segment-{speaker_id}",
        "speaker_id": speaker_id,
        "role": "患者",
        "role_confidence": 0.99,
        "role_source": "manual_speaker_map",
        "reviewed_by_doctor": True,
        "text": "我发热三天。",
        **overrides,
    }


@pytest.fixture
def preview_generator_spy():
    # A local deterministic provider keeps both the red and green runs offline.
    generator = LLMRecordGenerator(provider=MockLLMProvider())
    with patch("app.api.records.create_llm_record_generator", return_value=generator) as factory:
        with patch.object(generator, "extract_fields", wraps=generator.extract_fields) as extraction:
            yield factory, extraction


@pytest.mark.parametrize(
    "segments",
    [
        [_segment(role_confidence=0.86, role_source="global_two_party_constraint", reviewed_by_doctor=False)],
        [_segment(), _segment("spk2", role=None, role_source="unassigned", reviewed_by_doctor=False)],
        [_segment(role_source="unassigned", reviewed_by_doctor=False, needs_review=True)],
        [_segment(), _segment("spk2", role="待确认", role_source="speaker_context_rules", reviewed_by_doctor=False)],
    ],
    ids=["low-confidence", "mapped-and-unmapped", "untrusted-awaiting-review", "mapped-and-pending-role"],
)
def test_preview_rejects_incomplete_stable_role_quality_before_provider(segments, preview_generator_spy):
    factory, extraction = preview_generator_spy
    error = None
    try:
        preview_record(PreviewRecordRequest(conversation_text="患者：我发热三天。", segments=segments))
    except HTTPException as exc:
        error = exc

    # Check the cost boundary even when the old implementation returns success.
    extraction.assert_not_called()
    factory.assert_not_called()
    assert error is not None
    assert error.status_code == 409
    assert error.detail["role_quality"]["status"] == "needs_review"
    assert error.detail["policy_version"] == "speaker-role-policy-v1"
    assert error.detail["pending_confirmation"]


def test_preview_with_no_mapped_stable_role_still_rejects_before_provider(preview_generator_spy):
    factory, extraction = preview_generator_spy
    with pytest.raises(HTTPException) as raised:
        preview_record(PreviewRecordRequest(
            conversation_text="说话人 A：我发热三天。",
            segments=[_segment(role=None, role_source="unassigned", reviewed_by_doctor=False)],
        ))
    assert raised.value.status_code == 409
    assert "角色映射" in raised.value.detail
    extraction.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize("role_source,reviewed", [("manual_speaker_map", True), ("speaker_context_rules", False)])
def test_preview_accepts_roles_that_pass_existing_policy(role_source, reviewed, preview_generator_spy):
    factory, extraction = preview_generator_spy
    response = preview_record(PreviewRecordRequest(
        conversation_text="患者：我发热三天。",
        segments=[_segment(role_source=role_source, reviewed_by_doctor=reviewed)],
    ))
    assert response.status == "preview_ready"
    assert response.segment_count == 1
    assert not response.quality_preview["export_allowed"]
    factory.assert_called_once_with()
    extraction.assert_called_once_with("[患者] 我发热三天。")


def test_preview_ignores_unmapped_provisional_segment_before_role_quality(preview_generator_spy):
    _, extraction = preview_generator_spy
    response = preview_record(PreviewRecordRequest(
        conversation_text="临时输入不得进入抽取",
        segments=[_segment(), _segment("spk2", role=None, provisional=True, reviewed_by_doctor=False)],
    ))
    assert response.status == "preview_ready"
    assert response.segment_count == 1
    extraction.assert_called_once_with("[患者] 我发热三天。")


def test_preview_without_segments_keeps_text_only_compatibility(preview_generator_spy):
    factory, extraction = preview_generator_spy
    text = "[患者] 我发热三天。"
    response = preview_record(PreviewRecordRequest(conversation_text=text, source="text_preview"))
    assert response.status == "preview_ready"
    assert response.segment_count == 0
    assert response.source == "text_preview"
    factory.assert_called_once_with()
    extraction.assert_called_once_with(text)
