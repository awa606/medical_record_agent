"""Research adapter contracts; these are not model-quality claims."""
import pytest

from app.services.field_grounding import FIELD_KEYS, ground_fields
from scripts.experiments.evidence_selection import catalog, map_selection


def empty():
    return {key: [] for key in FIELD_KEYS}


@pytest.mark.parametrize("mode", ["unknown", "foreign", "duplicate", "number", "missing_key", "extra_key"])
def test_selection_rejects_invalid_contract(mode):
    _, rows = catalog("患者：没有花生过敏。")
    selection = empty()
    if mode == "unknown": selection["chief_complaint"] = ["invalid"]
    if mode == "foreign": selection["chief_complaint"] = [catalog("患者：胸痛")[1][0].id]
    if mode == "duplicate": selection["chief_complaint"] = [rows[0].id] * 2
    if mode == "number": selection["chief_complaint"] = [0]
    if mode == "missing_key": del selection["chief_complaint"]
    if mode == "extra_key": selection["auto_approve"] = True
    with pytest.raises(ValueError): map_selection(selection, rows)


def test_original_negation_units_and_order_not_rewritten():
    safe, rows = catalog("患者：没有花生过敏。患者：服用5mg。")
    selection = empty(); selection["present_illness"] = [rows[1].id, rows[0].id]
    result = map_selection(selection, rows)
    assert result.present_illness.value == "没有花生过敏；服用5mg"
    assert [s.index for s in result.present_illness.source_spans] == [0, 1]
    assert result.present_illness.confidence is None
    assert result.past_history.missing


@pytest.mark.parametrize("text", ["医生：有没有胸痛？", "患者：我父亲有花生过敏。"])
def test_wrong_role_and_subject_still_conflict(text):
    safe, rows = catalog(text); selection = empty(); selection["chief_complaint"] = [rows[0].id]
    assert ground_fields(map_selection(selection, rows), safe).chief_complaint.status == "conflicting"


def test_duplicate_audio_text_does_not_invent_identity():
    trusted = [{"segment_id": "p1", "role": "患者", "text": "头痛"},
               {"segment_id": "p2", "role": "患者", "text": "头痛"}]
    safe, rows = catalog("患者：头痛。患者：头痛。", trusted)
    assert rows[0].id != rows[1].id and rows[0].segment_id is None
    selection = empty(); selection["chief_complaint"] = [rows[0].id]
    assert ground_fields(map_selection(selection, rows), safe, trusted).chief_complaint.status == "conflicting"
