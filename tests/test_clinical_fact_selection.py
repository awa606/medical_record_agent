"""Contract integrity, field eligibility and scoring; not model-quality tests."""
import pytest

from app.services.field_grounding import FIELD_KEYS, ground_fields
from scripts.experiments.clinical_fact_selection import catalog, map_selection
from scripts.experiments.run_clinical_fact_selection import score


def empty():
    return {key: [] for key in FIELD_KEYS}


def test_mapping_preserves_child_subject_unknown_allergy_and_original_numbers():
    source = "医生：孩子多大？有什么不舒服？有没有药物过敏？\n家长：孩子八岁，咳嗽两天，咽痛，最高体温三十八点二度。我自己有高血压，孩子的药物过敏我不清楚。"
    safe, rows = catalog(source)
    selection = {key: [r.id for r in rows if key in r.allowed_fields] for key in FIELD_KEYS}
    fields = map_selection(selection, rows)
    assert fields.past_history.missing
    assert "孩子" in fields.present_illness.value
    assert "三十八点二" in fields.present_illness.value
    assert fields.allergy_history.status == "partial"
    assert score("P01", safe, fields)["passed"]
    checked = ground_fields(fields.model_copy(deep=True), safe)
    assert score("P01", safe, checked)["passed"]
    assert all(span.text in source for key in FIELD_KEYS for span in getattr(fields, key).source_spans)


@pytest.mark.parametrize("source", ["医生：有没有胸痛？有没有药物过敏？", "患者：我父亲有高血压。", "家长：我自己有药物过敏。"])
def test_questions_and_other_person_facts_are_not_eligible(source):
    _, rows = catalog(source)
    assert rows and all(not row.allowed_fields for row in rows)
    bad = empty()
    bad["past_history"] = [rows[0].id]
    with pytest.raises(ValueError, match="FIELD_OR_SUBJECT"):
        map_selection(bad, rows)


def test_mapper_does_not_fill_unselected_facts():
    _, rows = catalog("患者：发热两天，伴咳嗽和咽痛。")
    selected = empty()
    selected["chief_complaint"] = [next(r.id for r in rows if "发热" in r.text)]
    fields = map_selection(selected, rows)
    assert fields.present_illness.missing
    assert fields.accompanying_symptoms.missing
    assert "咳嗽" not in fields.chief_complaint.value


def test_duplicate_quotes_keep_distinct_sentence_ids_and_cross_input_ids_are_rejected():
    _, rows = catalog("患者：咳嗽两天。患者：咳嗽两天。")
    ids = [r.id for r in rows if "咳嗽" in r.text]
    assert len(ids) == len(set(ids)) == 2
    selected = empty()
    selected["present_illness"] = [ids[1]]
    assert map_selection(selected, rows).present_illness.source_spans[0].index == 1
    _, other = catalog("患者：咳嗽三天。")
    with pytest.raises(ValueError, match="FOREIGN_OR_UNKNOWN"):
        map_selection(selected, other)


def test_unknown_expression_stays_in_catalog_for_review():
    _, rows = catalog("患者：出现罕见症状甲。")
    assert len(rows) == 1 and "罕见症状甲" in rows[0].text
    assert rows[0].types == () and rows[0].allowed_fields == ()


def test_score_independently_rejects_family_history_even_when_quote_is_exact():
    source = "患者：我父亲有高血压。我自己发热两天，伴咳嗽和咽痛，最高体温三十八点二度，没有胸痛，也没有药物过敏史。"
    safe, rows = catalog(source)
    fields = map_selection({key: [r.id for r in rows if key in r.allowed_fields] for key in FIELD_KEYS}, rows)
    assert score("I01", safe, fields)["passed"]
    from app.schemas import MedicalField, SourceSpan
    fields.past_history = MedicalField(value="我父亲有高血压", source_spans=[SourceSpan(text="我父亲有高血压", index=0)])
    result = score("I01", safe, fields)
    assert not result["passed"]
    assert "past_history:wrong_patient_subject" in result["errors"]


@pytest.mark.parametrize("effect", ["没有效果", "后的效果不清楚"])
def test_catalog_actual_intake_is_not_removed_by_negative_or_unknown_effect(effect):
    source = f"患者：服用布洛芬{effect}。"
    safe, rows = catalog(source)
    row = next(r for r in rows if "服用布洛芬" in r.text)
    assert "previous_treatment" in row.allowed_fields
    selected = empty()
    selected["previous_treatment"] = [row.id]
    mapped = map_selection(selected, rows)
    assert mapped.previous_treatment.value == row.text
    assert [s.text for s in mapped.previous_treatment.source_spans] == [row.text]
    assert mapped.present_illness.missing  # Eligibility must not auto-fill another field.
    checked = ground_fields(mapped.model_copy(deep=True), safe)
    assert checked.previous_treatment.status != "conflicting"
    assert checked.previous_treatment.value == row.text


