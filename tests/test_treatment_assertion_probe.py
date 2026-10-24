from copy import deepcopy
from dataclasses import asdict
import hashlib
import io
import json

import pytest

from scripts.experiments.clinical_fact_selection import catalog, selection_prompt, selection_schema
from scripts.experiments.probe_treatment_assertion import build_variants


def archived(source):
    _, units = catalog(source)
    return {"request": {"model": "qwen3:4b", "options": {"temperature": 0, "num_ctx": 8192},
        "format": selection_schema(units), "messages": [{"role": "user", "content": selection_prompt(units)}]},
        "catalog": [asdict(unit) for unit in units]}


def test_only_assertion_changes_and_archived_input_is_not_modified():
    item = archived("患者：吃了布洛芬以后体温降下来了。")
    original = deepcopy(item)
    base, candidate, units = build_variants(item)
    assert item == original
    assert units[0].assertion == "unknown"
    before = base["messages"][0]["content"]
    after = candidate["messages"][0]["content"]
    assert before.replace('"assertion": "unknown"', '"assertion": "present"') == after
    candidate["messages"][0]["content"] = before
    assert base == candidate


@pytest.mark.parametrize("source", [
    "患者：没有服用布洛芬。", "患者：不清楚是否服用布洛芬。",
    "医生：建议服用布洛芬。", "患者：我父亲吃了布洛芬。",
    "患者：没有服用布洛芬而服用了阿莫西林。",
    "患者：吃了布洛芬，咳嗽两天。",
])
def test_probe_rejects_negated_uncertain_proposed_other_person_or_multi_action(source):
    with pytest.raises(ValueError):
        build_variants(archived(source))


def test_catalog_drift_is_rejected_instead_of_guessed():
    item = archived("患者：吃了布洛芬以后体温降下来了。")
    item["catalog"][0]["text"] = "其他原文"
    with pytest.raises(ValueError, match="CATALOG_REQUEST"):
        build_variants(item)


def test_deadline_before_case_request_is_not_counted_as_model_call(tmp_path, monkeypatch):
    from scripts.experiments import probe_treatment_assertion as probe
    artifact = tmp_path / "archive.json"
    artifact.write_text(json.dumps(archived("患者：吃了布洛芬以后体温降下来了。"), ensure_ascii=False), encoding="utf8")
    requests = []
    class Opener:
        def open(self, req, **kwargs):
            requests.append(req.full_url)
            payload = {"models": [{"name": "qwen3:4b", "digest": "a" * 64}]} if req.full_url.endswith("/api/tags") else {"done": True}
            return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(probe, "build_opener", lambda *args: Opener())
    times = iter((0, 0, 2))
    monkeypatch.setattr(probe.time, "time", lambda: next(times))
    output = tmp_path / "result"
    monkeypatch.setattr("sys.argv", ["probe", "--archive", str(artifact), "--archive-sha256",
        hashlib.sha256(artifact.read_bytes()).hexdigest(), "--url", "http://127.0.0.1:11435",
        "--digest", "a" * 64, "--output", str(output), "--deadline", "1970-01-01T00:00:01+00:00"])
    with pytest.raises(TimeoutError, match="TIMEBOX_EXPIRED"):
        probe.main()
    summary = json.loads((output / "summary.json").read_text())
    assert summary["attempted_cases"] == 1
    assert summary["case_calls"] == summary["http_requests_started"] == summary["responses_received"] == 0
    assert len(requests) == 2 and all(not url.endswith("/api/chat") for url in requests)
