import pytest

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
                "role": "患者",
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


def test_live_allergy_patch_preserves_negation_and_ignores_family_fact() -> None:
    absent = build_live_clinical_snapshot(
        session_id="S-allergy-absent",
        stable_segments=[
            normalize_live_segment(
                {"segment_id": "seg-patient", "role": "患者", "text": "我没有花生过敏。"},
                sequence=1,
            )
        ],
        version=1,
        based_on_sequence=1,
        updated_at="2026-09-21T10:00:00+08:00",
    )
    family = build_live_clinical_snapshot(
        session_id="S-allergy-family",
        stable_segments=[
            normalize_live_segment(
                {"segment_id": "seg-family", "role": "患者", "text": "我父亲有花生过敏。"},
                sequence=1,
            )
        ],
        version=1,
        based_on_sequence=1,
        updated_at="2026-09-21T10:00:00+08:00",
    )

    assert absent["record_patch"]["allergy_history"]["value"] == "我没有花生过敏"
    assert "allergy_history" not in family["record_patch"]


def _snapshot(role: str | None, text: str) -> dict:
    return build_live_clinical_snapshot(
        session_id="S-live-subject",
        stable_segments=[{"segment_id": "seg-1", "role": role, "text": text}],
        version=1,
        based_on_sequence=1,
        updated_at="2026-10-16T10:00:00+08:00",
    )


@pytest.mark.parametrize("role", [None, "", "unknown", "待确认", "医生", "doctor", "患者"])
def test_live_questions_never_become_patient_facts_or_references(role) -> None:
    result = _snapshot(role, "有没有发热、咳嗽或药物过敏？")
    assert result["record_patch"] == {}
    for key in ("alerts", "missing_items", "differentials", "care_plan", "next_questions"):
        assert result[key] == []
    assert result["stable_segment_count"] == 1
    assert result["temporary"] is True


@pytest.mark.parametrize("role", [None, "", "unknown", "待确认", "其他"])
def test_live_unresolved_role_is_not_inferred_from_symptom_text(role) -> None:
    result = _snapshot(role, "患者发热咳嗽，体温38.2℃。")
    assert result["record_patch"] == {}
    assert result["differentials"] == result["care_plan"] == result["next_questions"] == []


@pytest.mark.parametrize("role", ["家属", "家长", "陪同人员"])
def test_live_family_own_symptoms_do_not_trigger_patient_reference(role) -> None:
    result = _snapshot(role, "我是孩子的妈妈，我自己有高血压，昨天发热咳嗽。")
    assert result["record_patch"] == {}
    assert result["differentials"] == result["care_plan"] == result["next_questions"] == []


@pytest.mark.parametrize("role", ["患者", "patient"])
def test_live_patient_symptoms_and_negation_remain_visible(role) -> None:
    result = _snapshot(role, "我发热咳嗽，体温38.2℃，没有药物过敏。")
    assert result["record_patch"]["chief_complaint"]["value"] == "发热伴咳嗽"
    assert "38.2℃" in result["record_patch"]["present_illness"]["value"]
    assert "没有药物过敏" in result["record_patch"]["allergy_history"]["value"]
    assert result["differentials"]


@pytest.mark.parametrize("role", ["家属", "家长", "陪同人员"])
def test_live_family_explicit_child_report_retains_child_not_parent_facts(role) -> None:
    text = "孩子发热咳嗽，体温38.2℃，没有药物过敏；我自己有高血压和胸痛。"
    result = _snapshot(role, text)
    patch = result["record_patch"]
    assert patch["chief_complaint"]["value"] == "发热伴咳嗽"
    assert "38.2℃" in patch["present_illness"]["value"]
    assert "没有药物过敏" in patch["allergy_history"]["value"]
    assert "我自己" not in patch["present_illness"]["value"]
    assert "past_history" not in patch
    assert "associated_symptoms" not in patch
    assert result["alerts"] == []
    assert result["differentials"]
    assert patch["present_illness"]["evidence_segment_ids"] == ["seg-1"]


def test_live_mixed_segment_keeps_only_explicit_patient_clause() -> None:
    result = _snapshot("患者", "我父亲有高血压和胸痛，我发热咳嗽。")
    assert "父亲" not in result["record_patch"]["present_illness"]["value"]
    assert "past_history" not in result["record_patch"]
    assert result["alerts"] == []
    assert result["record_patch"]["chief_complaint"]["value"] == "发热伴咳嗽"


