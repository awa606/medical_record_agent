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
