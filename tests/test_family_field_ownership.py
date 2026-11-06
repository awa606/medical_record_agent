from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.field_grounding import ground_fields


def test_exactly_quoted_family_allergy_cannot_fill_patient_past_history():
    text = "我父亲有花生过敏"
    fields = MedicalRecordFields(past_history=MedicalField(value=text, status="complete", source_spans=[SourceSpan(text=text)]))
    result = ground_fields(fields, text)
    assert result.past_history.value == text
    assert result.past_history.status == "conflicting"
    assert "归属" in result.past_history.hint
    assert not result.past_history.confirmed_by_doctor


def test_patient_negative_allergy_remains_grounded_with_family_in_other_sentence():
    text = "我没有花生过敏。我父亲有花生过敏。"
    quote = "我没有花生过敏"
    fields = MedicalRecordFields(allergy_history=MedicalField(value=quote, status="complete", source_spans=[SourceSpan(text=quote, index=0)]))
    result = ground_fields(fields, text)
    assert result.allergy_history.status == "complete"
    assert result.allergy_history.value == quote


def test_invalid_decimal_citation_is_not_repaired_or_accepted():
    fields = MedicalRecordFields(chief_complaint=MedicalField(value="体温38.2℃", status="complete", source_spans=[SourceSpan(text="体温38..2℃")]))
    result = ground_fields(fields, "体温38.2℃")
    assert result.chief_complaint.status == "conflicting"
    assert result.chief_complaint.source_spans[0].text == "体温38..2℃"