def test_live_doctor_question_does_not_suppress_patient_answer_segment() -> None:
    result = build_live_clinical_snapshot(
        session_id="S-live-answer",
        stable_segments=[
            {"segment_id": "question", "role": "医生", "text": "有没有发热、咳嗽？"},
            {"segment_id": "answer", "role": "患者", "text": "我发热两天了，没有咳嗽。"},
        ],
        version=1,
        based_on_sequence=2,
        updated_at="2026-10-16T10:00:00+08:00",
    )
    patch = result["record_patch"]
    assert patch["chief_complaint"]["value"] == "发热"
    assert patch["present_illness"]["evidence_segment_ids"] == ["answer"]
    assert "有没有" not in patch["present_illness"]["value"]
    assert result["stable_segment_count"] == 2


def test_live_family_identity_does_not_make_following_self_report_a_child_fact() -> None:
    result = _snapshot("家属", "我是孩子的妈妈。昨天发热咳嗽，有高血压。")
    assert result["record_patch"] == {}
    assert result["differentials"] == result["care_plan"] == []


def test_live_family_can_explicitly_return_from_self_to_child_report() -> None:
    result = _snapshot("家属", "我自己有高血压。孩子发热咳嗽，没有药物过敏。")
    assert "past_history" not in result["record_patch"]
    assert "高血压" not in result["record_patch"]["present_illness"]["value"]
    assert "没有药物过敏" in result["record_patch"]["allergy_history"]["value"]


def test_live_doctor_explicit_patient_observation_keeps_source() -> None:
    result = _snapshot("医生", "患者体温38.2℃，咽部充血。")
    assert "38.2℃" in result["record_patch"]["present_illness"]["value"]
    assert "咽部充血" in result["record_patch"]["present_illness"]["value"]


def test_live_doctor_own_symptoms_after_patient_observation_are_excluded() -> None:
    result = _snapshot("医生", "患者咽部充血，我自己昨天发热，今天咳嗽。")
    assert result["record_patch"]["present_illness"]["value"] == "患者咽部充血"
    assert "chief_complaint" not in result["record_patch"]
    assert result["differentials"] == result["care_plan"] == []


def test_live_question_does_not_supply_child_subject_for_following_ambiguous_sentence() -> None:
    result = _snapshot("家属", "孩子发热吗？有咳嗽。")
    assert result["record_patch"] == {}
    assert result["differentials"] == result["care_plan"] == result["next_questions"] == []


def test_live_question_is_dropped_but_explicit_child_answer_is_kept() -> None:
    result = _snapshot("家属", "孩子发热吗？孩子没有发热，没有咳嗽，没有药物过敏。")
    assert "发热吗" not in result["record_patch"]["present_illness"]["value"]
    assert "chief_complaint" not in result["record_patch"]
    assert result["differentials"] == result["care_plan"] == result["next_questions"] == []
    assert "没有药物过敏" in result["record_patch"]["allergy_history"]["value"]


def test_live_filter_does_not_modify_original_transcript() -> None:
    source = {"segment_id": "original", "role": "家属", "text": "孩子发热，我自己有高血压。"}
    before = dict(source)
    result = build_live_clinical_snapshot(
        session_id="S-original-preserved", stable_segments=[source], version=1,
        based_on_sequence=1, updated_at="2026-10-16T10:00:00+08:00",
    )
    assert source == before
    assert result["record_patch"]["present_illness"]["value"] == "孩子发热"


@pytest.mark.parametrize("role,patient", [("家属", "孩子"), ("医生", "患者")])
@pytest.mark.parametrize("connector", ["但", "但是", "不过", "然而"])
@pytest.mark.parametrize("self_first", [True, False])
def test_live_contrast_boundary_keeps_patient_facts_in_both_orders(role, patient, connector, self_first) -> None:
    patient_clause = f"{patient}发热咳嗽"
    own_clause = "我自己有高血压和胸痛"
    parts = [own_clause, patient_clause] if self_first else [patient_clause, own_clause]
    result = _snapshot(role, connector.join(parts) + "。")
    patch = result["record_patch"]
    assert patch["chief_complaint"]["value"] == "发热伴咳嗽"
    assert patch["present_illness"]["value"] == patient_clause
    assert patch["present_illness"]["evidence_segment_ids"] == ["seg-1"]
    assert "past_history" not in patch
    assert "associated_symptoms" not in patch
    assert result["alerts"] == []
    assert result["differentials"]
