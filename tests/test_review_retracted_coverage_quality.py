"""Review-only coverage correction; no models, services or production writes."""
from copy import deepcopy

import pytest

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.field_alignment import (
    COVERAGE_HINT, MANUAL_REVIEW_HINT, coverage_missing,
    refresh_existing_coverage_hints, validate_field_alignment,
)


SOURCE = "患者：刚才说发烧，其实没有发热。"
FALSE_GAP = "已引用但未写入：发热（有）"


def quotes(positive="刚才说发烧", negative="其实没有发热", *, index=0):
    return [SourceSpan(text=positive, index=index), SourceSpan(text=negative, index=index)]


@pytest.mark.parametrize("value", ["其实没有发热", "没有发热", "否认发热", "刚才说发烧；其实没有发热"])
def test_review_full_source_removes_only_explicitly_retracted_positive_gap(value):
    spans = quotes()
    original = [s.model_dump() for s in spans]
    assert FALSE_GAP not in coverage_missing("present_illness", value, spans, source=SOURCE)
    assert [s.model_dump() for s in spans] == original


def test_review_without_authoritative_full_source_keeps_old_coverage_behavior():
    assert FALSE_GAP in coverage_missing("present_illness", "其实没有发热", quotes())
    assert FALSE_GAP in coverage_missing("present_illness", "其实没有发热", quotes(), source=None)


@pytest.mark.parametrize("value", ["发烧；没有发热", "发烧；其实没有发热"])
def test_review_bare_positive_is_not_a_retold_corrected_claim(value):
    assert FALSE_GAP in coverage_missing("present_illness", value, quotes(), source=SOURCE)


@pytest.mark.parametrize("source,positive,negative,value", [
    ("患者：发烧，没有发热。", "发烧", "没有发热", "没有发热"),
    ("患者：刚才说今天发烧，其实没有发热。", "刚才说今天发烧", "其实没有发热", "没有发热"),
    ("患者：刚才说发烧，其实没有胸痛。", "刚才说发烧", "其实没有胸痛", "没有胸痛"),
    ("患者：刚才说发烧，其实可能没有发热。", "刚才说发烧", "其实可能没有发热", "没有发热"),
    ("患者：刚才说发烧，其实不是没有发热。", "刚才说发烧", "其实不是没有发热", "没有发热"),
    ("患者：刚才说发烧，其实没有发热的是他。", "刚才说发烧", "其实没有发热的是他", "没有发热"),
    ("医生：刚才说发烧，其实没有发热？", "刚才说发烧", "其实没有发热", "没有发热"),
    ("患者：刚才说发烧，其实没有发热，又发烧了。", "刚才说发烧", "其实没有发热", "没有发热"),
    (SOURCE + "患者：刚才说发烧，其实没有发热。", "刚才说发烧", "其实没有发热", "没有发热"),
    (SOURCE, "刚才说发烧", "其实没有发热", "没有胸痛"),
])
def test_review_doubtful_subject_time_or_retraction_keeps_positive_gap(source, positive, negative, value):
    assert FALSE_GAP in coverage_missing("present_illness", value, quotes(positive, negative), source=source)


@pytest.mark.parametrize("index", [None, 1, 99])
def test_review_must_uniquely_match_real_span_index(index):
    assert FALSE_GAP in coverage_missing("present_illness", "其实没有发热", quotes(index=index), source=SOURCE)


def test_review_does_not_rewrite_or_accept_nonexact_alias_quote():
    spans = quotes(positive="刚才说发热")
    assert FALSE_GAP in coverage_missing("present_illness", "其实没有发热", spans, source=SOURCE)


def test_review_actual_negative_and_other_symptoms_still_need_coverage():
    source = "患者：刚才说发烧，其实没有发热，咳嗽。"
    spans = [*quotes(), SourceSpan(text="咳嗽", index=0)]
    missing = coverage_missing("present_illness", "其实没有发热", spans, source=source)
    assert FALSE_GAP not in missing
    assert "已引用但未写入：咳嗽（有）" in missing
    absent_missing = coverage_missing("present_illness", "咳嗽", spans, source=source)
    assert "已引用但未写入：发热（无）" in absent_missing


def test_review_manual_revision_keeps_provenance_partial_and_unrelated_gap():
    field = MedicalField(value="其实没有发热", status="partial", hint=MANUAL_REVIEW_HINT,
        source_spans=quotes(), fact_ids=["old-positive", "true-negative"],
        missing_elements=["症状持续时间未提及", FALSE_GAP],
        doctor_review_note="manual_doctor_edit_v1: 医生手工修改")
    fields = MedicalRecordFields(present_illness=field)
    before = deepcopy(fields.model_dump())
    refreshed = refresh_existing_coverage_hints(fields, source=SOURCE)
    actual = refreshed.present_illness
    assert fields.model_dump() == before
    assert actual.value == field.value and actual.fact_ids == field.fact_ids
    assert actual.source_spans == field.source_spans
    assert actual.missing_elements == ["症状持续时间未提及"]
    assert actual.hint == MANUAL_REVIEW_HINT and actual.status == "partial"
    assert actual.doctor_review_note == field.doctor_review_note
    assert not actual.confirmed_by_doctor and actual.doctor_review_status == "pending"


def test_review_owned_coverage_only_clears_its_proven_obsolete_item():
    fields = MedicalRecordFields(present_illness=MedicalField(
        value="其实没有发热", status="partial", hint=COVERAGE_HINT,
        source_spans=quotes(), missing_elements=[FALSE_GAP, "症状持续时间未提及"]))
    actual = refresh_existing_coverage_hints(fields, source=SOURCE).present_illness
    assert actual.missing_elements == ["症状持续时间未提及"]
    assert actual.status == "partial" and actual.hint is None


def test_review_does_not_touch_other_validators_hint_or_conflicting_fields():
    for hint, status in [("其他校验器提示", "partial"), (COVERAGE_HINT, "conflicting")]:
        fields = MedicalRecordFields(present_illness=MedicalField(
            value="其实没有发热", status=status, hint=hint,
            source_spans=quotes(), missing_elements=[FALSE_GAP]))
        assert refresh_existing_coverage_hints(fields, source=SOURCE).model_dump() == fields.model_dump()


def test_initial_model_alignment_does_not_get_review_source_relaxation():
    fields = MedicalRecordFields(present_illness=MedicalField(value="其实没有发热", source_spans=quotes()))
    checked, _ = validate_field_alignment(fields)
    assert FALSE_GAP in checked.present_illness.missing_elements
    assert checked.present_illness.status == "partial"
