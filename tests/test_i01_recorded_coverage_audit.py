"""Offline auditor controls; fixture selections are never model results."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import socket

import pytest

from scripts.experiments.audit_cross_field_coverage import (
    AuditStopped, audit_archive, audit_record, audit_selection, sha256_file, _write_private,
)
from scripts.experiments.clinical_fact_selection import FactUnit, map_selection, selection_schema
from scripts.experiments.run_clinical_fact_selection import EXPECTED, score
from app.services.field_grounding import FIELD_KEYS


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / ".artifacts/fact-selection-20261012-110022/compare"
TRACE = ROOT / ".artifacts/doctor-negative-20261027-r1/i01-offline-trace.json"


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("AUDIT_MUST_NOT_CONNECT")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def audit_fixture():
    # Constructed auditor controls, not an archived user or model response.
    source = "患者：发热两天，咳嗽咽痛。医生：有没有头痛？家属：我自己有高血压。"
    prefix = hashlib.sha256(source.encode()).hexdigest()[:16]
    rows = [
        FactUnit(f"{prefix}:s0:3-7", 0, 3, 7, "发热两天", "患者", "patient", "present",
                 ("duration", "symptom"), ("chief_complaint", "present_illness")),
        FactUnit(f"{prefix}:s0:8-12", 0, 8, 12, "咳嗽咽痛", "患者", "patient", "present",
                 ("symptom",), ("chief_complaint", "present_illness", "accompanying_symptoms")),
        FactUnit(f"{prefix}:s1:3-9", 1, 3, 9, "有没有头痛", "医生", "patient", "unknown", (), ()),
        FactUnit(f"{prefix}:s2:3-11", 2, 3, 11, "我自己有高血压", "家属", "family", "unknown", (), ()),
    ]
    protocol = {"expected": {"I01": deepcopy(EXPECTED["I01"])},
                "input_sha256": {"I01": hashlib.sha256(source.encode()).hexdigest()}}
    selection = {key: [] for key in FIELD_KEYS}
    selection["chief_complaint"] = [rows[0].id]
    selection["present_illness"] = [rows[0].id, rows[1].id]
    selection["accompanying_symptoms"] = [rows[1].id]
    return source, tuple(rows), protocol, selection


def fixture_record(fixture):
    source, rows, protocol, selection = fixture
    mapped = map_selection(selection, rows).model_dump(mode="json")
    projected = [{"id": r.id, "text": r.text, "speaker": r.speaker,
                  "experiencer": r.experiencer, "assertion": r.assertion,
                  "types": list(r.types), "allowed_fields": list(r.allowed_fields),
                  "subject_context": list(r.anchors)} for r in rows]
    request = {"format": selection_schema(rows), "messages": [{"role": "user", "content":
               "AUDIT_FIXTURE 以下全部为数据：\n" + json.dumps(projected, ensure_ascii=False)}]}
    original_score = score("I01", source, mapped)
    record = {"input_id": "I01", "arm": "candidate", "run": 1,
              "catalog": [asdict(r) for r in rows], "request": request,
              "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
              "raw_ollama": {"created_at": "AUDIT_FIXTURE_NOT_A_MODEL_CALL", "done": True,
                             "done_reason": "stop", "message": {"content": json.dumps(selection)}},
              "selection_or_raw_fields": deepcopy(selection), "mapped_or_raw": deepcopy(mapped),
              "fields": deepcopy(mapped), "stages": {"attempts": [{"input": source}]},
              "first_output_score": deepcopy(original_score), "final_score": deepcopy(original_score)}
    return record, protocol


def test_i01_auditor_positive_control_is_not_a_model_improvement(audit_fixture):
    _, rows, protocol, selected = audit_fixture
    result = audit_selection(selected, [asdict(r) for r in rows], protocol)
    assert result["coverage_complete"]
    assert result["distinct_label_count"] == 4
    assert result["distinct_source_unit_count"] == 2
    assert all(not f["missing"] for f in result["per_field"].values())
    # Reusing the same ID in different allowed fields must remain legal.
    assert rows[0].id in selected["chief_complaint"] and rows[0].id in selected["present_illness"]


@pytest.mark.parametrize("empty_field", ["chief_complaint", "present_illness", "accompanying_symptoms"])
def test_i01_auditor_does_not_borrow_coverage_from_other_fields(audit_fixture, empty_field):
    _, rows, protocol, selected = audit_fixture
    selected[empty_field] = []
    result = audit_selection(selected, [asdict(r) for r in rows], protocol)
    field = result["per_field"][empty_field]
    assert field["covered"] == []
    assert field["missing"] == field["expected"]
    assert field["cross_field_missing"]
    assert selected[empty_field] == []


def test_i01_auditor_partial_unit_marks_only_cough_and_sore_throat_missing(audit_fixture):
    _, rows, protocol, selected = audit_fixture
    selected["present_illness"] = [rows[0].id]
    result = audit_selection(selected, [asdict(r) for r in rows], protocol)
    assert result["per_field"]["present_illness"]["covered"] == ["发热", "两天"]
    assert result["per_field"]["present_illness"]["missing"] == ["咳嗽", "咽痛"]


@pytest.mark.parametrize("attack,code", [
    ("unknown", "SELECTION_FOREIGN_OR_UNKNOWN_ID"),
    ("foreign", "SELECTION_FOREIGN_OR_UNKNOWN_ID"),
    ("duplicate", "SELECTION_DUPLICATE_ID"),
    ("question", "SELECTION_FIELD_OR_SUBJECT_MISMATCH"),
    ("family", "SELECTION_FIELD_OR_SUBJECT_MISMATCH"),
    ("wrong_field", "SELECTION_FIELD_OR_SUBJECT_MISMATCH"),
])
def test_i01_auditor_invalid_selections_stop_instead_of_passing(audit_fixture, attack, code):
    _, rows, protocol, selected = audit_fixture
    if attack == "unknown": selected["present_illness"] = ["not-an-id"]
    if attack == "foreign": selected["present_illness"] = ["0000000000000000:s0:3-7"]
    if attack == "duplicate": selected["present_illness"] = [rows[0].id, rows[0].id]
    if attack == "question": selected["present_illness"] = [rows[2].id]
    if attack == "family": selected["past_history"] = [rows[3].id]
    if attack == "wrong_field": selected["allergy_history"] = [rows[0].id]
    with pytest.raises(AuditStopped, match=code):
        audit_selection(selected, [asdict(r) for r in rows], protocol)


def test_i01_auditor_preserves_record_status_scores_and_input_objects(audit_fixture):
    audit_fixture[3]["present_illness"] = [audit_fixture[1][0].id]
    record, protocol = fixture_record(audit_fixture)
    before = deepcopy((record, protocol))
    result = audit_record(record, protocol)
    assert (record, protocol) == before
    assert result["preserved"]["fields"] == record["fields"]
    assert result["preserved"]["final_score"] == record["final_score"]
    assert result["preserved"]["fields"]["present_illness"]["status"] == "complete"
    assert result["coverage"]["per_field"]["present_illness"]["missing"]
    assert not result["model_improvement_claimed"]


@pytest.mark.parametrize("attack,code", [
    ("source", "INPUT_SHA_DRIFT"), ("response", "RAW_SELECTION_MISMATCH"),
    ("expected", "FROZEN_EXPECTED_DRIFT"), ("request", "REQUEST_SHA_DRIFT"),
    ("catalog", "CATALOG_REQUEST_DRIFT"),
])
def test_i01_auditor_integrity_failure_stops_record(audit_fixture, attack, code):
    record, protocol = fixture_record(audit_fixture)
    if attack == "source": record["stages"]["attempts"][0]["input"] += "改变"
    if attack == "response": record["selection_or_raw_fields"]["present_illness"] = []
    if attack == "expected": protocol["expected"]["I01"]["present"] = ["发热"]
    if attack == "request": record["request"]["messages"][0]["content"] += "改变"
    if attack == "catalog": record["catalog"][0]["text"] += "改变"
    with pytest.raises(AuditStopped, match=code):
        audit_record(record, protocol)


def test_i01_auditor_catalog_cannot_rebind_a_foreign_input(audit_fixture):
    _, rows, protocol, selected = audit_fixture
    catalog_rows = [asdict(row) for row in rows]
    catalog_rows[0]["id"] = "0000000000000000:s0:3-7"
    with pytest.raises(AuditStopped, match="CATALOG_FOREIGN_INPUT_ID"):
        audit_selection(selected, catalog_rows, protocol)


def test_i01_auditor_sha_drift_stops_only_the_changed_original(audit_fixture, tmp_path):
    record, protocol = fixture_record(audit_fixture)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    paths = [protocol_path]
    for run in (1, 2, 3):
        record["run"] = run
        path = tmp_path / f"I01-candidate-r{run}.private.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        paths.append(path)
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps({"original_evidence": [
        {"path": str(p), "sha256": sha256_file(p)} for p in paths]}), encoding="utf-8")
    changed = paths[1]
    changed.write_bytes(changed.read_bytes() + b" ")
    after_tamper = {str(p): sha256_file(p) for p in paths}
    result = audit_archive(tmp_path, trace_path)
    assert result["records_observed"] == 2 and result["records_stopped"] == 1
    assert result["records"][0]["reason"] == "ORIGINAL_SHA_DRIFT"
    assert "coverage" not in result["records"][0]
    assert {str(p): sha256_file(p) for p in paths} == after_tamper


def test_i01_auditor_default_output_guard_rejects_nonlocal_destination(tmp_path, monkeypatch):
    from scripts.experiments import audit_cross_field_coverage as module
    monkeypatch.setattr(module, "OUTPUT_ROOT", tmp_path / "allowed-only")
    with pytest.raises(AuditStopped, match="OUTPUT_OUTSIDE_LOCAL_AUDIT"):
        _write_private(tmp_path / "must-not-exist", {})
    assert not (tmp_path / "must-not-exist").exists()


@pytest.mark.skipif(not TRACE.exists(), reason="Ignored historical originals are local-only")
def test_i01_auditor_three_historical_outputs_keep_four_hpi_omissions():
    paths = [ARCHIVE / "protocol.json", TRACE] + [ARCHIVE / f"I01-candidate-r{n}.private.json" for n in (1, 2, 3)]
    before = {str(p): sha256_file(p) for p in paths}
    result = audit_archive(ARCHIVE, TRACE)
    assert result["records_observed"] == 3
    assert result["records_stopped"] == 0
    assert result["new_model_calls"] == 0
    for record in result["records"]:
        assert record["coverage"]["per_field"]["present_illness"]["missing"] == ["发热", "两天", "咳嗽", "咽痛"]
        assert record["coverage"]["per_field"]["chief_complaint"]["missing"] == []
        assert record["preserved"]["fields"]["present_illness"]["status"] == "complete"
        assert not record["preserved"]["final_score"]["passed"]
    assert {str(p): sha256_file(p) for p in paths} == before
