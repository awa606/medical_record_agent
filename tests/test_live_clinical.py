from app.services.live_clinical import (
    build_live_clinical_snapshot,
    merge_live_segment,
    merge_snapshot_if_newer,
    normalize_live_segment,
    should_emit_live_snapshot,
)


def test_live_clinical_snapshot_limits_summary_cards_to_three_items() -> None:
    segments = [
        normalize_live_segment(
            {
                "segment_id": "seg-1",
                "text": "患者发热咳嗽咳痰，体温四十度，伴胸痛和呼吸困难，咽痛乏力。",
            },
            sequence=1,
        )
    ]

    snapshot = build_live_clinical_snapshot(
        session_id="S-live",
        stable_segments=segments,
        version=2,
        based_on_sequence=1,
        updated_at="2026-07-29T12:00:00+00:00",
    )

    assert snapshot["status"] == "temporary"
    assert snapshot["version"] == 2
    assert snapshot["record_patch"]["chief_complaint"]["temporary"] is True
    assert len(snapshot["missing_items"]) <= 3
    assert len(snapshot["differentials"]) <= 3
    assert len(snapshot["care_plan"]) <= 3
    assert snapshot["alerts"][0]["evidence_segment_ids"] == ["seg-1"]


def test_live_clinical_segment_merge_is_idempotent_and_monotonic() -> None:
    state: dict = {}
    first = normalize_live_segment({"segment_id": "seg-1", "text": "发热"}, sequence=0)
    duplicate = normalize_live_segment({"segment_id": "seg-1", "text": "发热"}, sequence=0)
    second = normalize_live_segment({"segment_id": "seg-2", "text": "咳嗽"}, sequence=1)

    assert merge_live_segment(state, first) is True
    assert merge_live_segment(state, duplicate) is False
    assert merge_live_segment(state, second) is True
    assert [item["sequence"] for item in state["stable_segments"]] == [0, 1]


def test_live_clinical_emits_first_snapshot_then_throttles() -> None:
    assert should_emit_live_snapshot({}, based_on_sequence=0)
    state = {"version": 1, "based_on_sequence": 0}

    assert should_emit_live_snapshot(state, based_on_sequence=2) is False
    assert should_emit_live_snapshot(state, based_on_sequence=3) is True


def test_older_live_clinical_result_cannot_overwrite_newer_snapshot() -> None:
    current = {"version": 4, "record_patch": {"chief_complaint": {"value": "new"}}}
    older = {"version": 3, "record_patch": {"chief_complaint": {"value": "old"}}}
    newer = {"version": 5, "record_patch": {"chief_complaint": {"value": "newer"}}}

    assert merge_snapshot_if_newer(current, older) is current
    assert merge_snapshot_if_newer(current, newer) is newer
