"""Bounded model-only comparison using the unchanged production Ollama request.

Raw conversations/responses stay in ignored local artifacts. No production writes,
prompt changes, output repairs, automatic retries, or model promotion occur here.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone
from unittest.mock import patch
from urllib import request

from app.schemas import MedicalRecordFields
from app.services.field_grounding import FIELD_KEYS, ground_fields
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.llm.ollama_provider import OllamaLLMProvider
from app.services.privacy import anonymize_text
from scripts.experiments.run_evidence_selection import inputs
from scripts.replay_citation_outputs import RecordedProvider, citation_errors, metrics

ROOT = Path(__file__).resolve().parents[2]


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def quality_checks(key: str, fields: MedicalRecordFields, source: str) -> dict[str, bool]:
    """Frozen engineering expectations; not a clinical accuracy score."""
    active = {k for k in FIELD_KEYS if getattr(fields, k).value and not getattr(fields, k).missing}
    value = lambda k: getattr(fields, k).value or ""
    checks = {
        "citations_match_input_and_index": not citation_errors(fields, source),
        "every_nonempty_field_has_evidence": all(getattr(fields, k).source_spans for k in active),
        "missing_flags_consistent": all(not (getattr(fields, k).missing and getattr(fields, k).value) for k in FIELD_KEYS),
    }
    if key == "realtek13":
        checks.update(
            four_expected_fields=active == {"chief_complaint", "present_illness", "accompanying_symptoms", "allergy_history"},
            fever_in_chief="发热" in value("chief_complaint"),
            symptoms_in_illness=all(t in value("present_illness") for t in ["发热", "咳嗽", "咽痛"]),
            exact_temperature="三十八点二度" in value("present_illness"),
            negated_chest_pain="没有胸痛" in value("present_illness"),
            negated_allergy="没有药物过敏史" in value("allergy_history"),
        )
    elif key == "case11":
        checks.update(
            headache_in_chief="头痛" in value("chief_complaint"),
            fever_and_temperature_in_illness=all(t in value("present_illness") for t in ["发烧", "39度"]),
            headache_in_accompanying="头痛" in value("accompanying_symptoms"),
            no_unmentioned_fields=active <= {"chief_complaint", "present_illness", "accompanying_symptoms"},
        )
    elif key in {"question", "family"}:
        checks["no_patient_fact"] = not active
    elif key == "negative_allergy":
        checks.update(allergy_only=active == {"allergy_history"}, negation_preserved="没有花生过敏" in value("allergy_history"))
    elif key == "treatment":
        checks.update(treatment_present="previous_treatment" in active,
                      only_treatment_or_illness=active <= {"previous_treatment", "present_illness"},
                      treatment_and_response=all(t in value("previous_treatment") for t in ["布洛芬", "体温降下来了"]))
    else:
        checks["no_unmentioned_fields"] = active <= {"chief_complaint", "present_illness"}
    return checks


def capture_production_call(provider, source, timeout):
    """Observe the real Provider's transport; return its original response bytes."""
    original = request.urlopen
    captured = []

    def observe(req, *args, **kwargs):
        response = original(req, *args, **kwargs)
        url = req.full_url if isinstance(req, request.Request) else req
        if not url.endswith("/api/chat"):
            return response
        with response:
            raw = response.read()
        captured.append({"request": json.loads(req.data), "response": json.loads(raw), "wire_sha256": sha(raw)})
        return io.BytesIO(raw)

    result, error = None, None
    with patch.object(request, "urlopen", side_effect=observe):
        try:
            result = provider.generate_fields_json(source, timeout_seconds=timeout)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
    if len(captured) > 1:
        raise AssertionError("Unexpected repeated model request")
    return result, error, captured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["qwen3:4b", "qwen3:8b"], required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--deadline", required=True, help="ISO timestamp with timezone")
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.deadline).timestamp()
    if time.time() >= deadline:
        raise SystemExit("TIMEBOX_EXPIRED before first request")
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(args.output / "private.sqlite3")
    os.environ["LLM_MAX_RETRIES"] = "0"
    with request.urlopen(args.url + "/api/tags", timeout=10) as response:
        tag = next(m for m in json.load(response)["models"] if m["name"] == args.model)
    assert tag["digest"] == args.expected_digest, "Model identity changed"
    provider = OllamaLLMProvider(base_url=args.url, model=args.model)
    prepared = list(inputs())
    code_files = ["app/services/llm/ollama_provider.py", "app/prompts/medical_record_prompts.py",
                  "app/services/llm/llm_record_generator.py", "app/services/field_grounding.py",
                  "app/services/clinical_facts.py", "scripts/experiments/compare_local_models.py",
                  "scripts/experiments/run_evidence_selection.py"]
    hashes = {p: sha((ROOT / p).read_bytes()) for p in code_files}
    protocol = {"base_sha": args.base_sha, "code_sha256": hashes, "model": args.model,
                "model_digest": tag["digest"], "runs_per_case": 3, "cases": [p[0] for p in prepared],
                "deadline": args.deadline, "retries": 0, "manual_corrections": 0,
                "contract": "unchanged production Provider payload; model is the comparison variable",
                "criteria": "quality_checks plus unchanged grounding; 21/21 required; no held-out expansion on failure"}
    write(args.output / "protocol.json", protocol)
    write(args.output / "inputs.private.json", [{"id": k, "source": s, "trusted": t, "case": c} for k,s,t,c in prepared])
    report = {**protocol, "started_at": datetime.now(timezone.utc).isoformat(), "calls": []}
    for key, source, trusted, case in prepared:
        safe = anonymize_text(source)
        for run in range(1, 4):
            remaining = deadline - time.time()
            if remaining < 10:
                report["stop_reason"] = "TIMEBOX_EXPIRED"
                break
            record = {"input_id": key, "run": run, "model": args.model, "input_sha256": sha(safe.encode()),
                      "started_at": datetime.now(timezone.utc).isoformat()}
            started = time.monotonic()
            response, error, captured = capture_production_call(provider, safe, min(120, remaining))
            record.update(transport=captured, provider_error=error, passed=False)
            try:
                if response is None:
                    raise RuntimeError(error or "No model response")
                assert len(captured) == 1
                payload = captured[0]["request"]
                neutral = {**payload, "model": "<MODEL>"}
                record["request_without_model_sha256"] = sha(json.dumps(neutral, ensure_ascii=False, sort_keys=True).encode())
                raw_object = json.loads(response.content)
                raw_fields = MedicalRecordFields.model_validate(raw_object.get("fields", raw_object))
                record["first_output"] = raw_fields.model_dump(mode="json")
                record["first_output_checks"] = quality_checks(key, raw_fields, safe)
                checked = ground_fields(raw_fields.model_copy(deep=True), safe, trusted)
                record["first_output_grounded"] = checked.model_dump(mode="json")
                record["conflicts"] = {k: getattr(checked,k).hint for k in FIELD_KEYS if getattr(checked,k).status == "conflicting"}
                record["metrics"] = metrics(checked, case)
                replay = RecordedProvider(raw_object)
                replay.model = args.model; replay.model_digest = tag["digest"]
                generator = LLMRecordGenerator(provider=replay, mode="edge", allow_mock_fallback=False)
                generator.max_retries = 0; generator.source_segments = trusted
                final = generator.extract_fields(source)
                assert replay.calls == 1
                record.update(pipeline=final.model_dump(mode="json"), repairs=generator.field_repairs,
                              pipeline_checks=quality_checks(key, final, safe))
                record["passed"] = all(record["first_output_checks"].values()) and not record["conflicts"]
                record["ollama_timing"] = {k:v for k,v in captured[0]["response"].items()
                    if k in ["total_duration", "load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration", "done_reason"]}
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            record["seconds"] = round(time.monotonic() - started, 3)
            path = args.output / f"{key}-{run}.private.json"
            write(path, record)
            summary = {k:record.get(k) for k in ["input_id", "run", "model", "passed", "seconds", "provider_error", "error", "first_output_checks", "conflicts", "metrics", "request_without_model_sha256", "ollama_timing"]}
            summary["raw_sha256"] = sha(path.read_bytes())
            report["calls"].append(summary)
            write(args.output / "report.json", report)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            if error: # A timeout or resource failure stops this model, never retries it.
                report["stop_reason"] = "PROVIDER_FAILURE"; break
        if report.get("stop_reason"):
            break
    report.update(completed_at=datetime.now(timezone.utc).isoformat(), total=len(report["calls"]),
                  passed=sum(r["passed"] for r in report["calls"]))
    report["gate"] = "SMALL_SPIKE_PASS" if report["total"] == report["passed"] == 21 else "REJECTED"
    write(args.output / "report.json", report)
    print(json.dumps({k:report[k] for k in ["model", "gate", "passed", "total"]}), flush=True)


if __name__ == "__main__":
    main()