def test_catalog_proposed_drug_does_not_borrow_adjacent_actual_intake():
    source = "患者：医生建议服用布洛芬，后来服用了对乙酰氨基酚。"
    safe, rows = catalog(source)
    proposal = next(r for r in rows if "建议" in r.text)
    actual = next(r for r in rows if "后来" in r.text)
    assert "previous_treatment" not in proposal.allowed_fields
    assert "previous_treatment" in actual.allowed_fields
    wrong = empty()
    wrong["previous_treatment"] = [proposal.id]
    with pytest.raises(ValueError, match="FIELD_OR_SUBJECT"):
        map_selection(wrong, rows)
    selected = empty()
    selected["previous_treatment"] = [actual.id]
    mapped = map_selection(selected, rows)
    assert mapped.previous_treatment.value == "后来服用了对乙酰氨基酚"
    assert "布洛芬" not in mapped.previous_treatment.value
    checked = ground_fields(mapped.model_copy(deep=True), safe)
    assert checked.previous_treatment.status != "conflicting"


def test_catalog_adjacent_same_symptom_keeps_each_assertion_and_eligibility():
    source = "患者：昨天没有胸痛，今天胸痛。"
    safe, rows = catalog(source)
    previous = next(r for r in rows if "昨天" in r.text)
    current = next(r for r in rows if "今天" in r.text)
    assert previous.assertion == "absent"
    assert current.assertion == "present"
    for key in ("chief_complaint", "accompanying_symptoms"):
        assert key not in previous.allowed_fields
        assert key in current.allowed_fields
    assert "present_illness" in previous.allowed_fields
    assert "present_illness" in current.allowed_fields
    selected = empty()
    selected["present_illness"] = [previous.id, current.id]
    mapped = map_selection(selected, rows)
    assert mapped.present_illness.value == "昨天没有胸痛；今天胸痛"
    assert [s.text for s in mapped.present_illness.source_spans] == [previous.text, current.text]
    checked = ground_fields(mapped.model_copy(deep=True), safe)
    assert checked.present_illness.status != "conflicting"


@pytest.mark.parametrize("source", [
    "患者：没有服用布洛芬。",
    "患者：医生建议服用布洛芬。",
    "患者：不确定是否服用布洛芬。",
    "家长：我自己服用了布洛芬。",
])
def test_catalog_non_actual_or_other_person_intake_cannot_fill_previous_treatment(source):
    _, rows = catalog(source)
    assert rows
    for row in rows:
        assert "previous_treatment" not in row.allowed_fields
        invalid = empty()
        invalid["previous_treatment"] = [row.id]
        with pytest.raises(ValueError, match="FIELD_OR_SUBJECT"):
            map_selection(invalid, rows)


def test_catalog_parent_reported_child_actual_intake_stays_eligible():
    source = "家长：孩子八岁，已经服用布洛芬。"
    safe, rows = catalog(source)
    actual = next(r for r in rows if "服用布洛芬" in r.text)
    assert actual.experiencer == "patient"
    assert "previous_treatment" in actual.allowed_fields
    selected = empty()
    selected["previous_treatment"] = [actual.id]
    mapped = map_selection(selected, rows)
    assert "孩子八岁" in mapped.previous_treatment.value
    assert "已经服用布洛芬" in mapped.previous_treatment.value
    assert all(span.text in safe for span in mapped.previous_treatment.source_spans)
    checked = ground_fields(mapped.model_copy(deep=True), safe)
    assert checked.previous_treatment.status != "conflicting"
    assert checked.previous_treatment.value == mapped.previous_treatment.value


def test_catalog_scope_fix_does_not_upgrade_unresolved_allergy_to_present():
    source = "患者：药物过敏我不清楚，药物过敏情况以后再问。"
    _, rows = catalog(source)
    allergy_rows = [row for row in rows if "allergy" in row.types]
    assert len(allergy_rows) == 2
    assert all(row.assertion == "uncertain" for row in allergy_rows)
    selected = empty()
    selected["allergy_history"] = [row.id for row in allergy_rows]
    mapped = map_selection(selected, rows)
    assert mapped.allergy_history.status == "partial"
    assert all(row.text in mapped.allergy_history.value for row in allergy_rows)
