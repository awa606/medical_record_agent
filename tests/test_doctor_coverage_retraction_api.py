"""Independent HTTP regression for the misleading withdrawn-fever export note.

Uses an isolated recorded Provider fixture; no ASR/model/network call. The old
R1 and its incorrect coverage finding remain immutable historical evidence.
"""
from copy import deepcopy
from io import BytesIO
import json
from xml.etree import ElementTree
from zipfile import ZipFile

from app.db import get_active_approval_for_task, get_record_revision, get_task, list_approvals_for_task
from app.schemas import SourceSpan
from tests.approval_helpers import review_payload_for_fields
from tests.test_doctor_negative_paraphrase_api import (
    SOURCE, approve_current, fields_for, recorded_review,
)


FALSE_POSITIVE_GAP = "已引用但未写入：发热（有）"
REAL_DURATION_GAP = "症状持续时间未提及"


def exported_text(client, task_id):
    response = client.post(f"/api/tasks/{task_id}/export")
    assert response.status_code == 200, response.text
    downloaded = client.get(f"/api/tasks/{task_id}/exports/docx")
    assert downloaded.status_code == 200, downloaded.text
    with ZipFile(BytesIO(downloaded.content)) as archive:
        xml = ElementTree.fromstring(archive.read("word/document.xml"))
    return "".join(xml.itertext())


def test_review_recomputes_withdrawn_symptom_coverage_without_erasing_real_gaps(recorded_review):
    client, task_id, provider, first_revision = recorded_review
    original_r1 = deepcopy(first_revision)
    fields = fields_for(task_id)
    assert FALSE_POSITIVE_GAP in fields.present_illness.missing_elements
    assert [span.text for span in fields.present_illness.source_spans] == ["刚才说发烧", "其实没有发热"]
    assert [span.index for span in fields.present_illness.source_spans] == [0, 0]
    original_other_missing = {key: deepcopy(getattr(fields, key).model_dump()) for key in (
        "past_history", "allergy_history", "physical_exam", "previous_treatment", "accompanying_symptoms",
    )}
    assert all(value["missing"] for value in original_other_missing.values())

    # Match the actual UI choice: one whole source sentence, not a fabricated
    # narrower citation. HPI still keeps the exact two original spans.
    fields.chief_complaint.value = "否认发热"
    fields.chief_complaint.source_spans = [SourceSpan(text=SOURCE.rstrip("。"), index=0)]
    # Duration is genuinely absent in this source; removing our false coverage
    # finding must not clear an unrelated, explicit information gap.
    fields.present_illness.missing_elements.append(REAL_DURATION_GAP)
    payload = review_payload_for_fields(task_id, fields)
    payload["source_corrected_fields"] = ["chief_complaint"]
    saved_r2 = client.post(f"/api/tasks/{task_id}/review", json=payload)
    assert saved_r2.status_code == 200, saved_r2.text
    r2_result = saved_r2.json()["result_json"]
    r2_fields = r2_result["fields"]
    assert FALSE_POSITIVE_GAP not in r2_fields["present_illness"]["missing_elements"], r2_fields["present_illness"]
    assert REAL_DURATION_GAP in r2_fields["present_illness"]["missing_elements"]
    assert r2_fields["chief_complaint"]["value"] == "否认发热"
    assert r2_fields["chief_complaint"]["status"] != "conflicting"
    for key, original in original_other_missing.items():
        assert r2_fields[key] == original
    assert get_record_revision(original_r1["id"]) == original_r1
    assert client.post(f"/api/tasks/{task_id}/export").status_code == 400
    r2_id = saved_r2.json()["current_record_revision_id"]
    r2_row = deepcopy(get_record_revision(r2_id))

    approved_r2 = approve_current(client, task_id)
    assert approved_r2.status_code == 200, approved_r2.text
    assert get_active_approval_for_task(task_id)["revision_id"] == r2_id
    r2_docx = exported_text(client, task_id)
    assert "否认发热" in r2_docx and "刚才说发烧；其实没有发热" in r2_docx
    assert FALSE_POSITIVE_GAP not in r2_docx
    assert REAL_DURATION_GAP in r2_docx
    assert json.loads(get_task(task_id)["result_json"])["export_event"]["revision_id"] == r2_id

    # Only HPI changes in the next revision. The already proven chief source
    # correction survives; the old approval must not cover this new content.
    later = fields_for(task_id)
    later.present_illness.value = "其实没有发热"
    saved_r3 = client.post(f"/api/tasks/{task_id}/review", json=review_payload_for_fields(task_id, later))
    assert saved_r3.status_code == 200, saved_r3.text
    r3_fields = saved_r3.json()["result_json"]["fields"]
    # Normalizing a partial field may restore its generic missing-information
    # label. Trust must instead remain pinned to the content and real evidence.
    for key in ("value", "status", "source_spans", "fact_ids", "doctor_review_note",
                "confirmed_by_doctor", "doctor_review_status"):
        assert r3_fields["chief_complaint"][key] == r2_fields["chief_complaint"][key]
    assert FALSE_POSITIVE_GAP not in r3_fields["present_illness"]["missing_elements"]
    assert REAL_DURATION_GAP in r3_fields["present_illness"]["missing_elements"]
    assert get_active_approval_for_task(task_id) is None
    assert list_approvals_for_task(task_id)[0]["status"] == "invalidated"
    assert client.post(f"/api/tasks/{task_id}/export").status_code == 400
    assert get_record_revision(r2_id) == r2_row
    assert get_record_revision(original_r1["id"]) == original_r1

    approved_r3 = approve_current(client, task_id)
    assert approved_r3.status_code == 200, approved_r3.text
    r3_id = saved_r3.json()["current_record_revision_id"]
    assert get_active_approval_for_task(task_id)["revision_id"] == r3_id
    r3_docx = exported_text(client, task_id)
    assert "否认发热" in r3_docx and "其实没有发热" in r3_docx
    assert "刚才说发烧；其实没有发热" not in r3_docx
    assert FALSE_POSITIVE_GAP not in r3_docx
    assert REAL_DURATION_GAP in r3_docx
    assert json.loads(get_task(task_id)["result_json"])["export_event"]["revision_id"] == r3_id
    assert get_record_revision(original_r1["id"]) == original_r1
    assert provider.calls == 1  # Recorded fixture only, no regeneration.
