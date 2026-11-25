"""Raw diagnostics require explicit opt-in; operational accounting survives."""
import json
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import Mock

import pytest

from app.services.llm.deepseek_provider import BudgetLedger, DeepSeekDemoProvider, MODEL, SpikeError


def provider(tmp_path):
    return DeepSeekDemoProvider(api_key="synthetic-test-key", output=tmp_path / "diagnostics",
                               ledger=BudgetLedger(tmp_path / "ledger.json"))


def test_raw_save_is_disabled_by_default_and_cannot_create_an_artifact(tmp_path):
    candidate = provider(tmp_path)
    assert candidate.diagnostics_enabled is False
    candidate.save("request.json", {"messages": [{"content": "患者合成原文"}]})
    candidate.save("raw_response.json", {"content": "模型合成原文"})
    candidate.save("model_first_output.json", {"value": "模型合成字段"})
    candidate.save("http_error.json", {"status": 503, "body": "上游回显原文"})
    assert not candidate.output.exists()


def test_operational_metadata_is_allowlisted_when_raw_capture_is_off(tmp_path):
    candidate = provider(tmp_path)
    candidate.diagnostics_enabled = False
    candidate.save("response_metadata.json", {
        "request_id": "request-123", "model": MODEL, "finish_reason": "stop",
        "latency_ms": 42, "budget_call_id": "a" * 32,
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "content": "合成病历"},
        "body": "患者全文", "transport_mode": "direct", "field_contract": "clause_v1",
    })
    saved = json.loads((candidate.output / "response_metadata.json").read_text(encoding="utf-8"))
    assert saved["latency_ms"] == 42
    assert saved["usage"] == {"prompt_tokens": 10, "completion_tokens": 2}
    assert "body" not in saved and "合成病历" not in json.dumps(saved, ensure_ascii=False)


@pytest.mark.parametrize("failure", [False, True])
def test_call_without_raw_capture_retains_accounting_and_does_not_retry(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("MRA_ANONYMIZE", "1")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "identity.sqlite3"))
    candidate = provider(tmp_path)
    candidate.diagnostics_enabled = False
    opener = Mock()
    if failure:
        opener.open.side_effect = TimeoutError("synthetic patient content")
    else:
        body = {"id": "request-123", "model": MODEL,
                "choices": [{"finish_reason": "stop", "message": {"content": '{"value":"合成字段"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
        opener.open.return_value.__enter__ = Mock(return_value=Mock(read=Mock(return_value=json.dumps(body).encode())))
        opener.open.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(candidate, "_opener", lambda: opener)
    if failure:
        with pytest.raises(SpikeError, match="TRANSPORT_TIMEOUT"):
            candidate.generate_fields_json("患者：咳嗽。", timeout_seconds=1)
    else:
        assert "合成字段" in candidate.generate_fields_json("患者：咳嗽。", timeout_seconds=1).content
    assert opener.open.call_count == 1
    assert candidate.last_diagnostic_response is None
    names = {path.name for path in (tmp_path / "diagnostics").rglob("*.json")}
    assert names == ({"response_metadata.json", "failure.json"} if failure else {"response_metadata.json"})
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert len(ledger["calls"]) == 1
    assert ledger["calls"][0]["state"] == ("failed_reservation_retained" if failure else "settled")


def test_explicit_synthetic_capture_preserves_raw_evidence_but_redacts_key(tmp_path):
    candidate = provider(tmp_path)
    candidate.diagnostics_enabled = True
    candidate.save("raw_response.json", {"content": "合成原文", "echo": "synthetic-test-key"})
    saved = (candidate.output / "raw_response.json").read_text(encoding="utf-8")
    assert "合成原文" in saved and "synthetic-test-key" not in saved


def test_http_failure_body_is_not_captured_or_retried(tmp_path, monkeypatch):
    monkeypatch.setenv("MRA_ANONYMIZE", "1")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "identity.sqlite3"))
    candidate = provider(tmp_path)
    opener = Mock()
    opener.open.side_effect = HTTPError(candidate.endpoint, 503, "synthetic upstream",
        {}, BytesIO("合成患者原文 synthetic-test-key".encode()))
    monkeypatch.setattr(candidate, "_opener", lambda: opener)
    with pytest.raises(SpikeError, match="HTTP_503"):
        candidate.generate_fields_json("患者：咳嗽。", timeout_seconds=1)
    assert opener.open.call_count == 1
    files = list((tmp_path / "diagnostics").rglob("*.json"))
    assert {p.name for p in files} == {"failure.json", "response_metadata.json"}
    all_text = "".join(p.read_text(encoding="utf8") for p in files)
    assert "合成患者" not in all_text and "synthetic-test-key" not in all_text
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf8"))
    assert len(ledger["calls"]) == 1
    assert ledger["calls"][0]["state"] == "failed_reservation_retained"
    assert ledger["calls"][0]["failure"] == "HTTP_503"
