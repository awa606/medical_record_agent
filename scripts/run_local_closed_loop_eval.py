"""Real Ollama evaluation. Synthetic corpus only; raw results stay in a private output directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone

from app.services.llm.factory import create_llm_record_generator
from app.services.clinical_facts import extract_clinical_facts
from app.services.field_grounding import FIELD_KEYS

ROOT = Path(__file__).resolve().parents[1]


def fact_key(fact):
    value = fact.get("value")
    if value is not None:
        value = str(value).replace("°C", "").replace("℃", "").replace(" ", "")
    return (fact.get("type"), fact.get("name"), fact.get("assertion", "present"), value, fact.get("unit"))


def evaluate(fields, case):
    active = [getattr(fields, k) for k in FIELD_KEYS if not getattr(fields, k).missing and getattr(fields, k).value]
    safe = [field for field in active if field.status != "conflicting"]
    expected = {fact_key(fact) for fact in case["expected"].get("facts", [])}
    actual = {fact_key(vars(fact)) for fact in extract_clinical_facts("。".join(field.value for field in safe))}
    return {
        "schema_field_presence": sum(k in fields.model_dump() for k in FIELD_KEYS) / len(FIELD_KEYS),
        "nonempty_fields": len(active), "grounded_fields": len(safe),
        "conflicting_fields": len(active) - len(safe),
        "expected_facts": len(expected), "recovered_facts": len(actual & expected),
        "extra_fact_keys": [list(k) for k in sorted(actual - expected, key=str)],
        "fact_recall": len(actual & expected) / len(expected) if expected else None,
        "warning": "Automatic fact parser proxy; extra keys require review, not a clinical hallucination verdict.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing evaluation")
    args.output.mkdir(parents=True)
    os.environ.setdefault("RECORD_PROVIDER_MODE", "edge")
    os.environ.setdefault("MRA_ANONYMIZE", "1")
    os.environ.setdefault("LLM_PROVIDER", "ollama")
    os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11435")
    os.environ.setdefault("OLLAMA_MODEL", "qwen3:4b")
    os.environ.setdefault("LLM_TIMEOUT_SECONDS", "120")
    os.environ.setdefault("LLM_MAX_RETRIES", "0")
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(args.output / "private.sqlite3")
    paths = sorted((ROOT / "data/clinical_e2e/field_disease_pack_v1/cases").glob("*.json"))[args.start-1:args.end]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source_hash = hashlib.sha256(b"".join(p.relative_to(ROOT).as_posix().encode() + p.read_bytes() for p in sorted((ROOT / "app").rglob("*.py")))).hexdigest()
    result = {"started_at": datetime.now(timezone.utc).isoformat(), "git_sha": sha,
              "app_source_sha256": source_hash, "split": [args.start, args.end],
              "environment": "development PC, real local Ollama, synthetic typed transcripts",
              "method": "Seven schema fields plus nonempty/grounding/automatic fact-recall counters; missing fields are not assumed normal.",
              "cases": []}
    for path in paths:
        case = json.loads(path.read_text(encoding="utf-8"))
        assert case["privacy"]["synthetic"]
        text = "\n".join(f'{s["role"]}：{s["text"]}' for s in case["segments"])
        generator = create_llm_record_generator()
        start = time.perf_counter()
        row = {"case_id": case["case_id"], "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        try:
            fields = generator.extract_fields(text)
            draft = generator.generate_draft(fields)
            safety = generator.safety_check(draft, fields)
            row.update(evaluate(fields, case))
            row.update({"success": True, "safety_blocked": safety.blocked, "trace": generator.get_trace()})
            (args.output / f'{case["case_id"]}.json').write_text(json.dumps({"fields": fields.model_dump(), "safety": safety.model_dump()},ensure_ascii=False,indent=2),encoding="utf-8")
        except Exception as exc:
            row.update({"success": False, "error": str(exc)[:300]})
        row["seconds"] = round(time.perf_counter() - start, 3)
        result["cases"].append(row)
        (args.output / "report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({k: row.get(k) for k in ("case_id","success","seconds","nonempty_fields","conflicting_fields","fact_recall")}), flush=True)
    rows = result["cases"]
    latencies = sorted(r["seconds"] for r in rows)
    result["summary"] = {"cases":len(rows), "schema_valid":sum(r.get("success",False) for r in rows),
        "nonempty_fields":sum(r.get("nonempty_fields",0) for r in rows),
        "grounded_fields":sum(r.get("grounded_fields",0) for r in rows),
        "conflicting_fields":sum(r.get("conflicting_fields",0) for r in rows),
        "expected_facts":sum(r.get("expected_facts",0) for r in rows),
        "recovered_facts":sum(r.get("recovered_facts",0) for r in rows),
        "p95_seconds":latencies[math.ceil(.95*len(latencies))-1], "max_seconds":max(latencies),
        "mock_fallback_count":sum(bool(r.get("trace",{}).get("fallback")) for r in rows)}
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    (args.output / "report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result["summary"]),flush=True)


if __name__ == "__main__":
    main()
