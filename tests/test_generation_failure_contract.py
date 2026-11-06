import json

import pytest

from app.agents import MedicalRecordOrchestrator
from app.db import get_task_steps
from app.schemas import MedicalRecordFields
from app.services.llm.base import LLMProviderResponse
from app.services.llm.llm_record_generator import FIELD_KEYS, LLMRecordGenerator


class ResponseProvider:
    name = "ollama"
    model = "contract-test"

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def generate_fields_json(self, *args, **kwargs):
        self.calls += 1
        return LLMProviderResponse(self.name, self.model, json.dumps(self.payload), 1)


def empty_payload():
    return {**{k: {"value": None, "missing": True, "hint": "null",
                  "confidence": None, "source_spans": []} for k in FIELD_KEYS},
            "candidate_diagnoses": []}


def run_task(tmp_path, monkeypatch, payload):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    p = ResponseProvider(payload)
    g = LLMRecordGenerator(provider=p, mode="edge", allow_mock_fallback=False)
    g.diagnostics_enabled = True
    result = MedicalRecordOrchestrator(g).run_from_text("患者：发热两天。")
    return p, g, result


@pytest.mark.parametrize("hint", [None, "null", " NULL ", "   "])
def test_missing_hint_has_chinese_default(hint):
    p = empty_payload()
    p["past_history"]["hint"] = hint
    fields = LLMRecordGenerator(provider=ResponseProvider(p))._fields_from_response(json.dumps(p))
    assert fields.past_history.hint == "建议补问"


def test_all_discarded_fields_fail_without_revision_or_retries(tmp_path, monkeypatch):
    payload = empty_payload()
    for key in FIELD_KEYS:
        payload[key].update(value="发热两天", source_spans=[{"text": "发热两天", "index": 0}])
    provider, generator, result = run_task(tmp_path, monkeypatch, payload)
    assert provider.calls == 1
    assert result["status"] == "FAILED"
    assert "LLM_OUTPUT_CONTRADICTION" in result["error_message"]
    assert len(get_task_steps(result["task_id"])) == 1
    assert result["llm_trace"]["payload_repairs"]
    assert generator.diagnostic_attempts[0]["raw_response"]
    assert "raw_response" not in json.dumps(result["llm_trace"])
    import sqlite3
    with sqlite3.connect(tmp_path / "test.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM record_revision").fetchone()[0] == 0


def test_no_information_is_distinct_from_contradiction(tmp_path, monkeypatch):
    provider, _, result = run_task(tmp_path, monkeypatch, empty_payload())
    assert provider.calls == 1
    assert result["status"] == "FAILED"
    assert "LLM_NO_SUPPORTED_FACTS" in result["error_message"]


def test_valid_information_and_partial_contradiction_remain_distinct(tmp_path, monkeypatch):
    payload = empty_payload()
    payload["chief_complaint"].update(value="发热两天", missing=False,
                                     source_spans=[{"text": "发热两天", "index": 0}])
    payload["physical_exam"].update(value="正常", source_spans=[{"text": "正常", "index": 0}])
    provider, _, result = run_task(tmp_path, monkeypatch, payload)
    assert provider.calls == 1
    assert result["fields"].chief_complaint.value == "发热两天"
    assert result["fields"].physical_exam.value is None
    assert result["fields"].physical_exam.status == "conflicting"
    assert result["safety_check"].blocked
