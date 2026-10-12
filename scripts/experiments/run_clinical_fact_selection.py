"""18 archived offline replays, then preregistered 18 local single-call comparisons.

Only synthetic B01/I01/P01 sources. Raw text and responses stay in ignored output.
Never deploy, retry, correct model selections, or overwrite earlier evidence.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from unittest.mock import patch

from app.prompts.medical_record_prompts import MEDICAL_RECORD_SYSTEM_PROMPT
from app.services.clinical_facts import split_clinical_segments
from app.services.field_grounding import FIELD_KEYS
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.llm.ollama_provider import extraction_schema, numbered_source
from scripts.experiments.clinical_fact_selection import catalog, map_selection, selection_prompt, selection_schema
from scripts.replay_citation_outputs import DIGEST, RecordedProvider

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "B01": {"chief": ["发热", "两天"], "present": ["发热", "两天", "咳嗽", "咽痛", "三十八点二", "没有胸痛"], "accompanying": ["咳嗽", "咽痛"], "allergy": "没有药物过敏"},
    "I01": {"chief": ["发热", "两天"], "present": ["发热", "两天", "咳嗽", "咽痛", "三十八点二", "没有胸痛"], "accompanying": ["咳嗽", "咽痛"], "allergy": "没有药物过敏"},
    "P01": {"chief": ["咳嗽", "两天"], "present": ["孩子", "咳嗽", "两天", "咽痛", "三十八点二"], "accompanying": ["咽痛"], "allergy": "不清楚"},
}
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": 2048}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score(case, source, fields):
    if fields is None:
        return {"passed": False, "errors": ["no_fields"]}
    data = fields.model_dump(mode="json") if hasattr(fields, "model_dump") else fields
    data = data.get("fields", data)
    errors = []
    wanted = EXPECTED[case]
    for key, names in (("chief_complaint", wanted["chief"]), ("present_illness", wanted["present"]),
                       ("accompanying_symptoms", wanted["accompanying"]), ("allergy_history", [wanted["allergy"]])):
        field = data.get(key) or {}
        value = field.get("value") or ""
        if field.get("missing") or not value or field.get("status") == "conflicting":
            errors.append(key + ":missing_or_conflicting")
        errors.extend(key + ":missing_fact:" + n for n in names if n not in value)
    sentences = split_clinical_segments(source)
    for key in FIELD_KEYS:
        field = data.get(key) or {}
        value = field.get("value")
        if value in (None, "", "null"):
            continue
        if key in {"past_history", "previous_treatment", "physical_exam"}:
            errors.append(key + ":unsupported_field")
        if any(word in value for word in ("父亲", "高血压")):
            errors.append(key + ":wrong_patient_subject")
        if field.get("missing"):
            errors.append(key + ":nonempty_marked_missing")
        if field.get("status") == "conflicting":
            errors.append(key + ":conflicting")
        spans = field.get("source_spans") or []
        if not spans:
            errors.append(key + ":no_quote")
        for span in spans:
            quote, index = span.get("text"), span.get("index")
            if not quote or quote not in source:
                errors.append(key + ":quote_not_exact")
            if not isinstance(index, int) or not 0 <= index < len(sentences) or quote not in sentences[index]:
                errors.append(key + ":quote_index_mismatch")
        evidence = "\n".join(s.get("text") or "" for s in spans)
        if any(c.strip() not in evidence for c in re.split(r"[，,。；;\n]", value) if c.strip()):
            errors.append(key + ":value_not_supported")
    if case == "P01" and "没有" in ((data.get("allergy_history") or {}).get("value") or ""):
        errors.append("allergy_history:unknown_changed_to_absent")
    if case == "I01" and "头痛" in "".join((data.get(k) or {}).get("value") or "" for k in FIELD_KEYS):
        errors.append("unanswered_headache_filled")
    return {"passed": not errors, "errors": sorted(set(errors))}


def pipeline(content, source):
    provider = RecordedProvider(content)
    generator = LLMRecordGenerator(provider=provider, allow_mock_fallback=False)
    generator.max_retries = 0
    generator.diagnostics_enabled = True
    fields, error = None, None
    try:
        fields = generator.extract_fields(source)
    except Exception as exc:
        error = str(exc)
    assert provider.calls == 1
    return fields, {"attempts": generator.diagnostic_attempts, "repairs": generator.field_repairs,
        "error": error, "provider_calls": provider.calls}


def offline(archive, output):
    output.mkdir(parents=True, exist_ok=False)
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(output / "identity-map.sqlite3")
    rows = []
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden in offline replay")):
        for path in sorted(archive.glob("*-r*-t*.private.json")):
            item = json.loads(path.read_text(encoding="utf8"))
            source = item["attempts"][0]["input"]
            content = json.loads(item["model_raw"]["message"]["content"])
            fields, stages = pipeline(content, source)
            result = {"input_id": item["case"], "archive_file": path.name, "archive_sha256": sha(path),
                "temperature": item["temperature"], "raw": score(item["case"], source, content),
                "saved_pipeline": score(item["case"], source, item["fields"]),
                "current_pipeline": score(item["case"], source, fields)}
            write(output / path.name, {**result, "stages": stages, "fields": fields.model_dump(mode="json") if fields else None})
            rows.append(result)
    report = {"real_model_calls": 0, "runs": len(rows), "rows": rows,
        "passes": {stage: sum(r[stage]["passed"] for r in rows) for stage in ("raw", "saved_pipeline", "current_pipeline")}}
    assert len(rows) == 18
    write(output / "report.json", report)
    return report


def remote(container, path, payload=None):
    # Internal Docker URL only; no host port, application API or clinical DB writes.
    code = "import json,sys; from urllib.request import Request,urlopen; p=json.load(sys.stdin); req=Request('http://ollama:11434'+p['path'],data=json.dumps(p['body'],ensure_ascii=False).encode() if p['body'] is not None else None,headers={'Content-Type':'application/json'}); print(urlopen(req,timeout=120).read().decode())"
    proc = subprocess.run(["docker", "exec", "-i", container, "python", "-c", code],
        input=json.dumps({"path": path, "body": payload}, ensure_ascii=False), capture_output=True,
        text=True, encoding="utf8", timeout=140, check=True)
    return json.loads(proc.stdout)


def compare(archive, output, container):
    output.mkdir(parents=True, exist_ok=False)
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(output / "identity-map.sqlite3")
    tag = next(m for m in remote(container, "/api/tags")["models"] if m["name"] == "qwen3:4b")
    assert tag["digest"] == DIGEST, "Model digest changed; no inference permitted"
    sources = {key: json.loads((archive / f"{key}-r1-t0.private.json").read_text(encoding="utf8"))["attempts"][0]["input"] for key in EXPECTED}
    hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for directory in (ROOT / "app", ROOT / "scripts/experiments") for p in sorted(directory.rglob("*.py"))}
    protocol = {"started_at": datetime.now(timezone.utc).isoformat(), "base_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_sha256": hashes, "model_digest": DIGEST, "server": remote(container, "/api/version"),
        "options": OPTIONS, "think": False, "retries": 0, "manual_corrections": 0,
        "calls_planned": 18, "expected": EXPECTED, "input_sha256": {k: hashlib.sha256(s.encode()).hexdigest() for k, s in sources.items()},
        "stop": "Finish exactly 18 planned single calls; candidate <9/9 prohibits boundary/full-set/deployment expansion.",
        "scope": "Synthetic text only; no new ASR, audio, clinical DB, production-provider change or deployment"}
    write(output / "protocol.json", protocol)
    results = []
    for key, source in sources.items():
        _, units = catalog(source)
        for run in range(1, 4):
            for arm in ("baseline", "candidate"):
                payload = {"model": "qwen3:4b", "stream": False, "think": False, "options": OPTIONS, "keep_alive": "30m"}
                if arm == "baseline":
                    payload.update(format=extraction_schema(), messages=[{"role": "system", "content": MEDICAL_RECORD_SYSTEM_PROMPT}, {"role": "user", "content": numbered_source(source)}])
                else:
                    payload.update(format=selection_schema(units), messages=[{"role": "user", "content": selection_prompt(units)}])
                start = time.monotonic()
                record = {"input_id": key, "run": run, "arm": arm, "request": payload,
                    "request_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                    "catalog": [asdict(u) for u in units] if arm == "candidate" else None}
                try:
                    raw = remote(container, "/api/chat", payload)
                    record["raw_ollama"] = raw
                    if raw.get("done_reason") == "length":
                        raise ValueError("LLM_OUTPUT_TRUNCATED")
                    parsed = json.loads(raw["message"]["content"])
                    record["selection_or_raw_fields"] = parsed
                    content = map_selection(parsed, units).model_dump(mode="json") if arm == "candidate" else parsed
                    record["first_output_score"] = score(key, source, content)
                    fields, stages = pipeline(content, source)
                    record.update(stages=stages, final_score=score(key, source, fields),
                        mapped_or_raw=content, fields=fields.model_dump(mode="json") if fields else None)
                    passed = record["first_output_score"]["passed"] and record["final_score"]["passed"]
                except Exception as exc:
                    record["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
                    passed = False
                record.update(passed=passed, seconds=round(time.monotonic() - start, 3))
                path = output / f"{key}-{arm}-r{run}.private.json"
                write(path, record)
                summary = {k: record[k] for k in ("input_id", "run", "arm", "passed", "seconds")}
                summary.update(first_output_score=record.get("first_output_score"), final_score=record.get("final_score"), error=record.get("error"), raw_sha256=sha(path))
                results.append(summary)
                write(output / "report.json", {"calls": results})
                print(json.dumps(summary, ensure_ascii=False), flush=True)
    passed = {arm: sum(r["passed"] for r in results if r["arm"] == arm) for arm in ("baseline", "candidate")}
    report = {"completed_at": datetime.now(timezone.utc).isoformat(), "calls": results,
        "actual_calls": len(results), "passed": passed, "gate": "SMALL_SPIKE_PASS" if passed["candidate"] == 9 else "REJECTED",
        "candidate_source_unchanged": all(sha(ROOT / path) == digest for path, digest in hashes.items())}
    if not report["candidate_source_unchanged"]:
        report["gate"] = "INVALID_SOURCE_DRIFT"
    write(output / "report.json", report)
    print(json.dumps({k: report[k] for k in ("actual_calls", "passed", "gate", "candidate_source_unchanged")}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("offline", "compare"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--container", default="mra51usage8798-app-1")
    args = parser.parse_args()
    result = offline(args.archive, args.output) if args.mode == "offline" else compare(args.archive, args.output, args.container)
    if args.mode == "offline":
        print(json.dumps({k: result[k] for k in ("real_model_calls", "runs", "passes")}), flush=True)


if __name__ == "__main__":
    main()
